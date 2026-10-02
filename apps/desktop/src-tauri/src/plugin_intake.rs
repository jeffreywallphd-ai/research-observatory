//! Native-only connector archive intake. Package bytes and selected paths never
//! enter the renderer; Core holds only a short-lived, project-bound review token.

use crate::application_lock::ApplicationLockManager;
use crate::directory_picker::{DirectoryPickerManager, PickerFailure};
use crate::supervisor::{NativeImportConnection, NativePluginAction, RuntimeSupervisor};
use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};

const MAX_ARCHIVE_BYTES: u64 = 64 * 1024 * 1024;
const MAX_CHUNKS: u32 = 512;
const MAX_RESPONSE_BYTES: usize = 32 * 1024;

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct PluginIntakeRequest {
    pub root: String,
    pub project_id: String,
    pub operation_id: String,
}

fn hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn new_action_id() -> Result<String, &'static str> {
    let mut bytes = [0_u8; 16];
    crate::supervisor::fill_secure_random(&mut bytes)?;
    let milliseconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "RO-PLUGIN-CLOCK-UNAVAILABLE")?
        .as_millis() as u64;
    bytes[..6].copy_from_slice(&milliseconds.to_be_bytes()[2..]);
    bytes[6] = 0x70 | (bytes[6] & 0x0f);
    bytes[8] = 0x80 | (bytes[8] & 0x3f);
    Ok(format!(
        "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
        bytes[0],
        bytes[1],
        bytes[2],
        bytes[3],
        bytes[4],
        bytes[5],
        bytes[6],
        bytes[7],
        bytes[8],
        bytes[9],
        bytes[10],
        bytes[11],
        bytes[12],
        bytes[13],
        bytes[14],
        bytes[15]
    ))
}

pub(crate) fn decode_request(payload: &Value) -> Option<PluginIntakeRequest> {
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Envelope {
        request: PluginIntakeRequest,
    }
    let request = serde_json::from_value::<Envelope>(payload.clone())
        .ok()?
        .request;
    (crate::directory_picker::local_path_syntax(&request.root)
        && crate::supervisor::canonical_project_id(&request.project_id)
        && hex(&request.operation_id, 32))
    .then_some(request)
}

#[derive(Serialize)]
#[serde(tag = "status", rename_all = "kebab-case")]
pub(crate) enum PluginIntakeOutcome {
    Reviewed {
        #[serde(rename = "packageToken")]
        package_token: String,
        #[serde(rename = "expiresAt")]
        expires_at: String,
        review: Value,
    },
    Cancelled,
    Unavailable,
    Failed,
}

type ActiveIntake = Arc<Mutex<Option<(String, Arc<AtomicBool>)>>>;

#[derive(Default, Clone)]
pub(crate) struct PluginIntakeManager {
    active: ActiveIntake,
    cancelled_before_start: Arc<Mutex<Option<String>>>,
}

struct Permit {
    manager: PluginIntakeManager,
    cancelled: Arc<AtomicBool>,
}

impl Drop for Permit {
    fn drop(&mut self) {
        if let Ok(mut active) = self.manager.active.lock()
            && active
                .as_ref()
                .is_some_and(|(_, flag)| Arc::ptr_eq(flag, &self.cancelled))
        {
            *active = None;
        }
    }
}

impl PluginIntakeManager {
    fn begin(&self, operation_id: &str) -> Result<Permit, PickerFailure> {
        if !hex(operation_id, 32) {
            return Err(PickerFailure::Failed);
        }
        let mut early = self
            .cancelled_before_start
            .lock()
            .map_err(|_| PickerFailure::Failed)?;
        if early.as_deref() == Some(operation_id) {
            *early = None;
            return Err(PickerFailure::Cancelled);
        }
        let mut active = self.active.lock().map_err(|_| PickerFailure::Failed)?;
        if active.is_some() {
            return Err(PickerFailure::Unavailable);
        }
        let cancelled = Arc::new(AtomicBool::new(false));
        *active = Some((operation_id.to_owned(), Arc::clone(&cancelled)));
        Ok(Permit {
            manager: self.clone(),
            cancelled,
        })
    }

    pub(crate) fn cancel(&self, operation_id: &str, picker: &DirectoryPickerManager) {
        if !hex(operation_id, 32) {
            return;
        }
        let Ok(mut early) = self.cancelled_before_start.lock() else {
            return;
        };
        let flag = self.active.lock().ok().and_then(|active| {
            active
                .as_ref()
                .filter(|(id, _)| id == operation_id)
                .map(|(_, flag)| Arc::clone(flag))
        });
        if let Some(flag) = flag {
            flag.store(true, Ordering::Release);
            picker.cancel_pending();
        } else {
            *early = Some(operation_id.to_owned());
        }
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Context {
    project_id: String,
    session_id: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct IntakeStatus {
    intake_id: String,
    state: String,
    byte_length: u64,
    chunk_count: u32,
    package_token: Option<String>,
}

struct PendingPackage {
    connection: Arc<NativeImportConnection>,
    address: Value,
    intake_id: Option<String>,
    accepted: bool,
}

impl PendingPackage {
    fn request(&self, action: NativePluginAction, extra: Value) -> Result<Value, PickerFailure> {
        let mut body = self
            .address
            .as_object()
            .ok_or(PickerFailure::Failed)?
            .clone();
        if let Some(id) = &self.intake_id
            && matches!(
                action,
                NativePluginAction::Chunk | NativePluginAction::Seal | NativePluginAction::Cancel
            )
        {
            body.insert("intakeId".into(), id.clone().into());
        }
        body.extend(extra.as_object().ok_or(PickerFailure::Failed)?.clone());
        let response = self
            .connection
            .plugin_request(action, Value::Object(body))
            .map_err(|_| PickerFailure::Failed)?;
        if response.status != 200
            || response.content_type != "application/json"
            || response.body.len() > MAX_RESPONSE_BYTES
        {
            return Err(PickerFailure::Failed);
        }
        serde_json::from_str(&response.body).map_err(|_| PickerFailure::Failed)
    }

    fn status(&self, value: Value) -> Result<IntakeStatus, PickerFailure> {
        let status: IntakeStatus =
            serde_json::from_value(value).map_err(|_| PickerFailure::Failed)?;
        if !crate::supervisor::canonical_uuid_v7(&status.intake_id)
            || self
                .intake_id
                .as_ref()
                .is_some_and(|id| id != &status.intake_id)
            || status.byte_length > MAX_ARCHIVE_BYTES
            || status.chunk_count > MAX_CHUNKS
            || !matches!(status.state.as_str(), "receiving" | "sealed" | "cancelled")
            || status
                .package_token
                .as_ref()
                .is_some_and(|token| !hex(token, 64))
        {
            return Err(PickerFailure::Failed);
        }
        Ok(status)
    }
}

impl Drop for PendingPackage {
    fn drop(&mut self) {
        if self.intake_id.is_some() && !self.accepted {
            // Same exact project/Core session only. Close/lock also clears Core's
            // ephemeral intake state even when this best-effort RPC is fenced.
            let _ = self.request(NativePluginAction::Cancel, json!({}));
        }
    }
}

pub(crate) struct PreparedPlugin {
    pending: PendingPackage,
    permit: Permit,
    package_token: String,
    expires_at: String,
    review: Value,
}

impl PreparedPlugin {
    pub(crate) fn accept(&mut self) -> bool {
        let Ok(active) = self.permit.manager.active.lock() else {
            return false;
        };
        if self.permit.cancelled.load(Ordering::Acquire)
            || !active
                .as_ref()
                .is_some_and(|(_, flag)| Arc::ptr_eq(flag, &self.permit.cancelled))
            || !self.pending.connection.is_current()
        {
            return false;
        }
        self.pending.accepted = true;
        true
    }

    pub(crate) fn into_outcome(self) -> PluginIntakeOutcome {
        PluginIntakeOutcome::Reviewed {
            package_token: self.package_token,
            expires_at: self.expires_at,
            review: self.review,
        }
    }
}

#[cfg(windows)]
pub(crate) fn prepare(
    manager: PluginIntakeManager,
    picker: DirectoryPickerManager,
    supervisor: RuntimeSupervisor,
    lock: ApplicationLockManager,
    ticket: u64,
    owner: isize,
    request: PluginIntakeRequest,
) -> Result<PreparedPlugin, PickerFailure> {
    let permit = manager.begin(&request.operation_id)?;
    if permit.cancelled.load(Ordering::Acquire)
        || lock.finish_protected_action(ticket).is_err()
        || !picker.is_open()
    {
        return Err(PickerFailure::Cancelled);
    }
    let connection = Arc::new(
        supervisor
            .native_import_connection(&request.root, &request.project_id)
            .map_err(|_| PickerFailure::Unavailable)?,
    );
    let mut pending = PendingPackage {
        connection: Arc::clone(&connection),
        address: json!({"root":request.root,"projectId":request.project_id}),
        intake_id: None,
        accepted: false,
    };
    let context: Context =
        serde_json::from_value(pending.request(NativePluginAction::Context, json!({}))?)
            .map_err(|_| PickerFailure::Failed)?;
    if context.project_id != request.project_id || !hex(&context.session_id, 32) {
        return Err(PickerFailure::Failed);
    }
    pending.address["sessionId"] = context.session_id.into();
    let cancelled = Arc::clone(&permit.cancelled);
    let checking_picker = picker.clone();
    picker.import_source(
        owner,
        move || {
            !cancelled.load(Ordering::Acquire)
                && checking_picker.is_open()
                && lock.finish_protected_action(ticket).is_ok()
                && connection.is_current()
        },
        move |source, authorized| {
            let created =
                pending.status(pending.request(NativePluginAction::Create, json!({}))?)?;
            pending.intake_id = Some(created.intake_id);
            if created.state != "receiving"
                || created.byte_length != 0
                || created.chunk_count != 0
                || created.package_token.is_some()
            {
                return Err(PickerFailure::Failed);
            }
            let mut accepted_bytes = 0_u64;
            let seal = source
                .transfer(
                    || authorized(),
                    |ordinal, bytes| {
                        if ordinal > MAX_CHUNKS
                            || accepted_bytes + bytes.len() as u64 > MAX_ARCHIVE_BYTES
                        {
                            return Err("RO-PLUGIN-ARCHIVE-LIMIT");
                        }
                        let data = base64::engine::general_purpose::STANDARD.encode(bytes);
                        let status = pending
                            .request(
                                NativePluginAction::Chunk,
                                json!({"ordinal":ordinal,"data":data}),
                            )
                            .and_then(|value| pending.status(value))
                            .map_err(|_| "RO-PLUGIN-TRANSFER-FAILED")?;
                        accepted_bytes += bytes.len() as u64;
                        if status.state != "receiving"
                            || status.byte_length != accepted_bytes
                            || status.chunk_count != ordinal
                            || status.package_token.is_some()
                        {
                            return Err("RO-PLUGIN-TRANSFER-FAILED");
                        }
                        Ok(())
                    },
                )
                .map_err(|_| {
                    if authorized() {
                        PickerFailure::Failed
                    } else {
                        PickerFailure::Cancelled
                    }
                })?;
            if !authorized() {
                return Err(PickerFailure::Cancelled);
            }
            if seal.byte_length == 0 {
                return Err(PickerFailure::Failed);
            }
            let sealed = pending.status(pending.request(
                NativePluginAction::Seal,
                json!({
                    "archiveSha256":format!("sha256:{}",seal.source_sha256),
                    "byteLength":seal.byte_length,"chunkCount":seal.chunk_count
                }),
            )?)?;
            if sealed.state != "sealed"
                || sealed.byte_length != seal.byte_length
                || sealed.chunk_count != seal.chunk_count
            {
                return Err(PickerFailure::Failed);
            }
            let token = sealed.package_token.ok_or(PickerFailure::Failed)?;
            let reviewed =
                pending.request(NativePluginAction::Review, json!({"packageToken":token}))?;
            if !authorized() || reviewed["packageToken"].as_str() != Some(token.as_str()) {
                return Err(PickerFailure::Cancelled);
            }
            let expires_at = reviewed["expiresAt"]
                .as_str()
                .ok_or(PickerFailure::Failed)?;
            let review = reviewed["review"]
                .as_object()
                .ok_or(PickerFailure::Failed)?;
            if expires_at.len() > 64 || review.len() > 32 {
                return Err(PickerFailure::Failed);
            }
            Ok(PreparedPlugin {
                pending,
                permit,
                package_token: token,
                expires_at: expires_at.to_owned(),
                review: Value::Object(review.clone()),
            })
        },
    )
}

pub(crate) fn failure(error: PickerFailure) -> PluginIntakeOutcome {
    match error {
        PickerFailure::Cancelled => PluginIntakeOutcome::Cancelled,
        PickerFailure::Unavailable => PluginIntakeOutcome::Unavailable,
        PickerFailure::Failed => PluginIntakeOutcome::Failed,
    }
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct PluginActionRequest {
    root: String,
    project_id: String,
    kind: String,
    #[serde(default)]
    package_token: Option<String>,
    #[serde(default)]
    plugin_id: Option<String>,
    #[serde(default)]
    publisher_key_id: Option<String>,
}

pub(crate) fn decode_action(payload: &Value) -> Option<PluginActionRequest> {
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Envelope {
        request: PluginActionRequest,
    }
    let request = serde_json::from_value::<Envelope>(payload.clone())
        .ok()?
        .request;
    if !crate::directory_picker::local_path_syntax(&request.root)
        || !crate::supervisor::canonical_project_id(&request.project_id)
    {
        return None;
    }
    let valid_id = |value: &str| {
        !value.is_empty()
            && value.len() <= 128
            && value.bytes().all(|byte| {
                byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'-' | b'_' | b':')
            })
    };
    let package_token = request
        .package_token
        .as_ref()
        .is_some_and(|value| hex(value, 64));
    let plugin_id = request
        .plugin_id
        .as_ref()
        .is_some_and(|value| valid_id(value));
    let publisher = request
        .publisher_key_id
        .as_ref()
        .is_some_and(|value| valid_id(value));
    let valid = match request.kind.as_str() {
        "review" | "discard" | "grant-enable" => package_token && !plugin_id && !publisher,
        "grant-status" | "grant-revoke" => plugin_id && !package_token && !publisher,
        "trust-status" | "trust-revoke" => publisher && !package_token && !plugin_id,
        _ => false,
    };
    valid.then_some(request)
}

#[derive(Serialize)]
#[serde(tag = "status", rename_all = "kebab-case")]
pub(crate) enum PluginActionOutcome {
    Ok { value: Value },
    Cancelled,
    Unavailable,
    Failed,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct CorePackageReview {
    package_token: String,
    review: CorePackageDetails,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct CorePackageDetails {
    plugin_id: String,
    plugin_version: String,
    publisher_key_id: String,
    package_sha256: String,
    manifest_sha256: String,
    permissions: Vec<String>,
    destinations: Vec<CoreDestination>,
    operations: Vec<String>,
    data_classes: Vec<String>,
    credential_scopes: Vec<String>,
    trust_status: String,
    runtime_status: String,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct CoreDestination {
    scheme: String,
    host: String,
    port: u16,
    path_template: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct CoreGrantStatus {
    plugin_id: String,
    status: String,
    revision: Option<u64>,
    package_sha256: Option<String>,
}

fn read_plugin_core(
    connection: &NativeImportConnection,
    action: NativePluginAction,
    body: Value,
) -> Option<Value> {
    let response = connection.plugin_request(action, body).ok()?;
    if response.status != 200
        || response.content_type != "application/json"
        || response.body.len() > MAX_RESPONSE_BYTES
        || !connection.is_current()
    {
        return None;
    }
    serde_json::from_str(&response.body).ok()
}

fn visible(value: &str) -> String {
    value.chars().flat_map(char::escape_default).collect()
}

fn lines(values: &[String]) -> String {
    if values.is_empty() {
        "none".to_owned()
    } else {
        values
            .iter()
            .map(|value| visible(value))
            .collect::<Vec<_>>()
            .join(", ")
    }
}

fn native_enable_decision(
    project_id: &str,
    token: &str,
    package_value: Value,
    trust_value: Value,
    grant_value: Value,
) -> Option<(Value, String)> {
    let package: CorePackageReview = serde_json::from_value(package_value).ok()?;
    let trust: TrustStatus = serde_json::from_value(trust_value).ok()?;
    let grant: CoreGrantStatus = serde_json::from_value(grant_value).ok()?;
    let review = package.review;
    let key_sha = trust.public_key_sha256.as_deref()?;
    if package.package_token != token
        || review.trust_status != "active"
        || review.runtime_status != "ready"
        || trust.status != "active"
        || trust.publisher_key_id != review.publisher_key_id
        || trust.revision.is_none_or(|revision| revision == 0)
        || !key_sha.starts_with("sha256:")
        || !hex(&key_sha[7..], 64)
        || grant.plugin_id != review.plugin_id
        || !matches!(grant.status.as_str(), "enabled" | "disabled")
        || !review.package_sha256.starts_with("sha256:")
        || !hex(&review.package_sha256[7..], 64)
        || !review.manifest_sha256.starts_with("sha256:")
        || !hex(&review.manifest_sha256[7..], 64)
        || review
            .destinations
            .iter()
            .any(|destination| destination.scheme != "https")
    {
        return None;
    }
    let destinations = review
        .destinations
        .iter()
        .map(|destination| {
            format!(
                "https://{}:{}{}",
                visible(&destination.host),
                destination.port,
                visible(&destination.path_template)
            )
        })
        .collect::<Vec<_>>();
    let message = format!(
        "Enable this exact connector package for project {project_id}?\n\nPlugin: {} version {}\nPublisher: {}\nTrusted key: {key_sha}\nPackage: {}\nManifest: {}\nOperations: {}\nPermissions: {}\nDestinations: {}\nData classes: {}\nCredential scopes: {}\n\nThis grants only this project. Each later request still needs current rights, privacy policy and separate egress consent. No request is sent now.",
        visible(&review.plugin_id),
        visible(&review.plugin_version),
        visible(&review.publisher_key_id),
        review.package_sha256,
        review.manifest_sha256,
        lines(&review.operations),
        lines(&review.permissions),
        destinations.join(", "),
        lines(&review.data_classes),
        lines(&review.credential_scopes)
    );
    if message.encode_utf16().count() > 8192 {
        return None;
    }
    let confirmation = json!({
        "actionId": new_action_id().ok()?, "projectId": project_id,
        "pluginId": review.plugin_id, "pluginVersion": review.plugin_version,
        "publisherKeyId": review.publisher_key_id, "trustedKeySha256": key_sha,
        "trustedKeyRevision": trust.revision?, "packageSha256": review.package_sha256,
        "manifestSha256": review.manifest_sha256, "permissions": review.permissions,
        "destinations": review.destinations, "operations": review.operations,
        "dataClasses": review.data_classes, "credentialScopes": review.credential_scopes,
        "expectedRevision": grant.revision,
    });
    Some((confirmation, message))
}

fn native_confirm(owner: isize, title: &str, message: &str) -> bool {
    #[cfg(windows)]
    {
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            IDYES, MB_DEFBUTTON2, MB_ICONWARNING, MB_YESNO, MessageBoxW,
        };
        let title: Vec<u16> = title.encode_utf16().chain(Some(0)).collect();
        let message: Vec<u16> = message.encode_utf16().chain(Some(0)).collect();
        unsafe {
            MessageBoxW(
                owner as _,
                message.as_ptr(),
                title.as_ptr(),
                MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2,
            ) == IDYES
        }
    }
    #[cfg(not(windows))]
    {
        let _ = (owner, title, message);
        false
    }
}

pub(crate) fn perform_action(
    supervisor: RuntimeSupervisor,
    lock: ApplicationLockManager,
    ticket: u64,
    owner: isize,
    request: PluginActionRequest,
) -> PluginActionOutcome {
    if lock.finish_protected_action(ticket).is_err() {
        return PluginActionOutcome::Cancelled;
    }
    let Ok(connection) = supervisor.native_import_connection(&request.root, &request.project_id)
    else {
        return PluginActionOutcome::Unavailable;
    };
    let address = json!({"root":request.root,"projectId":request.project_id});
    let Ok(context) = connection.plugin_request(NativePluginAction::Context, address.clone())
    else {
        return PluginActionOutcome::Unavailable;
    };
    if context.status != 200
        || context.content_type != "application/json"
        || context.body.len() > MAX_RESPONSE_BYTES
    {
        return PluginActionOutcome::Failed;
    }
    let Ok(context) = serde_json::from_str::<Context>(&context.body) else {
        return PluginActionOutcome::Failed;
    };
    if context.project_id != request.project_id || !hex(&context.session_id, 32) {
        return PluginActionOutcome::Failed;
    }
    let mut body = address.as_object().cloned().expect("fixed object");
    body.insert("sessionId".into(), context.session_id.into());
    let action = match request.kind.as_str() {
        "review" => {
            body.insert("packageToken".into(), request.package_token.into());
            NativePluginAction::Review
        }
        "discard" => {
            body.insert("packageToken".into(), request.package_token.into());
            NativePluginAction::Discard
        }
        "grant-status" => {
            body.insert("pluginId".into(), request.plugin_id.into());
            NativePluginAction::GrantStatus
        }
        "grant-enable" => {
            let token = request.package_token.as_deref().unwrap_or_default();
            let mut review_request = body.clone();
            review_request.insert("packageToken".into(), token.into());
            let Some(review_value) = read_plugin_core(
                &connection,
                NativePluginAction::Review,
                Value::Object(review_request),
            ) else {
                return PluginActionOutcome::Failed;
            };
            let Ok(review) = serde_json::from_value::<CorePackageReview>(review_value.clone())
            else {
                return PluginActionOutcome::Failed;
            };
            let mut trust_request = body.clone();
            trust_request.insert(
                "publisherKeyId".into(),
                review.review.publisher_key_id.clone().into(),
            );
            let Some(trust_value) = read_plugin_core(
                &connection,
                NativePluginAction::TrustStatus,
                Value::Object(trust_request),
            ) else {
                return PluginActionOutcome::Failed;
            };
            let mut grant_request = body.clone();
            grant_request.insert("pluginId".into(), review.review.plugin_id.clone().into());
            let Some(grant_value) = read_plugin_core(
                &connection,
                NativePluginAction::GrantStatus,
                Value::Object(grant_request),
            ) else {
                return PluginActionOutcome::Failed;
            };
            let Some((confirmation, message)) = native_enable_decision(
                &request.project_id,
                token,
                review_value,
                trust_value,
                grant_value,
            ) else {
                return PluginActionOutcome::Failed;
            };
            if lock.finish_protected_action(ticket).is_err() || !connection.is_current() {
                return PluginActionOutcome::Cancelled;
            }
            if !native_confirm(owner, "Enable connector for this project", &message) {
                return PluginActionOutcome::Cancelled;
            }
            if lock.finish_protected_action(ticket).is_err() || !connection.is_current() {
                return PluginActionOutcome::Cancelled;
            }
            body.insert("packageToken".into(), token.into());
            body.insert("confirmation".into(), confirmation);
            NativePluginAction::GrantEnable
        }
        "grant-revoke" => {
            let plugin_id = request.plugin_id.as_deref().unwrap_or_default();
            let mut status_request = body.clone();
            status_request.insert("pluginId".into(), plugin_id.into());
            let Some(status_value) = read_plugin_core(
                &connection,
                NativePluginAction::GrantStatus,
                Value::Object(status_request),
            ) else {
                return PluginActionOutcome::Failed;
            };
            let Ok(status) = serde_json::from_value::<CoreGrantStatus>(status_value) else {
                return PluginActionOutcome::Failed;
            };
            let Some(revision) = status.revision.filter(|value| *value >= 1) else {
                return PluginActionOutcome::Failed;
            };
            let Some(package_sha) = status.package_sha256.as_deref() else {
                return PluginActionOutcome::Failed;
            };
            if status.plugin_id != plugin_id
                || status.status != "enabled"
                || !package_sha.starts_with("sha256:")
                || !hex(&package_sha[7..], 64)
            {
                return PluginActionOutcome::Failed;
            }
            let message = format!(
                "Disable connector {} in project {}?\n\nCurrent package: {}\n\nNew requests will stop. In-flight work may continue until its next authority check or timeout, but cannot publish after disabling. Imported evidence and provenance remain.",
                visible(plugin_id),
                request.project_id,
                package_sha
            );
            if lock.finish_protected_action(ticket).is_err() || !connection.is_current() {
                return PluginActionOutcome::Cancelled;
            }
            if !native_confirm(owner, "Disable connector for this project", &message) {
                return PluginActionOutcome::Cancelled;
            }
            if lock.finish_protected_action(ticket).is_err() || !connection.is_current() {
                return PluginActionOutcome::Cancelled;
            }
            let Ok(action_id) = new_action_id() else {
                return PluginActionOutcome::Failed;
            };
            body.insert("pluginId".into(), plugin_id.into());
            body.insert("expectedRevision".into(), revision.into());
            body.insert("actionId".into(), action_id.into());
            NativePluginAction::GrantRevoke
        }
        "trust-status" => {
            body.insert("publisherKeyId".into(), request.publisher_key_id.into());
            NativePluginAction::TrustStatus
        }
        "trust-revoke" => {
            let publisher = request.publisher_key_id.as_deref().unwrap_or_default();
            let mut status_request = body.clone();
            status_request.insert("publisherKeyId".into(), publisher.into());
            let Some(status_value) = read_plugin_core(
                &connection,
                NativePluginAction::TrustStatus,
                Value::Object(status_request),
            ) else {
                return PluginActionOutcome::Failed;
            };
            let Ok(status) = serde_json::from_value::<TrustStatus>(status_value) else {
                return PluginActionOutcome::Failed;
            };
            let Some(revision) = status.revision.filter(|value| *value >= 1) else {
                return PluginActionOutcome::Failed;
            };
            let Some(key_sha) = status.public_key_sha256.as_deref() else {
                return PluginActionOutcome::Failed;
            };
            if status.publisher_key_id != publisher
                || status.status != "active"
                || !key_sha.starts_with("sha256:")
                || !hex(&key_sha[7..], 64)
            {
                return PluginActionOutcome::Failed;
            }
            let message = format!(
                "Remove local trust for publisher {}?\n\nTrusted key: {}\n\nThis affects dependent connector packages across every project. New execution will be denied; imported evidence remains.",
                visible(publisher),
                key_sha
            );
            if lock.finish_protected_action(ticket).is_err() || !connection.is_current() {
                return PluginActionOutcome::Cancelled;
            }
            if !native_confirm(owner, "Remove connector publisher trust", &message) {
                return PluginActionOutcome::Cancelled;
            }
            if lock.finish_protected_action(ticket).is_err() || !connection.is_current() {
                return PluginActionOutcome::Cancelled;
            }
            let Ok(action_id) = new_action_id() else {
                return PluginActionOutcome::Failed;
            };
            body.insert("publisherKeyId".into(), publisher.into());
            body.insert("expectedRevision".into(), revision.into());
            body.insert("publicKeySha256".into(), key_sha.into());
            body.insert("actionId".into(), action_id.into());
            body.insert("publicKeyHex".into(), Value::Null);
            body.insert("previousKeySha256".into(), Value::Null);
            body.insert("operation".into(), "revoke".into());
            NativePluginAction::TrustDecide
        }
        _ => return PluginActionOutcome::Failed,
    };
    let Ok(response) = connection.plugin_request(action, Value::Object(body)) else {
        return PluginActionOutcome::Unavailable;
    };
    if lock.finish_protected_action(ticket).is_err() || !connection.is_current() {
        // Core may already have committed. Never imply that cancellation
        // preserved the old configuration after a request was dispatched.
        return PluginActionOutcome::Failed;
    }
    if response.status != 200
        || response.content_type != "application/json"
        || response.body.len() > MAX_RESPONSE_BYTES
    {
        return PluginActionOutcome::Failed;
    }
    match serde_json::from_str(&response.body) {
        Ok(value) => PluginActionOutcome::Ok { value },
        Err(_) => PluginActionOutcome::Failed,
    }
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct PluginTrustRequest {
    root: String,
    project_id: String,
    operation_id: String,
    publisher_key_id: String,
}

pub(crate) fn decode_trust_request(payload: &Value) -> Option<PluginTrustRequest> {
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Envelope {
        request: PluginTrustRequest,
    }
    let request = serde_json::from_value::<Envelope>(payload.clone())
        .ok()?
        .request;
    (crate::directory_picker::local_path_syntax(&request.root)
        && crate::supervisor::canonical_project_id(&request.project_id)
        && hex(&request.operation_id, 32)
        && !request.publisher_key_id.is_empty()
        && request.publisher_key_id.len() <= 128
        && request.publisher_key_id.bytes().all(|value| {
            value.is_ascii_alphanumeric() || matches!(value, b'.' | b'_' | b':' | b'-')
        }))
    .then_some(request)
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct TrustStatus {
    publisher_key_id: String,
    status: String,
    revision: Option<u64>,
    public_key_sha256: Option<String>,
}

#[cfg(windows)]
fn confirm_native_trust(owner: isize, publisher: &str, fingerprint: &str, replacing: bool) -> bool {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        IDYES, MB_DEFBUTTON2, MB_ICONWARNING, MB_YESNO, MessageBoxW,
    };
    let effect = if replacing {
        "This replaces a previously revoked key for this publisher."
    } else {
        "This trusts the selected publisher key on this computer."
    };
    let message = format!(
        "Publisher: {publisher}\nKey SHA-256: {fingerprint}\n\n{effect}\n\nA valid signature identifies a publisher; it does not make a connector safe or enable it for a project. Trust this key?"
    );
    let message: Vec<u16> = message.encode_utf16().chain(Some(0)).collect();
    let title: Vec<u16> = "Review connector publisher trust"
        .encode_utf16()
        .chain(Some(0))
        .collect();
    unsafe {
        MessageBoxW(
            owner as _,
            message.as_ptr(),
            title.as_ptr(),
            MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2,
        ) == IDYES
    }
}

#[cfg(windows)]
pub(crate) fn trust_publisher(
    manager: PluginIntakeManager,
    picker: DirectoryPickerManager,
    supervisor: RuntimeSupervisor,
    lock: ApplicationLockManager,
    ticket: u64,
    owner: isize,
    request: PluginTrustRequest,
) -> PluginActionOutcome {
    let Ok(permit) = manager.begin(&request.operation_id) else {
        return PluginActionOutcome::Unavailable;
    };
    if permit.cancelled.load(Ordering::Acquire)
        || lock.finish_protected_action(ticket).is_err()
        || !picker.is_open()
    {
        return PluginActionOutcome::Cancelled;
    }
    let Ok(connection) = supervisor.native_import_connection(&request.root, &request.project_id)
    else {
        return PluginActionOutcome::Unavailable;
    };
    let connection = Arc::new(connection);
    let address = json!({"root":request.root,"projectId":request.project_id});
    let Ok(context) = connection.plugin_request(NativePluginAction::Context, address.clone())
    else {
        return PluginActionOutcome::Unavailable;
    };
    if context.status != 200
        || context.content_type != "application/json"
        || context.body.len() > MAX_RESPONSE_BYTES
    {
        return PluginActionOutcome::Failed;
    }
    let Ok(context) = serde_json::from_str::<Context>(&context.body) else {
        return PluginActionOutcome::Failed;
    };
    if context.project_id != request.project_id || !hex(&context.session_id, 32) {
        return PluginActionOutcome::Failed;
    }
    let mut address = address;
    address["sessionId"] = context.session_id.into();
    let cancelled = Arc::clone(&permit.cancelled);
    let checking_picker = picker.clone();
    let checking_connection = Arc::clone(&connection);
    let result = picker.import_source(
        owner,
        move || {
            !cancelled.load(Ordering::Acquire)
                && checking_picker.is_open()
                && lock.finish_protected_action(ticket).is_ok()
                && checking_connection.is_current()
        },
        move |source, authorized| {
            let mut key = Vec::with_capacity(32);
            source
                .transfer(
                    || authorized(),
                    |_ordinal, chunk| {
                        if key.len() + chunk.len() > 32 {
                            return Err("RO-PLUGIN-PUBLISHER-KEY-LIMIT");
                        }
                        key.extend_from_slice(chunk);
                        Ok(())
                    },
                )
                .map_err(|_| {
                    if authorized() {
                        PickerFailure::Failed
                    } else {
                        PickerFailure::Cancelled
                    }
                })?;
            if key.len() != 32 || !authorized() {
                return Err(PickerFailure::Failed);
            }
            let fingerprint = format!("sha256:{:x}", Sha256::digest(&key));
            let mut status_request = address.clone();
            status_request["publisherKeyId"] = request.publisher_key_id.clone().into();
            let response = connection
                .plugin_request(NativePluginAction::TrustStatus, status_request)
                .map_err(|_| PickerFailure::Failed)?;
            if response.status != 200
                || response.content_type != "application/json"
                || response.body.len() > MAX_RESPONSE_BYTES
            {
                return Err(PickerFailure::Failed);
            }
            let status: TrustStatus =
                serde_json::from_str(&response.body).map_err(|_| PickerFailure::Failed)?;
            if status.publisher_key_id != request.publisher_key_id
                || !matches!(status.status.as_str(), "untrusted" | "active" | "revoked")
                || status.revision.is_some_and(|revision| revision == 0)
                || status.public_key_sha256.as_ref().is_some_and(|value| {
                    value.len() != 71 || !value.starts_with("sha256:") || !hex(&value[7..], 64)
                })
            {
                return Err(PickerFailure::Failed);
            }
            if status.status == "active" {
                return Err(PickerFailure::Failed);
            }
            let rotating = status.status == "revoked"
                && status.public_key_sha256.as_deref() != Some(fingerprint.as_str());
            if !confirm_native_trust(owner, &request.publisher_key_id, &fingerprint, rotating)
                || !authorized()
            {
                return Err(PickerFailure::Cancelled);
            }
            let action_id = new_action_id().map_err(|_| PickerFailure::Failed)?;
            let mut decision = address;
            decision["publisherKeyId"] = request.publisher_key_id.into();
            decision["publicKeyHex"] = key
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect::<String>()
                .into();
            decision["publicKeySha256"] = fingerprint.into();
            decision["expectedRevision"] = status.revision.into();
            decision["operation"] = (if rotating { "rotate" } else { "trust" }).into();
            decision["previousKeySha256"] = (if rotating {
                status.public_key_sha256
            } else {
                None
            })
            .into();
            decision["actionId"] = action_id.into();
            let response = connection
                .plugin_request(NativePluginAction::TrustDecide, decision)
                .map_err(|_| PickerFailure::Failed)?;
            if !authorized()
                || response.status != 200
                || response.content_type != "application/json"
                || response.body.len() > MAX_RESPONSE_BYTES
            {
                return Err(PickerFailure::Failed);
            }
            serde_json::from_str::<Value>(&response.body).map_err(|_| PickerFailure::Failed)
        },
    );
    match result {
        Ok(value) => PluginActionOutcome::Ok { value },
        Err(PickerFailure::Cancelled) => PluginActionOutcome::Cancelled,
        Err(PickerFailure::Unavailable) => PluginActionOutcome::Unavailable,
        Err(PickerFailure::Failed) => PluginActionOutcome::Failed,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cancellation_before_native_picker_start_is_consumed() {
        let manager = PluginIntakeManager::default();
        let picker = DirectoryPickerManager::default();
        let operation_id = "0123456789abcdef0123456789abcdef";
        manager.cancel(operation_id, &picker);
        assert!(matches!(
            manager.begin(operation_id),
            Err(PickerFailure::Cancelled)
        ));
        let permit = manager
            .begin(operation_id)
            .expect("one cancelled request cannot poison later admission");
        manager.cancel(operation_id, &picker);
        assert!(permit.cancelled.load(Ordering::Acquire));
    }

    #[test]
    fn renderer_cannot_supply_extra_authority_to_discard() {
        let request = json!({"request": {"root": "C:/Research/synthetic", "projectId": "01900000-0000-4000-8000-000000000001", "kind": "discard", "packageToken": "a".repeat(64)}});
        assert!(decode_action(&request).is_some());
        let mut extra = request;
        extra["request"]["arbitraryUrl"] = "https://example.invalid".into();
        assert!(decode_action(&extra).is_none());
        extra["request"]
            .as_object_mut()
            .expect("object")
            .remove("arbitraryUrl");
        extra["request"]["packageToken"] = "not-a-token".into();
        assert!(decode_action(&extra).is_none());
    }

    #[test]
    fn renderer_cannot_supply_human_decision_facts() {
        let address = json!({"root": "C:/Research/synthetic", "projectId": "01900000-0000-4000-8000-000000000001"});
        for (kind, identity, field, value) in [
            (
                "grant-enable",
                "packageToken",
                "confirmation",
                json!({"projectId": "forged"}),
            ),
            ("grant-revoke", "pluginId", "expectedRevision", json!(1)),
            (
                "grant-revoke",
                "pluginId",
                "actionId",
                json!("01900000-0000-7000-8000-000000000001"),
            ),
            (
                "trust-revoke",
                "publisherKeyId",
                "publicKeySha256",
                json!(format!("sha256:{}", "a".repeat(64))),
            ),
        ] {
            let mut request = address.clone();
            request["kind"] = kind.into();
            request[identity] = if identity == "packageToken" {
                "a".repeat(64).into()
            } else {
                "example.publisher".into()
            };
            assert!(decode_action(&json!({"request": request})).is_some());
            request[field] = value;
            assert!(decode_action(&json!({"request": request})).is_none());
        }
    }

    #[test]
    fn native_enable_confirmation_comes_from_current_core_identity_and_scope() {
        let project = "01900000-0000-4000-8000-000000000001";
        let token = "a".repeat(64);
        let package = json!({
            "packageToken": token, "review": {
                "pluginId": "example.repository", "pluginVersion": "1.0.0", "publisherKeyId": "example.publisher",
                "packageSha256": format!("sha256:{}", "b".repeat(64)),
                "manifestSha256": format!("sha256:{}", "c".repeat(64)),
                "permissions": ["provider-network"],
                "destinations": [{"scheme": "https", "host": "repository.example.invalid", "port": 443, "pathTemplate": "/records/{repository_id}"}],
                "operations": ["repository-metadata"], "dataClasses": ["public-metadata"],
                "credentialScopes": [], "trustStatus": "active", "runtimeStatus": "ready"
            }
        });
        let trust = json!({"publisherKeyId": "example.publisher", "status": "active", "revision": 2,
            "publicKeySha256": format!("sha256:{}", "d".repeat(64))});
        let grant = json!({"pluginId": "example.repository", "status": "disabled", "revision": 3,
            "packageSha256": null});
        let (confirmation, message) = native_enable_decision(
            project,
            &token,
            package.clone(),
            trust.clone(),
            grant.clone(),
        )
        .expect("trusted Core review");
        assert_eq!(confirmation["projectId"], project);
        assert_eq!(confirmation["expectedRevision"], 3);
        assert_eq!(confirmation["trustedKeyRevision"], 2);
        assert_eq!(
            confirmation["destinations"],
            package["review"]["destinations"]
        );
        assert!(message.contains("repository.example.invalid:443/records/{repository_id}"));
        assert!(message.contains(&format!("sha256:{}", "b".repeat(64))));
        let mut forged = package.clone();
        forged["packageToken"] = "e".repeat(64).into();
        assert!(
            native_enable_decision(project, &token, forged, trust.clone(), grant.clone()).is_none()
        );
        let mut revoked = trust.clone();
        revoked["status"] = "revoked".into();
        assert!(
            native_enable_decision(project, &token, package.clone(), revoked, grant.clone())
                .is_none()
        );
        let mut other_plugin = grant;
        other_plugin["pluginId"] = "other.repository".into();
        assert!(native_enable_decision(project, &token, package, trust, other_plugin).is_none());
    }
}
