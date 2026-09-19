//! Native selected-stream composition; never a renderer filesystem capability.

use crate::application_lock::ApplicationLockManager;
use crate::directory_picker::{DirectoryPickerManager, PickerFailure};
use crate::supervisor::{NativeImportAction, NativeImportConnection, RuntimeSupervisor};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ImportRequest {
    pub root: String,
    pub project_id: String,
    pub operation_id: String,
    format_name: String,
    encoding: String,
    #[serde(default = "comma")]
    delimiter: String,
    rights: serde_json::Value,
}

fn comma() -> String {
    ",".to_string()
}

fn hex32(value: &str) -> bool {
    value.len() == 32
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn valid_rights(value: &serde_json::Value) -> bool {
    let Some(rights) = value.as_object() else {
        return false;
    };
    let actions = [
        "store",
        "inspect",
        "index",
        "derive",
        "model-use",
        "quote",
        "export",
        "share",
    ];
    rights.len() == actions.len()
        && actions.iter().all(|action| {
            let Some(permission) = rights.get(*action).and_then(serde_json::Value::as_object)
            else {
                return false;
            };
            permission.len() == 2
                && permission.contains_key("value")
                && permission.contains_key("basis")
                && matches!(
                    permission["value"].as_str(),
                    Some("permitted" | "denied" | "unknown")
                )
                && matches!(
                    permission["basis"].as_str(),
                    Some("not-reported" | "researcher-confirmed")
                )
                && (permission["value"] == "unknown"
                    || permission["basis"] == "researcher-confirmed")
                && (!matches!(*action, "store" | "inspect") || permission["value"] == "permitted")
        })
}

pub(crate) fn decode_request(payload: &serde_json::Value) -> Option<ImportRequest> {
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Envelope {
        request: ImportRequest,
    }
    let Envelope { request } = serde_json::from_value(payload.clone()).ok()?;
    (crate::directory_picker::local_path_syntax(&request.root)
        && crate::supervisor::canonical_project_id(&request.project_id)
        && hex32(&request.operation_id)
        && matches!(
            request.format_name.as_str(),
            "ris" | "bibtex" | "csl-json" | "doi-list" | "csv"
        )
        && matches!(request.encoding.as_str(), "utf-8" | "cp1252")
        && !(request.format_name == "csl-json" && request.encoding != "utf-8")
        && matches!(request.delimiter.as_str(), "," | "\t" | ";")
        && (request.format_name == "csv" || request.delimiter == ",")
        && valid_rights(&request.rights))
    .then_some(request)
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ImportStatus {
    pub preview_id: String,
    state: String,
    byte_length: u64,
    chunk_count: u32,
    job_id: Option<String>,
    job_state: Option<String>,
}

#[derive(Serialize)]
#[serde(tag = "status", rename_all = "kebab-case")]
pub(crate) enum ImportOutcome {
    Prepared {
        #[serde(rename = "sourceName")]
        source_name: String,
        preview: ImportStatus,
    },
    Cancelled,
    Unavailable,
    Failed,
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ReportRequest {
    pub root: String,
    pub project_id: String,
    pub operation_id: String,
    pub preview_id: String,
    pub revision: u32,
}
pub(crate) fn decode_report_request(payload: &serde_json::Value) -> Option<ReportRequest> {
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Envelope {
        request: ReportRequest,
    }
    let Envelope { request } = serde_json::from_value(payload.clone()).ok()?;
    (crate::directory_picker::local_path_syntax(&request.root)
        && crate::supervisor::canonical_project_id(&request.project_id)
        && crate::supervisor::canonical_uuid_v7(&request.preview_id)
        && hex32(&request.operation_id)
        && (1..=2147483647).contains(&request.revision))
    .then_some(request)
}
#[derive(Debug, Serialize)]
#[serde(tag = "status", rename_all = "kebab-case")]
pub(crate) enum ReportOutcome {
    Saved {
        filename: String,
        #[serde(rename = "byteLength")]
        byte_length: u64,
    },
    Cancelled,
    Unavailable,
    Failed,
}
impl crate::directory_picker::PickerResult for ReportOutcome {
    fn committed(&self) -> bool {
        matches!(self, Self::Saved { .. })
    }
    fn cancelled() -> Self {
        Self::Cancelled
    }
    fn unavailable() -> Self {
        Self::Unavailable
    }
    fn failed() -> Self {
        Self::Failed
    }
}

struct ActiveImport {
    id: String,
    cancelled: Arc<AtomicBool>,
}
#[derive(Default)]
struct Admission {
    closed: bool,
    active: Option<ActiveImport>,
    cancelled_before_start: BTreeSet<String>,
}
#[derive(Clone, Default)]
pub(crate) struct ImportManager {
    shared: Arc<(Mutex<Admission>, Condvar)>,
}
struct ImportPermit {
    manager: ImportManager,
    cancelled: Arc<AtomicBool>,
}

impl Drop for ImportPermit {
    fn drop(&mut self) {
        let mut state = self
            .manager
            .shared
            .0
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if state
            .active
            .as_ref()
            .is_some_and(|value| Arc::ptr_eq(&value.cancelled, &self.cancelled))
        {
            state.active = None;
        }
        self.manager.shared.1.notify_all();
    }
}

impl ImportManager {
    fn begin(&self, id: &str) -> Result<ImportPermit, PickerFailure> {
        let mut state = self.shared.0.lock().map_err(|_| PickerFailure::Failed)?;
        if state.cancelled_before_start.remove(id) {
            return Err(PickerFailure::Cancelled);
        }
        if state.closed || state.active.is_some() || state.cancelled_before_start.len() >= 256 {
            return Err(PickerFailure::Unavailable);
        }
        let cancelled = Arc::new(AtomicBool::new(false));
        state.active = Some(ActiveImport {
            id: id.into(),
            cancelled: Arc::clone(&cancelled),
        });
        Ok(ImportPermit {
            manager: self.clone(),
            cancelled,
        })
    }

    pub(crate) fn cancel(&self, id: &str, picker: &DirectoryPickerManager) {
        if !hex32(id) {
            return;
        }
        if let Ok(mut state) = self.shared.0.lock() {
            if let Some(active) = state.active.as_ref().filter(|value| value.id == id) {
                active.cancelled.store(true, Ordering::Release);
                picker.cancel_pending();
            } else if state.cancelled_before_start.len() < 256 {
                // IPC and blocking-worker scheduling may deliver cancellation
                // before admission. Never evict a pending cancellation.
                state.cancelled_before_start.insert(id.to_owned());
            } else if !state.cancelled_before_start.contains(id) {
                // A flooding caller cannot trade bounded memory for a lost
                // cancellation. Further intake requires a fresh native session.
                state.closed = true;
                if let Some(active) = &state.active {
                    active.cancelled.store(true, Ordering::Release);
                    picker.cancel_pending();
                }
            }
        }
    }

    pub(crate) fn begin_close(&self) {
        let mut state = self
            .shared
            .0
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        state.closed = true;
        if let Some(active) = &state.active {
            active.cancelled.store(true, Ordering::Release);
        }
    }

    pub(crate) fn wait_for_cleanup(&self) {
        let mut state = self
            .shared
            .0
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        while state.active.is_some() {
            state = self
                .shared
                .1
                .wait(state)
                .unwrap_or_else(|error| error.into_inner());
        }
    }
}

struct PendingPreview {
    connection: Arc<NativeImportConnection>,
    address: serde_json::Value,
    preview_id: Option<String>,
    accepted: bool,
}

impl PendingPreview {
    fn request(
        &self,
        action: NativeImportAction,
        extra: serde_json::Value,
    ) -> Result<serde_json::Value, PickerFailure> {
        let mut body = self
            .address
            .as_object()
            .ok_or(PickerFailure::Failed)?
            .clone();
        if let Some(preview) = &self.preview_id {
            body.insert("previewId".into(), preview.clone().into());
        }
        body.extend(extra.as_object().ok_or(PickerFailure::Failed)?.clone());
        let response = self
            .connection
            .request(action, serde_json::Value::Object(body))
            .map_err(|_| PickerFailure::Failed)?;
        if response.status != 200
            || response.content_type != "application/json"
            || response.body.len() > 16384
        {
            return Err(PickerFailure::Failed);
        }
        serde_json::from_str(&response.body).map_err(|_| PickerFailure::Failed)
    }

    fn status(&self, value: serde_json::Value) -> Result<ImportStatus, PickerFailure> {
        ImportStatus::decode(self.preview_id.as_deref(), value)
    }
}

impl ImportStatus {
    fn decode(preview: Option<&str>, value: serde_json::Value) -> Result<Self, PickerFailure> {
        let status: ImportStatus =
            serde_json::from_value(value).map_err(|_| PickerFailure::Failed)?;
        if !crate::supervisor::canonical_uuid_v7(&status.preview_id)
            || preview.is_some_and(|preview| preview != status.preview_id)
            || status.byte_length > 268435456
            || status.chunk_count > 2048
            || !matches!(
                status.state.as_str(),
                "created"
                    | "source-sealed"
                    | "parse-started"
                    | "parse-completed"
                    | "draft-revised"
                    | "cancelled"
                    | "failed"
                    | "security-interrupted"
            )
            || status
                .job_id
                .as_ref()
                .is_some_and(|id| !crate::supervisor::canonical_uuid_v7(id))
            || status.job_id.is_some() != status.job_state.is_some()
            || status.job_state.as_ref().is_some_and(|state| {
                !matches!(
                    state.as_str(),
                    "runnable"
                        | "claimed"
                        | "running"
                        | "retry-scheduled"
                        | "cancelling"
                        | "cancelled"
                        | "failed"
                        | "succeeded"
                )
            })
        {
            return Err(PickerFailure::Failed);
        }
        Ok(status)
    }
}

impl Drop for PendingPreview {
    fn drop(&mut self) {
        if !self.accepted && self.preview_id.is_some() {
            // Best effort in the exact original Core/project session. No new
            // process is contacted. Dead-session intake stays incomplete.
            let _ = self.request(NativeImportAction::Cancel, serde_json::json!({}));
        }
    }
}

pub(crate) struct PreparedImport {
    pending: PendingPreview,
    permit: ImportPermit,
    source_name: String,
    status: ImportStatus,
}

impl PreparedImport {
    /// No network or file I/O; caller holds the lock-generation publication guard.
    pub(crate) fn accept(&mut self) -> bool {
        let Ok(state) = self.permit.manager.shared.0.lock() else {
            return false;
        };
        if state.closed
            || self.permit.cancelled.load(Ordering::Acquire)
            || !state
                .active
                .as_ref()
                .is_some_and(|entry| Arc::ptr_eq(&entry.cancelled, &self.permit.cancelled))
            || !self.pending.connection.is_current()
        {
            return false;
        }
        self.pending.accepted = true;
        true
    }

    pub(crate) fn into_outcome(self) -> ImportOutcome {
        ImportOutcome::Prepared {
            source_name: self.source_name,
            preview: self.status,
        }
    }
}

#[cfg(windows)]
pub(crate) fn prepare(
    manager: ImportManager,
    picker: DirectoryPickerManager,
    supervisor: RuntimeSupervisor,
    lock: ApplicationLockManager,
    ticket: u64,
    owner: isize,
    request: ImportRequest,
) -> Result<PreparedImport, PickerFailure> {
    use base64::Engine;
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
    let mut pending = PendingPreview {
        connection: Arc::clone(&connection),
        address: serde_json::json!({"root":request.root,"projectId":request.project_id}),
        preview_id: None,
        accepted: false,
    };
    #[derive(Deserialize)]
    #[serde(rename_all = "camelCase", deny_unknown_fields)]
    struct Context {
        project_id: String,
        session_id: String,
    }
    let context: Context = serde_json::from_value(
        pending.request(NativeImportAction::Context, serde_json::json!({}))?,
    )
    .map_err(|_| PickerFailure::Failed)?;
    if context.project_id != request.project_id || !hex32(&context.session_id) {
        return Err(PickerFailure::Failed);
    }
    pending.address["sessionId"] = context.session_id.into();
    let cancelled = Arc::clone(&permit.cancelled);
    let checking_picker = picker.clone();
    picker.import_source(owner, move || !cancelled.load(Ordering::Acquire)
        && checking_picker.is_open() && lock.finish_protected_action(ticket).is_ok() && connection.is_current(),
        move |source, authorized| {
            let source_name = source.basename().to_owned();
            let status = pending.status(pending.request(NativeImportAction::Create, serde_json::json!({
                "sourceName":source_name,"formatName":request.format_name,"encoding":request.encoding,"delimiter":request.delimiter,"rights":request.rights
            }))?)?;
            pending.preview_id = Some(status.preview_id.clone());
            if status.state != "created" || status.byte_length != 0 || status.chunk_count != 0 || status.job_id.is_some() {
                return Err(PickerFailure::Failed);
            }
            let mut accepted_bytes = 0_u64;
            let seal = source.transfer(|| authorized(), |ordinal, bytes| {
                let data = base64::engine::general_purpose::STANDARD.encode(bytes);
                let status = pending.request(NativeImportAction::Chunk, serde_json::json!({"ordinal":ordinal,"data":data}))
                    .and_then(|value| pending.status(value)).map_err(|_| "RO-IMPORT-TRANSFER-FAILED")?;
                accepted_bytes += bytes.len() as u64;
                if status.state != "created" || status.byte_length != accepted_bytes || status.chunk_count != ordinal {
                    return Err("RO-IMPORT-TRANSFER-FAILED");
                }
                Ok(())
            }).map_err(|_| if authorized() { PickerFailure::Failed } else { PickerFailure::Cancelled })?;
            if !authorized() { return Err(PickerFailure::Cancelled); }
            let sealed = pending.status(pending.request(NativeImportAction::Seal, serde_json::json!({
                "sourceSha256":seal.source_sha256,"byteLength":seal.byte_length,"chunkCount":seal.chunk_count
            }))?)?;
            if !authorized() { return Err(PickerFailure::Cancelled); }
            if sealed.state != "source-sealed" || sealed.byte_length != seal.byte_length || sealed.chunk_count != seal.chunk_count {
                return Err(PickerFailure::Failed);
            }
            let status = pending.status(pending.request(NativeImportAction::Schedule, serde_json::json!({}))?)?;
            if !authorized() { return Err(PickerFailure::Cancelled); }
            if status.job_id.is_none() || matches!(status.state.as_str(), "created" | "cancelled" | "failed" | "security-interrupted") {
                return Err(PickerFailure::Failed);
            }
            Ok(PreparedImport { pending, permit, source_name, status })
        })
}

pub(crate) fn failure(error: PickerFailure) -> ImportOutcome {
    match error {
        PickerFailure::Cancelled => ImportOutcome::Cancelled,
        PickerFailure::Unavailable => ImportOutcome::Unavailable,
        PickerFailure::Failed => ImportOutcome::Failed,
    }
}

#[cfg(windows)]
pub(crate) fn save_report(
    manager: ImportManager,
    picker: DirectoryPickerManager,
    supervisor: RuntimeSupervisor,
    lock: ApplicationLockManager,
    ticket: u64,
    owner: isize,
    request: ReportRequest,
) -> ReportOutcome {
    use crate::import_report::{ReportCursor, ReportPage, StagedReport};
    let permit = match manager.begin(&request.operation_id) {
        Ok(permit) => permit,
        Err(PickerFailure::Cancelled) => return ReportOutcome::Cancelled,
        Err(_) => return ReportOutcome::Unavailable,
    };
    let Ok(connection) = supervisor.native_import_connection(&request.root, &request.project_id)
    else {
        return ReportOutcome::Unavailable;
    };
    let connection = Arc::new(connection);
    let call_connection = Arc::clone(&connection);
    let mut address = serde_json::json!({"root":request.root,"projectId":request.project_id});
    let rpc = move |action, body| -> Result<serde_json::Value, &'static str> {
        let response = call_connection.request(action, body)?;
        if response.status != 200
            || response.content_type != "application/json"
            || response.body.len() > 900000
        {
            return Err("RO-IMPORT-REPORT-FAILED");
        }
        serde_json::from_str(&response.body).map_err(|_| "RO-IMPORT-REPORT-FAILED")
    };
    if permit.cancelled.load(Ordering::Acquire)
        || lock.finish_protected_action(ticket).is_err()
        || !picker.is_open()
    {
        return ReportOutcome::Cancelled;
    }
    let Ok(context) = rpc(NativeImportAction::Context, address.clone()) else {
        return ReportOutcome::Failed;
    };
    if context.as_object().is_none_or(|object| object.len() != 2)
        || context["projectId"] != request.project_id
        || !context["sessionId"].as_str().is_some_and(hex32)
    {
        return ReportOutcome::Failed;
    }
    address["sessionId"] = context["sessionId"].clone();
    address["previewId"] = request.preview_id.clone().into();
    address["revision"] = request.revision.into();
    address["limit"] = 25.into();
    let page = move |after: u32| -> Result<ReportPage, &'static str> {
        let mut body = address.clone();
        body["after"] = after.into();
        serde_json::from_value(rpc(NativeImportAction::Report, body)?)
            .map_err(|_| "RO-IMPORT-REPORT-FAILED")
    };
    // Authorize the current draft before asking for a destination. This page is
    // re-requested after the dialog; no stale page becomes export authority.
    if page(0).is_err() {
        return ReportOutcome::Failed;
    }
    let checking_connection = Arc::clone(&connection);
    let checking_lock = lock.clone();
    let checking_picker = picker.clone();
    let publication_picker = picker.clone();
    let cancelled = Arc::clone(&permit.cancelled);
    picker.report_destination(
        owner,
        move || {
            !cancelled.load(Ordering::Acquire)
                && checking_picker.is_open()
                && checking_lock.finish_protected_action(ticket).is_ok()
                && checking_connection.is_current()
        },
        move |directory, authorized| {
            let result = (|| -> Result<ReportOutcome, &'static str> {
                let mut cursor = ReportCursor::new(&request.preview_id, request.revision);
                let mut stage = StagedReport::create(&directory, &request.operation_id)?;
                while !cursor.complete {
                    if !authorized() {
                        return Err("RO-IMPORT-REPORT-CANCELLED");
                    }
                    let csv = cursor.accept(page(cursor.after)?)?;
                    if !authorized() {
                        return Err("RO-IMPORT-REPORT-CANCELLED");
                    }
                    stage.append(csv.as_bytes())?;
                }
                stage.verify(|| authorized())?;
                cursor.authorize_final(page(cursor.after)?)?;
                let (filename, byte_length) = stage.receipt();
                // Final Core authorization above and native rename below are
                // distinct points, not an invented cross-process transaction.
                lock.commit_protected_action(ticket, || {
                    let state = permit
                        .manager
                        .shared
                        .0
                        .lock()
                        .map_err(|_| "RO-IMPORT-REPORT-CANCELLED")?;
                    if state.closed
                        || permit.cancelled.load(Ordering::Acquire)
                        || !publication_picker.is_open()
                        || !crate::directory_picker::valid_owner(owner)
                        || !state
                            .active
                            .as_ref()
                            .is_some_and(|active| Arc::ptr_eq(&active.cancelled, &permit.cancelled))
                    {
                        return Err("RO-IMPORT-REPORT-CANCELLED");
                    }
                    connection.publish_current(|| stage.publish())
                })?;
                Ok(ReportOutcome::Saved {
                    filename,
                    byte_length,
                })
            })();
            match result {
                Ok(saved) => saved,
                Err(_) if !authorized() => ReportOutcome::Cancelled,
                Err(_) => ReportOutcome::Failed,
            }
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn request() -> serde_json::Value {
        let mut rights = serde_json::Map::new();
        for action in [
            "store",
            "inspect",
            "index",
            "derive",
            "model-use",
            "quote",
            "export",
            "share",
        ] {
            rights.insert(
                action.into(),
                if matches!(action, "store" | "inspect") {
                    json!({"value":"permitted","basis":"researcher-confirmed"})
                } else {
                    json!({"value":"unknown","basis":"not-reported"})
                },
            );
        }
        json!({"request":{"root":"C:/Synthetic/project", "projectId":"01900000-0000-4000-8000-000000000001",
            "operationId":"a".repeat(32),"formatName":"csv","encoding":"utf-8","rights":rights}})
    }

    #[test]
    fn native_import_delimiter_request_is_explicit_and_csv_only() {
        assert_eq!(decode_request(&request()).unwrap().delimiter, ",");
        for delimiter in [",", "\t", ";"] {
            let mut value = request();
            value["request"]["delimiter"] = json!(delimiter);
            assert_eq!(decode_request(&value).unwrap().delimiter, delimiter);
        }
        for delimiter in ["", "|", "\\t", "\n"] {
            let mut value = request();
            value["request"]["delimiter"] = json!(delimiter);
            assert!(decode_request(&value).is_none());
        }
        let mut value = request();
        value["request"]["formatName"] = json!("ris");
        value["request"]["delimiter"] = json!(";");
        assert!(decode_request(&value).is_none());
    }

    #[test]
    fn report_request_binds_exact_draft_and_never_accepts_renderer_destination() {
        let value = json!({"request":{"root":"C:/Synthetic/project", "projectId":"01900000-0000-4000-8000-000000000001",
            "operationId":"a".repeat(32), "previewId":"01900000-0000-7000-8000-000000000001", "revision":1}});
        assert!(decode_report_request(&value).is_some());
        for key in [
            "path",
            "destination",
            "filename",
            "sessionId",
            "rights",
            "actor",
        ] {
            let mut altered = value.clone();
            altered["request"][key] = json!("synthetic");
            assert!(decode_report_request(&altered).is_none());
        }
        for invalid in [json!(0), json!(true), json!(-1), json!(2147483648_u64)] {
            let mut altered = value.clone();
            altered["request"]["revision"] = invalid;
            assert!(decode_report_request(&altered).is_none());
        }
    }

    #[test]
    fn native_intake_request_never_accepts_a_source_path_actor_or_implicit_rights() {
        assert!(decode_request(&request()).is_some());
        for key in [
            "sourcePath",
            "actor",
            "resumeEpoch",
            "sessionId",
            "previewId",
        ] {
            let mut value = request();
            value["request"][key] = json!("synthetic");
            assert!(decode_request(&value).is_none());
        }
        for field in ["store", "inspect"] {
            let mut value = request();
            value["request"]["rights"][field] = json!({"value":"unknown","basis":"not-reported"});
            assert!(decode_request(&value).is_none());
        }
        let mut value = request();
        value["request"]["rights"]["store"]["basis"] = json!("not-reported");
        assert!(decode_request(&value).is_none());
        let mut value = request();
        value["request"]["formatName"] = json!("csl-json");
        value["request"]["encoding"] = json!("cp1252");
        assert!(decode_request(&value).is_none());
    }

    #[test]
    fn native_intake_status_is_bounded_and_bound_to_the_exact_preview() {
        let id = "01900000-0000-7000-8000-000000000001";
        let value = json!({"previewId":id,"state":"created","byteLength":1,"chunkCount":1,"jobId":null,"jobState":null});
        assert!(ImportStatus::decode(Some(id), value.clone()).is_ok());
        assert!(
            ImportStatus::decode(Some("01900000-0000-7000-8000-000000000002"), value.clone())
                .is_err()
        );
        for (key, replacement) in [
            ("byteLength", json!(268435457_u64)),
            ("chunkCount", json!(2049)),
            ("jobState", json!("succeeded")),
            ("state", json!("fabricated")),
            ("sourcePath", json!("synthetic")),
        ] {
            let mut changed = value.clone();
            changed[key] = replacement;
            assert!(ImportStatus::decode(Some(id), changed).is_err());
        }
    }

    #[test]
    fn native_intake_admission_cancellation_and_close_wait_for_the_owned_permit() {
        use std::sync::mpsc;
        use std::time::Duration;
        let manager = ImportManager::default();
        let picker = DirectoryPickerManager::default();
        let permit = manager.begin(&"a".repeat(32)).unwrap();
        assert!(manager.begin(&"b".repeat(32)).is_err());
        manager.cancel(&"b".repeat(32), &picker);
        assert!(!permit.cancelled.load(Ordering::Acquire));
        manager.cancel(&"a".repeat(32), &picker);
        assert!(permit.cancelled.load(Ordering::Acquire));
        manager.begin_close();
        let waiting = manager.clone();
        let (done, completion) = mpsc::channel();
        let waiter = std::thread::spawn(move || {
            waiting.wait_for_cleanup();
            done.send(()).unwrap();
        });
        assert!(completion.recv_timeout(Duration::from_millis(50)).is_err());
        drop(permit);
        completion.recv_timeout(Duration::from_secs(5)).unwrap();
        waiter.join().unwrap();
        assert!(manager.begin(&"c".repeat(32)).is_err());
    }

    #[test]
    fn native_intake_cancel_before_worker_admission_prevents_any_preparation() {
        use std::sync::mpsc;
        use std::time::Duration;
        let manager = ImportManager::default();
        let picker = DirectoryPickerManager::default();
        let worker_manager = manager.clone();
        let (release, ready) = mpsc::channel();
        let prepared = Arc::new(AtomicBool::new(false));
        let worker_prepared = Arc::clone(&prepared);
        let worker = std::thread::spawn(move || {
            ready.recv_timeout(Duration::from_secs(5)).unwrap();
            let _permit = worker_manager.begin(&"a".repeat(32))?;
            // Context, picker and Create all occur only after admission.
            worker_prepared.store(true, Ordering::Release);
            Ok::<(), PickerFailure>(())
        });
        manager.cancel(&"a".repeat(32), &picker);
        release.send(()).unwrap();
        assert!(matches!(
            worker.join().unwrap(),
            Err(PickerFailure::Cancelled)
        ));
        assert!(!prepared.load(Ordering::Acquire));
        assert!(manager.begin(&"b".repeat(32)).is_ok());
    }

    #[test]
    fn native_intake_pending_cancellations_are_bounded_without_eviction() {
        let manager = ImportManager::default();
        let picker = DirectoryPickerManager::default();
        manager.cancel("invalid", &picker);
        for ordinal in 0..257 {
            manager.cancel(&format!("{ordinal:032x}"), &picker);
        }
        assert_eq!(
            manager
                .shared
                .0
                .lock()
                .unwrap()
                .cancelled_before_start
                .len(),
            256
        );
        assert!(matches!(
            manager.begin(&format!("{:032x}", 0)),
            Err(PickerFailure::Cancelled)
        ));
        assert!(manager.begin(&format!("{:032x}", 256)).is_err());
        assert!(manager.begin(&format!("{:032x}", 300)).is_err());
    }
}
