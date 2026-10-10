//! Purpose-specific Reader broker. Renderer supplies opaque selection only;
//! Native owns destinations, current authority and every physical operation.

#[cfg(all(test, feature = "integration-harness"))]
#[path = "viewer_actions/windows_integration_tests.rs"]
mod windows_integration_tests;

use crate::application_lock::ApplicationLockManager;
use crate::directory_picker::{DirectoryPickerManager, PickerFailure};
use crate::document_runtime::current_document_context;
use crate::document_viewer::{ViewerSelector, ViewerSourceRequest, metadata_matches};
use crate::supervisor::{NativeDocumentAction, NativeImportConnection, RuntimeSupervisor};
use crate::viewer_export::{FAILED, LocalDeliverable};
use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tauri::State;

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq, Debug)]
#[serde(rename_all = "kebab-case")]
pub(crate) enum ReaderAction {
    CopyQuotation,
    PrintQuotation,
    ExportQuotation,
    ExportAnnotation,
    OpenExternalOriginal,
}

#[derive(Clone, Copy, Deserialize, PartialEq)]
#[serde(rename_all = "kebab-case")]
enum ActionStage {
    Policy,
    DeniedAttempt,
    RightsReview,
    Execute,
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ReaderActionRequest {
    schema_version: String,
    project_id: String,
    selector: ViewerSelector,
    operation_id: String,
    stage: ActionStage,
    action: ReaderAction,
    anchor_id: Option<String>,
    expected_policy_revision_id: Option<String>,
    command_id: Option<String>,
    #[serde(default)]
    confirmed: bool,
}

impl ReaderActionRequest {
    fn valid(&self) -> bool {
        self.schema_version == "1.0"
            && crate::supervisor::canonical_project_id(&self.project_id)
            && self.selector.valid()
            && uuid(&self.operation_id)
            && self.anchor_id.as_ref().is_none_or(|id| uuid(id))
            && self
                .expected_policy_revision_id
                .as_ref()
                .is_none_or(|id| uuid(id))
            && (self.action != ReaderAction::OpenExternalOriginal || self.anchor_id.is_none())
            && match self.stage {
                ActionStage::Policy | ActionStage::DeniedAttempt => {
                    self.command_id.is_none() && !self.confirmed
                }
                ActionStage::RightsReview => {
                    self.command_id.as_ref().is_some_and(|id| uuid(id))
                        && self.confirmed
                        && self.anchor_id.is_none()
                }
                ActionStage::Execute => {
                    self.expected_policy_revision_id.is_some()
                        && self.command_id.is_none()
                        && self.confirmed
                }
            }
    }
    fn source(&self) -> ViewerSourceRequest {
        ViewerSourceRequest {
            schema_version: self.schema_version.clone(),
            project_id: self.project_id.clone(),
            selector: self.selector.clone(),
        }
    }
}

fn uuid(id: &str) -> bool {
    crate::supervisor::canonical_uuid_v7(id)
}
fn digest(id: &str) -> bool {
    id.len() == 64
        && id
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn code(value: &Value) -> bool {
    value.as_str().is_some_and(|s| {
        !s.is_empty()
            && s.len() <= 120
            && s.bytes()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-')
    })
}
fn exact(value: &Value, keys: &[&str]) -> bool {
    value
        .as_object()
        .is_some_and(|m| m.len() == keys.len() && keys.iter().all(|k| m.contains_key(*k)))
}
fn uses(action: ReaderAction) -> Vec<Value> {
    let mut result = vec![
        json!({"action":"inspect","purpose":"document-analysis","destinationKind":"local-project"}),
    ];
    if action != ReaderAction::OpenExternalOriginal {
        result.push(json!({"action":"derive","purpose":"document-analysis","destinationKind":"local-project"}));
    }
    if matches!(
        action,
        ReaderAction::CopyQuotation | ReaderAction::PrintQuotation | ReaderAction::ExportQuotation
    ) {
        result.push(json!({"action":"quote","purpose":"viewer-quotation","destinationKind":"local-project"}));
    }
    result.push(json!({"action":"export","purpose":format!("viewer-{}",json!(action).as_str().unwrap_or("invalid")),"destinationKind":"local-export"}));
    for value in &mut result {
        let fields = value.as_object_mut().expect("fixed local use");
        for field in ["provider", "region", "shareGroup"] {
            fields.insert(field.into(), Value::Null);
        }
    }
    result
}
fn basis_matches(value: &Value, action: ReaderAction, ready: bool) -> bool {
    let fixed = uses(action);
    value.as_array().is_some_and(|a| {
        a.len() == fixed.len()
            && a.iter().zip(fixed.iter()).all(|(v, u)| {
                exact(v, &["use", "code", "reasonCode"])
                    && &v["use"] == u
                    && code(&v["reasonCode"])
                    && matches!(
                        v["code"].as_str(),
                        Some("allow" | "deny" | "unknown" | "require-confirmation")
                    )
                    && (!ready
                        || v["code"] == "allow"
                        || u["destinationKind"] == "local-export"
                            && v["code"] == "require-confirmation"
                            && v["reasonCode"] == "rights-further-authority-required")
            })
    })
}
fn position(value: &Value) -> Option<(u64, u64)> {
    if !exact(value, &["start", "end"]) {
        return None;
    }
    let start = value["start"].as_u64()?;
    let end = value["end"].as_u64()?;
    (start <= end && end <= (1u64 << 53) - 1).then_some((start, end))
}
fn annotation_valid(value: &Value) -> bool {
    if !value["nodeId"].as_str().is_some_and(uuid)
        || !matches!(
            value["nodeKind"].as_str(),
            Some(
                "region"
                    | "title"
                    | "abstract"
                    | "section"
                    | "paragraph"
                    | "sentence"
                    | "list"
                    | "list-item"
                    | "footnote"
                    | "reference"
                    | "citation-marker"
                    | "table"
                    | "table-cell"
                    | "figure"
                    | "caption"
                    | "equation"
                    | "unknown"
            )
        )
        || !value["textPosition"].is_null() && position(&value["textPosition"]).is_none()
    {
        return false;
    }
    let confidence = &value["confidence"];
    if !exact(confidence, &["state", "value"])
        || !matches!(
            confidence["state"].as_str(),
            Some("reported" | "unknown" | "not-reported" | "not-applicable" | "unavailable")
        )
        || if confidence["state"] == "reported" {
            !confidence["value"]
                .as_f64()
                .is_some_and(|v| v.is_finite() && (0.0..=1.0).contains(&v))
        } else {
            !confidence["value"].is_null()
        }
    {
        return false;
    }
    let region = &value["pageRegion"];
    let available = value["coordinatesState"] == "available";
    if !matches!(
        value["coordinatesState"].as_str(),
        Some(
            "available"
                | "not-reported"
                | "format-has-no-pages"
                | "unsupported-location"
                | "parser-unavailable"
        )
    ) || available == region.is_null()
    {
        return false;
    }
    if !available {
        return true;
    }
    exact(
        region,
        &[
            "pageIndex",
            "pageNumber",
            "x0",
            "y0",
            "x1",
            "y1",
            "sourceWidth",
            "sourceHeight",
            "rotation",
            "frame",
            "origin",
            "unit",
            "granularity",
        ],
    ) && region["pageIndex"]
        .as_u64()
        .is_some_and(|i| i < 500 && region["pageNumber"].as_u64() == Some(i + 1))
        && ["x0", "x1", "y0", "y1"].iter().all(|k| {
            region[*k]
                .as_f64()
                .is_some_and(|v| v.is_finite() && (0.0..=1.0).contains(&v))
        })
        && region["x0"].as_f64() <= region["x1"].as_f64()
        && region["y0"].as_f64() <= region["y1"].as_f64()
        && ["sourceWidth", "sourceHeight"].iter().all(|k| {
            region[*k]
                .as_f64()
                .is_some_and(|v| v.is_finite() && v > 0.0)
        })
        && matches!(region["rotation"].as_u64(), Some(0 | 90 | 180 | 270))
        && region["frame"] == "unrotated-source-page"
        && region["origin"] == "top-left"
        && region["unit"] == "normalized"
        && region["granularity"] == "block"
}

fn frame_id() -> Result<String, &'static str> {
    let mut bytes = [0u8; 16];
    crate::supervisor::fill_secure_random(&mut bytes)?;
    let millis = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| FAILED)?
        .as_millis();
    if millis > 0xffff_ffff_ffff {
        return Err(FAILED);
    }
    bytes[..6].copy_from_slice(&(millis as u64).to_be_bytes()[2..]);
    bytes[6] = (bytes[6] & 0x0f) | 0x70;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    let hex: String = bytes.iter().map(|b| format!("{b:02x}")).collect();
    Ok(format!(
        "{}-{}-{}-{}-{}",
        &hex[..8],
        &hex[8..12],
        &hex[12..16],
        &hex[16..20],
        &hex[20..]
    ))
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ReaderActionOutcome {
    schema_version: &'static str,
    project_id: String,
    operation_id: String,
    action: ReaderAction,
    status: &'static str,
    drained: bool,
    decision: Option<Value>,
    review: Option<Value>,
}

struct ActiveAction {
    project: String,
    operation: String,
    owner: isize,
    connection: Arc<NativeImportConnection>,
    cancelled: AtomicBool,
    closed: AtomicBool,
    delivered: AtomicBool,
    // Retained until a complete response or exact Core terminal acknowledgement.
    // Absence of a response does not release physical Core ownership.
    core_frame: Mutex<Option<(String, String)>>,
}

#[derive(Default)]
struct ActionOwners {
    active: Option<Arc<ActiveAction>>,
    terminal: VecDeque<(String, String)>,
    early: VecDeque<(String, String, isize)>,
    exhausted: bool,
}
#[derive(Clone, Default)]
pub(crate) struct ViewerActionManager(Arc<Mutex<ActionOwners>>);

struct OwnedAction {
    manager: ViewerActionManager,
    active: Arc<ActiveAction>,
}
impl Drop for OwnedAction {
    fn drop(&mut self) {
        self.active.closed.store(true, Ordering::Release);
        self.manager.release_closed(&self.active);
    }
}

impl ViewerActionManager {
    fn begin(
        &self,
        request: &ReaderActionRequest,
        owner: isize,
        connection: Arc<NativeImportConnection>,
    ) -> Result<OwnedAction, &'static str> {
        let mut state = self.0.lock().map_err(|_| FAILED)?;
        let key = (request.project_id.clone(), request.operation_id.clone());
        if state.exhausted || state.active.is_some() || state.terminal.contains(&key) {
            return Err(FAILED);
        }
        let cancelled = state
            .early
            .iter()
            .position(|(p, o, w)| p == &key.0 && o == &key.1 && *w == owner);
        if let Some(index) = cancelled {
            state.early.remove(index);
        }
        let active = Arc::new(ActiveAction {
            project: key.0,
            operation: key.1,
            owner,
            connection,
            cancelled: AtomicBool::new(cancelled.is_some()),
            closed: AtomicBool::new(false),
            delivered: AtomicBool::new(false),
            core_frame: Mutex::new(None),
        });
        state.active = Some(Arc::clone(&active));
        Ok(OwnedAction {
            manager: self.clone(),
            active,
        })
    }
    fn release_closed(&self, active: &Arc<ActiveAction>) -> bool {
        if !active.closed.load(Ordering::Acquire) {
            return false;
        }
        // This flag is set only by child.wait/try_wait observing actual exit,
        // and is tied to this connection's exact process, not a later restart.
        if active.connection.core_physically_closed() {
            if let Ok(mut frame) = active.core_frame.lock() {
                *frame = None;
            }
        }
        if active
            .core_frame
            .lock()
            .map_or(true, |frame| frame.is_some())
        {
            return false;
        }
        let Ok(mut state) = self.0.lock() else {
            return false;
        };
        if state
            .active
            .as_ref()
            .is_some_and(|a| Arc::ptr_eq(a, active))
        {
            state.active = None;
            state
                .terminal
                .push_back((active.project.clone(), active.operation.clone()));
            while state.terminal.len() > 256 {
                state.terminal.pop_front();
            }
        }
        true
    }
    fn cancel(&self, project: &str, operation: &str, owner: isize) -> bool {
        let Ok(mut state) = self.0.lock() else {
            return false;
        };
        let key = (project.to_owned(), operation.to_owned());
        if state.terminal.contains(&key) {
            return true;
        }
        let Some(active) = state
            .active
            .as_ref()
            .filter(|a| a.project == project && a.operation == operation && a.owner == owner)
            .cloned()
        else {
            if state
                .active
                .as_ref()
                .is_some_and(|a| a.project == project && a.operation == operation)
            {
                return false;
            }
            let early = (project.to_owned(), operation.to_owned(), owner);
            if !state.early.contains(&early) {
                if state.early.len() >= 256 {
                    state.exhausted = true;
                } else {
                    state.early.push_back(early);
                }
            }
            return false;
        };
        active.cancelled.store(true, Ordering::Release);
        drop(state);
        cancel_frame(&active);
        self.release_closed(&active)
    }
    pub(crate) fn cancel_all(&self) {
        if let Ok(state) = self.0.lock() {
            if let Some(active) = &state.active {
                active.cancelled.store(true, Ordering::Release);
            }
        }
    }
    pub(crate) fn reconcile_closed(&self) {
        if let Some(active) = self.0.lock().ok().and_then(|s| s.active.clone()) {
            self.release_closed(&active);
        }
    }
    pub(crate) fn wait_for_cleanup(&self) {
        // Called only from a blocking lifecycle worker, after Core stop. A
        // terminal flag is not proof that a Native callback or Core process ended.
        loop {
            let active = self.0.lock().ok().and_then(|s| s.active.clone());
            let Some(active) = active else {
                return;
            };
            if self.release_closed(&active) {
                return;
            }
            std::thread::sleep(std::time::Duration::from_millis(20));
        }
    }
    fn unissued_drained(&self, request: &ReaderActionRequest) -> bool {
        self.0.lock().is_ok_and(|state| {
            state.active.as_ref().is_none_or(|a| {
                a.project != request.project_id || a.operation != request.operation_id
            })
        })
    }
}

fn cancel_frame(active: &ActiveAction) -> bool {
    let Ok(frame) = active.core_frame.lock().map(|f| f.clone()) else {
        return false;
    };
    let Some((session, request)) = frame else {
        return true;
    };
    let reply = active.connection.document_request(NativeDocumentAction::ViewerCancel,
        json!({"root":active.connection.document_root(), "projectId":active.project, "sessionId":session, "requestId":request}));
    let drained = reply.is_ok_and(|r| {
        r.status == 200
            && r.content_type == "application/json"
            && r.body.len() <= 1024
            && serde_json::from_str::<Value>(&r.body).is_ok_and(|v| {
                v.as_object().is_some_and(|m| m.len() == 5)
                    && v["schemaVersion"] == "1.0"
                    && v["projectId"] == active.project
                    && v["sessionId"] == session
                    && v["requestId"] == request
                    && v["drained"] == true
            })
    });
    if drained {
        if let Ok(mut pending) = active.core_frame.lock() {
            if pending.as_ref() == Some(&(session, request)) {
                *pending = None;
            }
        }
    }
    drained
}

fn rpc(
    active: &ActiveAction,
    action: NativeDocumentAction,
    mut body: Value,
    current: &dyn Fn() -> bool,
) -> Result<Value, &'static str> {
    if !current() || active.core_frame.lock().map_or(true, |f| f.is_some()) {
        return Err(FAILED);
    }
    let context =
        current_document_context(&active.connection, &active.project).map_err(|_| FAILED)?;
    let id = frame_id()?;
    let fields = body.as_object_mut().ok_or(FAILED)?;
    fields.insert("root".into(), active.connection.document_root().into());
    fields.insert("projectId".into(), active.project.clone().into());
    fields.insert("sessionId".into(), context.session_id.clone().into());
    fields.insert("requestId".into(), id.clone().into());
    *active.core_frame.lock().map_err(|_| FAILED)? = Some((context.session_id, id.clone()));
    let result = active
        .connection
        .document_request_owned(action, body, current);
    match result {
        Ok(response) => {
            // A fully received synchronous reply follows actual Core closure,
            // including a denial. A transport failure needs a terminal receipt.
            *active.core_frame.lock().map_err(|_| FAILED)? = None;
            if !current()
                || response.status != 200
                || response.content_type != "application/json"
                || response.body.len() > 1_406_296
            {
                return Err(FAILED);
            }
            let value: Value = serde_json::from_str(&response.body).map_err(|_| FAILED)?;
            if matches!(action, NativeDocumentAction::ViewerRange) && value["requestId"] != id {
                return Err(FAILED);
            }
            Ok(value)
        }
        Err(_) => {
            cancel_frame(active);
            Err(FAILED)
        }
    }
}

fn policy_matches(value: &Value, request: &ReaderActionRequest) -> bool {
    value.as_object().is_some_and(|m| {
        m.len() == 10
            && [
                "schemaVersion",
                "metadata",
                "action",
                "anchorId",
                "policyRevisionId",
                "state",
                "reasonCode",
                "canReview",
                "requirements",
                "selectionLimitCodepoints",
            ]
            .iter()
            .all(|k| m.contains_key(*k))
    }) && value["schemaVersion"] == "1.0"
        && value["action"] == json!(request.action)
        && value["anchorId"] == json!(request.anchor_id)
        && metadata_matches(&value["metadata"], &request.source())
        && (value["policyRevisionId"].is_null()
            || value["policyRevisionId"].as_str().is_some_and(uuid))
        && matches!(
            value["state"].as_str(),
            Some("ready" | "review-required" | "denied" | "unavailable")
        )
        && value["reasonCode"].as_str().is_some_and(|s| {
            !s.is_empty()
                && s.len() <= 120
                && s.bytes()
                    .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-')
        })
        && value["canReview"].is_boolean()
        && (value["canReview"] != true || value["state"] == "review-required")
        && value["selectionLimitCodepoints"] == 2048
        && basis_matches(
            &value["requirements"],
            request.action,
            value["state"] == "ready",
        )
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Payload {
    schema_version: String,
    metadata: Value,
    action: ReaderAction,
    anchor_id: Option<String>,
    anchor_revision_id: Option<String>,
    policy_revision_id: String,
    authority_sha256: String,
    content_sha256: String,
    content_utf8: String,
}

impl Payload {
    fn decode(value: Value, request: &ReaderActionRequest) -> Result<Self, &'static str> {
        let payload: Self = serde_json::from_value(value).map_err(|_| FAILED)?;
        if payload.schema_version != "1.0"
            || payload.action != request.action
            || payload.anchor_id != request.anchor_id
            || Some(&payload.policy_revision_id) != request.expected_policy_revision_id.as_ref()
            || !metadata_matches(&payload.metadata, &request.source())
            || !digest(&payload.authority_sha256)
            || !digest(&payload.content_sha256)
            || payload.content_utf8.len() > 65536
            || format!("{:x}", Sha256::digest(payload.content_utf8.as_bytes()))
                != payload.content_sha256
        {
            return Err(FAILED);
        }
        let content: Value = serde_json::from_str(&payload.content_utf8).map_err(|_| FAILED)?;
        let common = [
            "schemaVersion",
            "action",
            "source",
            "normalizedRevisionId",
            "policyRevisionId",
            "scholarlyVerification",
            "policyBasis",
        ];
        let quotation = [
            "text",
            "anchorId",
            "anchorRevisionId",
            "textPosition",
            "citationMetadata",
        ];
        let annotation = [
            "anchorId",
            "anchorRevisionId",
            "nodeId",
            "nodeKind",
            "textPosition",
            "pageRegion",
            "confidence",
            "coordinatesState",
        ];
        let keys: Vec<_> = common
            .into_iter()
            .chain(
                match payload.action {
                    ReaderAction::CopyQuotation
                    | ReaderAction::PrintQuotation
                    | ReaderAction::ExportQuotation => quotation.as_slice(),
                    ReaderAction::ExportAnnotation => annotation.as_slice(),
                    ReaderAction::OpenExternalOriginal => &[],
                }
                .iter()
                .copied(),
            )
            .collect();
        if !content
            .as_object()
            .is_some_and(|m| m.len() == keys.len() && keys.iter().all(|k| m.contains_key(*k)))
            || content["schemaVersion"] != "1.0"
            || content["action"] != json!(payload.action)
            || content["source"] != payload.metadata["source"]
            || content["normalizedRevisionId"] != payload.metadata["normalizedRevisionId"]
            || content["policyRevisionId"] != payload.policy_revision_id
            || content["scholarlyVerification"] != "unverified"
            || !basis_matches(&content["policyBasis"], payload.action, true)
        {
            return Err(FAILED);
        }
        if payload.action != ReaderAction::OpenExternalOriginal {
            if payload
                .anchor_revision_id
                .as_ref()
                .is_none_or(|id| !uuid(id))
                || content["anchorId"] != json!(payload.anchor_id)
                || content["anchorRevisionId"] != json!(payload.anchor_revision_id)
            {
                return Err(FAILED);
            }
        } else if payload.anchor_id.is_some() || payload.anchor_revision_id.is_some() {
            return Err(FAILED);
        }
        if matches!(
            payload.action,
            ReaderAction::CopyQuotation
                | ReaderAction::PrintQuotation
                | ReaderAction::ExportQuotation
        ) {
            let text = content["text"].as_str().ok_or(FAILED)?;
            if text.is_empty()
                || text.chars().count() > 2048
                || text.contains('\0')
                || content["citationMetadata"]["projectId"] != request.project_id
                || content["citationMetadata"]["revisionId"]
                    != payload.metadata["normalizedRevisionId"]
                || content["citationMetadata"]["documentId"]
                    != payload.metadata["source"]["documentId"]
                || !exact(
                    &content["citationMetadata"],
                    &[
                        "projectId",
                        "documentId",
                        "revisionId",
                        "acceptedAt",
                        "displayLabel",
                        "labelOrigin",
                    ],
                )
                || !content["citationMetadata"]["acceptedAt"]
                    .as_str()
                    .is_some_and(|s| s.len() <= 40 && s.ends_with('Z'))
                || !content["citationMetadata"]["displayLabel"]
                    .as_str()
                    .is_some_and(|s| s.chars().count() <= 512 && !s.contains('\0'))
                || content["citationMetadata"]["labelOrigin"] != "canonical-document-revision"
                || !position(&content["textPosition"])
                    .is_some_and(|(start, end)| end - start == text.chars().count() as u64)
            {
                return Err(FAILED);
            }
        }
        if payload.action == ReaderAction::ExportAnnotation && !annotation_valid(&content) {
            return Err(FAILED);
        }
        Ok(payload)
    }
}

fn payload(
    active: &ActiveAction,
    request: &ReaderActionRequest,
    authority: Option<&str>,
    current: &dyn Fn() -> bool,
) -> Result<Payload, &'static str> {
    let value = rpc(
        active,
        NativeDocumentAction::ViewerActionPayload,
        json!({"selector":request.selector,"action":request.action,"anchorId":request.anchor_id,
            "expectedPolicyRevisionId":request.expected_policy_revision_id,"expectedAuthoritySha256":authority}),
        current,
    )?;
    Payload::decode(value, request)
}

fn fresh(
    active: &ActiveAction,
    request: &ReaderActionRequest,
    before: &Payload,
    current: &dyn Fn() -> bool,
) -> Result<(), &'static str> {
    let after = payload(active, request, Some(&before.authority_sha256), current)?;
    if after.metadata != before.metadata
        || after.content_sha256 != before.content_sha256
        || after.anchor_revision_id != before.anchor_revision_id
    {
        return Err(FAILED);
    }
    Ok(())
}

fn export(
    active: Arc<ActiveAction>,
    request: ReaderActionRequest,
    before: Payload,
    directory: std::path::PathBuf,
    live: Arc<dyn Fn() -> bool + Send + Sync>,
    publication_live: Arc<dyn Fn() -> bool + Send + Sync>,
    gate: ApplicationLockManager,
    ticket: u64,
) -> Result<(), PickerFailure> {
    let failure = |_| PickerFailure::Failed;
    let application = if request.action == ReaderAction::OpenExternalOriginal {
        Some(crate::viewer_export::choose_application(active.owner, &*live).map_err(failure)?)
    } else {
        None
    };
    let extension = if application.is_some() {
        match before.metadata["source"]["format"].as_str() {
            Some("pdf") => "pdf",
            Some("docx") => "docx",
            Some("html") => "html",
            Some("plain-text") => "txt",
            _ => "xml",
        }
    } else {
        "json"
    };
    let mut output =
        LocalDeliverable::create(&directory, &request.operation_id, extension).map_err(failure)?;
    let (expected, length) = if application.is_some() {
        let length = before.metadata["source"]["byteLength"]
            .as_u64()
            .ok_or(PickerFailure::Failed)?;
        let mut offset = 0;
        while offset < length {
            let end = (offset + 1_048_576).min(length);
            let value = rpc(
                &active,
                NativeDocumentAction::ViewerRange,
                json!({"selector":request.selector,"start":offset,"end":end}),
                &*live,
            )
            .map_err(failure)?;
            if value["schemaVersion"] != "1.0"
                || value["metadata"] != before.metadata
                || value["start"] != offset
                || value["end"] != end
                || !value.as_object().is_some_and(|m| m.len() == 6)
            {
                return Err(PickerFailure::Failed);
            }
            let bytes = base64::engine::general_purpose::STANDARD
                .decode(value["bytesBase64"].as_str().ok_or(PickerFailure::Failed)?)
                .map_err(|_| PickerFailure::Failed)?;
            if bytes.len() as u64 != end - offset {
                return Err(PickerFailure::Failed);
            }
            output.append(&bytes, &*live).map_err(failure)?;
            offset = end;
        }
        (
            before.metadata["source"]["objectSha256"]
                .as_str()
                .ok_or(PickerFailure::Failed)?
                .to_owned(),
            length,
        )
    } else {
        output
            .append(before.content_utf8.as_bytes(), &*live)
            .map_err(failure)?;
        (
            before.content_sha256.clone(),
            before.content_utf8.len() as u64,
        )
    };
    output.verify(&expected, length, &*live).map_err(failure)?;
    fresh(&active, &request, &before, &*live).map_err(failure)?;
    // Core rights publication and OS publication are distinct fences. The
    // Native lock/generation lock serializes the actual local file publication.
    gate.commit_protected_action(ticket, || {
        active
            .connection
            .publish_current(|| output.publish(&*publication_live))
    })
    .map_err(failure)?;
    active.delivered.store(true, Ordering::Release);
    if let Some(application) = application {
        let (mut file, _guards, path) = output.into_external_file().map_err(failure)?;
        use std::io::Read;
        let mut sha = Sha256::new();
        let mut buffer = [0u8; 65536];
        let mut count = 0u64;
        while live() {
            let n = file.read(&mut buffer).map_err(|_| PickerFailure::Failed)?;
            if n == 0 {
                break;
            }
            count += n as u64;
            if count > length {
                return Err(PickerFailure::Failed);
            }
            sha.update(&buffer[..n]);
        }
        if count != length || format!("{:x}", sha.finalize()) != expected {
            return Err(PickerFailure::Failed);
        }
        fresh(&active, &request, &before, &*live).map_err(failure)?;
        gate.commit_protected_action(ticket, || {
            active.connection.publish_current(|| {
                crate::viewer_export::open_original(&application, &path, &*publication_live)
            })
        })
        .map_err(failure)?;
    }
    Ok(())
}

#[tauri::command]
pub(crate) async fn document_viewer_action(
    window: tauri::WebviewWindow,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    manager: State<'_, ViewerActionManager>,
    picker: State<'_, DirectoryPickerManager>,
    request: ReaderActionRequest,
) -> Result<ReaderActionOutcome, ()> {
    if !request.valid() {
        return Err(());
    }
    let owner = crate::directory_window_handle(&window).ok_or(())?;
    let ticket = lock.begin_protected_action().map_err(|_| ())?;
    let connection = Arc::new(
        supervisor
            .native_document_connection(&request.project_id)
            .map_err(|_| ())?,
    );
    let lease = match manager.begin(&request, owner, connection) {
        Ok(lease) => lease,
        Err(_) => {
            return Ok(ReaderActionOutcome {
                schema_version: "1.0",
                project_id: request.project_id.clone(),
                operation_id: request.operation_id.clone(),
                action: request.action,
                status: "unavailable",
                drained: manager.unissued_drained(&request),
                decision: None,
                review: None,
            });
        }
    };
    let active = Arc::clone(&lease.active);
    let gate = lock.inner().clone();
    let picker = picker.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let current_active = Arc::clone(&active);
        let current_gate = gate.clone();
        let publication_active = Arc::clone(&active);
        let publication_window = window.clone();
        // The publication closure runs inside both authority mutexes. Re-entering
        // those mutexes through `live` would deadlock; these non-locking checks
        // supplement the held lock/session fences at the actual OS effect.
        let publication_live: Arc<dyn Fn() -> bool + Send + Sync> = Arc::new(move ||
            !publication_active.cancelled.load(Ordering::Acquire)
            && crate::directory_window_handle(&publication_window) == Some(owner));
        let live: Arc<dyn Fn() -> bool + Send + Sync> = Arc::new(move || !current_active.cancelled.load(Ordering::Acquire)
            && current_active.connection.is_current() && current_gate.finish_protected_action(ticket).is_ok()
            && crate::directory_window_handle(&window) == Some(owner));
        let mut outcome = ReaderActionOutcome { schema_version: "1.0", project_id: request.project_id.clone(), operation_id: request.operation_id.clone(),
            action: request.action, status: "unavailable", drained: false, decision: None, review: None };
        let result = (|| -> Result<(), &'static str> {
            match request.stage {
                ActionStage::Policy | ActionStage::DeniedAttempt => {
                    let value = rpc(&active, NativeDocumentAction::ViewerActionPolicy,
                        json!({"selector":request.selector,"action":request.action,"anchorId":request.anchor_id,
                            "directTransfer":request.stage == ActionStage::DeniedAttempt}), &*live)?;
                    if !policy_matches(&value, &request) || !live() { return Err(FAILED); }
                    outcome.decision = Some(value); outcome.status = "policy";
                }
                ActionStage::RightsReview => {
                    let value = rpc(&active, NativeDocumentAction::ViewerRightsReview,
                        json!({"selector":request.selector,"action":request.action,"expectedPolicyRevisionId":request.expected_policy_revision_id,
                            "commandId":request.command_id,"confirmed":true}), &*live)?;
                    if !value.as_object().is_some_and(|m| m.len() == 5) || value["schemaVersion"] != "1.0" || value["status"] != "recorded"
                        || value["action"] != json!(request.action) || !value["policyRevisionId"].as_str().is_some_and(uuid)
                        || !metadata_matches(&value["metadata"], &request.source()) || !live() { return Err(FAILED); }
                    outcome.review = Some(value); outcome.status = "recorded";
                }
                ActionStage::Execute => {
                    let before = payload(&active, &request, None, &*live)?;
                    match request.action {
                        ReaderAction::CopyQuotation => {
                            fresh(&active, &request, &before, &*live)?;
                            gate.commit_protected_action(ticket, || active.connection.publish_current(|| crate::viewer_export::copy_quotation(owner, &before.content_utf8, &*publication_live)))?;
                            active.delivered.store(true, Ordering::Release);
                        }
                        ReaderAction::PrintQuotation => {
                            let printer = picker.with_native_dialog(owner, |current| crate::viewer_export::choose_printer(owner, &|| current() && live())).ok_or(FAILED)??;
                            if let Some(name) = printer.file_printer().map(str::to_owned) {
                                drop(printer);
                                let destination_active = Arc::clone(&active);
                                let destination_live = Arc::clone(&live);
                                let destination_gate = gate.clone();
                                let destination_publication_live = Arc::clone(&publication_live);
                                let selected = request.clone();
                                picker.viewer_destination(owner, move || destination_live(), move |directory, selected_live| {
                                    let failure = |_| PickerFailure::Failed;
                                    let output = LocalDeliverable::create(&directory, &selected.operation_id, "pdf").map_err(failure)?;
                                    let mut output = crate::viewer_print::print_file(&name, &before.content_utf8, output, Arc::clone(&selected_live),
                                        &|| fresh(&destination_active, &selected, &before, &*selected_live)).map_err(failure)?;
                                    fresh(&destination_active, &selected, &before, &*selected_live).map_err(failure)?;
                                    destination_gate.commit_protected_action(ticket, || destination_active.connection.publish_current(||
                                        output.publish(&*destination_publication_live))).map_err(failure)?;
                                    destination_active.delivered.store(true, Ordering::Release);
                                    Ok(())
                                }).map_err(|f| if f == PickerFailure::Cancelled { "RO-VIEWER-ACTION-CANCELLED" } else { FAILED })?;
                            } else { return Err(FAILED); }
                        }
                        _ => {
                            let destination_active = Arc::clone(&active);
                            let destination_live = Arc::clone(&live);
                            let destination_gate = gate.clone();
                            let destination_publication_live = Arc::clone(&publication_live);
                            let selected = request.clone();
                            picker.viewer_destination(owner, move || destination_live(), move |directory, selected_live| {
                                export(destination_active, selected, before, directory, selected_live, destination_publication_live, destination_gate, ticket)
                            }).map_err(|f| if f == PickerFailure::Cancelled { "RO-VIEWER-ACTION-CANCELLED" } else { FAILED })?;
                        }
                    }
                    outcome.status = "completed";
                }
            }
            Ok(())
        })();
        if result.is_err() {
            outcome.decision = None; outcome.review = None;
            if active.cancelled.load(Ordering::Acquire) || !live() || result == Err("RO-VIEWER-ACTION-CANCELLED") { outcome.status = "cancelled"; }
            if active.delivered.load(Ordering::Acquire) { outcome.status = "partial"; }
        }
        cancel_frame(&active);
        drop(lease);
        outcome.drained = active.closed.load(Ordering::Acquire) && active.core_frame.lock().is_ok_and(|f| f.is_none());
        outcome
    }).await.map_err(|_| ())
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ActionCancelRequest {
    schema_version: String,
    project_id: String,
    operation_id: String,
}

#[tauri::command]
pub(crate) async fn document_viewer_action_cancel(
    window: tauri::WebviewWindow,
    manager: State<'_, ViewerActionManager>,
    request: ActionCancelRequest,
) -> Result<bool, ()> {
    if request.schema_version != "1.0"
        || !crate::supervisor::canonical_project_id(&request.project_id)
        || !uuid(&request.operation_id)
    {
        return Err(());
    }
    let owner = crate::directory_window_handle(&window).ok_or(())?;
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        manager.cancel(&request.project_id, &request.operation_id, owner)
    })
    .await
    .map_err(|_| ())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request(number: u16) -> ReaderActionRequest {
        serde_json::from_value(json!({"schemaVersion":"1.0","projectId":"01a123ff-0000-7000-8000-000000000001",
            "selector":{"attachmentId":"01a123ff-0000-7000-8000-000000000002","documentRevisionId":"01a123ff-0000-7000-8000-000000000003","normalizedRevisionId":null},
            "operationId":format!("01a123ff-0000-7000-8000-{number:012}"),"stage":"policy","action":"open-external-original",
            "anchorId":null,"expectedPolicyRevisionId":null,"commandId":null,"confirmed":false})).unwrap()
    }
    #[test]
    fn cancellation_before_admission_survives_and_cannot_report_absence_as_drain() {
        let manager = ViewerActionManager::default();
        let request = request(10);
        assert!(!manager.cancel(&request.project_id, &request.operation_id, 51));
        let connection = Arc::new(NativeImportConnection::action_test_connection(
            &request.project_id,
            false,
        ));
        let lease = manager.begin(&request, 51, connection).unwrap();
        assert!(lease.active.cancelled.load(Ordering::Acquire));
        assert!(!manager.cancel(&request.project_id, &request.operation_id, 51));
        drop(lease);
        assert!(manager.cancel(&request.project_id, &request.operation_id, 51));
    }
    #[test]
    fn unknown_core_frame_retains_admission_after_actual_native_closure() {
        let manager = ViewerActionManager::default();
        let request = request(10);
        let lease = manager
            .begin(
                &request,
                51,
                Arc::new(NativeImportConnection::action_test_connection(
                    &request.project_id,
                    false,
                )),
            )
            .unwrap();
        let active = Arc::clone(&lease.active);
        *active.core_frame.lock().unwrap() = Some(("owned-session".into(), "owned-request".into()));
        drop(lease);
        assert!(active.closed.load(Ordering::Acquire));
        assert!(!manager.release_closed(&active));
        assert!(!manager.unissued_drained(&request));
        let next = super::tests::request(11);
        assert!(manager.unissued_drained(&next));
        assert!(
            manager
                .begin(
                    &next,
                    51,
                    Arc::new(NativeImportConnection::action_test_connection(
                        &next.project_id,
                        false
                    ))
                )
                .is_err()
        );
        *active.core_frame.lock().unwrap() = None;
        assert!(manager.release_closed(&active));
    }
    #[test]
    fn early_markers_are_window_owned_bounded_and_fail_closed_on_exhaustion() {
        let manager = ViewerActionManager::default();
        let original = request(10);
        manager.cancel(&original.project_id, &original.operation_id, 52);
        let lease = manager
            .begin(
                &original,
                51,
                Arc::new(NativeImportConnection::action_test_connection(
                    &original.project_id,
                    true,
                )),
            )
            .unwrap();
        assert!(!lease.active.cancelled.load(Ordering::Acquire));
        drop(lease);
        for n in 20..277 {
            let r = request(n);
            manager.cancel(&r.project_id, &r.operation_id, 51);
        }
        let state = manager.0.lock().unwrap();
        assert!(state.exhausted);
        assert_eq!(256, state.early.len());
        drop(state);
        let r = request(400);
        assert!(
            manager
                .begin(
                    &r,
                    51,
                    Arc::new(NativeImportConnection::action_test_connection(
                        &r.project_id,
                        true
                    ))
                )
                .is_err()
        );
    }
    #[test]
    fn caller_text_paths_authority_and_broad_use_purposes_are_rejected() {
        let r = request(10);
        assert!(r.valid());
        let base = json!({"schemaVersion":"1.0","projectId":r.project_id,"selector":r.selector,"operationId":r.operation_id,
            "stage":"execute","action":"copy-quotation","anchorId":"01a123ff-0000-7000-8000-000000000005",
            "expectedPolicyRevisionId":"01a123ff-0000-7000-8000-000000000006","commandId":null,"confirmed":true});
        for field in [
            "text",
            "root",
            "actorId",
            "destination",
            "applicationPath",
            "policy",
            "grant",
        ] {
            let mut changed = base.clone();
            changed[field] = "untrusted".into();
            assert!(serde_json::from_value::<ReaderActionRequest>(changed).is_err());
        }
        let basis = Value::Array(
            uses(ReaderAction::CopyQuotation)
                .into_iter()
                .map(|u| json!({"use":u,"code":"allow","reasonCode":"rights-permitted"}))
                .collect(),
        );
        assert!(basis_matches(&basis, ReaderAction::CopyQuotation, true));
        assert!(!basis_matches(
            &basis,
            ReaderAction::OpenExternalOriginal,
            true
        ));
        let mut changed = basis.clone();
        changed[3]["use"]["purpose"] = "project-export".into();
        assert!(!basis_matches(&changed, ReaderAction::CopyQuotation, true));
        changed = basis;
        changed[3]["code"] = "unknown".into();
        assert!(!basis_matches(&changed, ReaderAction::CopyQuotation, true));
    }
}
