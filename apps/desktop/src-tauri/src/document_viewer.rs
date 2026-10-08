//! Closed source/range commands: native owns root, session, window and byte IPC.

use crate::application_lock::ApplicationLockManager;
use crate::document_runtime::current_document_context;
use crate::supervisor::{NativeDocumentAction, NativeImportConnection, RuntimeSupervisor};
use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tauri::State;

const MAX_RANGE: u64 = 1_048_576;
const MAX_SOURCE: u64 = 134_217_728;
const MAX_RESPONSE: usize = 1_406_296;

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ViewerSelector {
    attachment_id: String,
    document_revision_id: String,
    normalized_revision_id: Option<String>,
}

impl ViewerSelector {
    fn valid(&self) -> bool {
        crate::supervisor::canonical_uuid_v7(&self.attachment_id)
            && crate::supervisor::canonical_uuid_v7(&self.document_revision_id)
            && self.normalized_revision_id.as_ref().is_none_or(|id| {
                crate::supervisor::canonical_uuid_v7(id) && id != &self.document_revision_id
            })
    }
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ViewerSourceRequest {
    schema_version: String,
    project_id: String,
    selector: ViewerSelector,
}

impl ViewerSourceRequest {
    fn valid(&self) -> bool {
        self.schema_version == "1.0"
            && crate::supervisor::canonical_project_id(&self.project_id)
            && self.selector.valid()
    }
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ViewerRangeRequest {
    schema_version: String,
    project_id: String,
    selector: ViewerSelector,
    request_id: String,
    start: u64,
    end: u64,
}

impl ViewerRangeRequest {
    fn valid(&self) -> bool {
        ViewerSourceRequest {
            schema_version: self.schema_version.clone(),
            project_id: self.project_id.clone(),
            selector: self.selector.clone(),
        }
        .valid()
            && crate::supervisor::canonical_uuid_v7(&self.request_id)
            && self.start < self.end
            && self.end <= MAX_SOURCE
            && self.end - self.start <= MAX_RANGE
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ViewerCancelRequest {
    schema_version: String,
    project_id: String,
    request_id: String,
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ViewerTextRequest {
    schema_version: String,
    project_id: String,
    selector: ViewerSelector,
    node_id: String,
    offset: u64,
}

impl ViewerTextRequest {
    fn source(&self) -> ViewerSourceRequest {
        ViewerSourceRequest {
            schema_version: self.schema_version.clone(),
            project_id: self.project_id.clone(),
            selector: self.selector.clone(),
        }
    }
    fn valid(&self) -> bool {
        self.source().valid()
            && self.selector.normalized_revision_id.is_some()
            && crate::supervisor::canonical_uuid_v7(&self.node_id)
            && self.offset <= 67_108_864
    }
}

fn text_matches(value: &Value, request: &ViewerTextRequest) -> bool {
    value.as_object().is_some_and(|fields| fields.len() == 7)
        && metadata_matches(&value["metadata"], &request.source())
        && value["nodeId"].as_str() == Some(request.node_id.as_str())
        && value["offset"].as_u64() == Some(request.offset)
        && value["text"]
            .as_str()
            .is_some_and(|text| text.chars().count() <= 4096)
        && (value["nextOffset"].is_null()
            || value["nextOffset"].as_u64()
                == value["text"]
                    .as_str()
                    .map(|text| request.offset + text.chars().count() as u64))
        && (value["pageNumber"].is_null()
            || value["pageNumber"]
                .as_u64()
                .is_some_and(|page| (1..=500).contains(&page)))
        && matches!(
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
}

#[tauri::command]
pub(crate) async fn document_viewer_text(
    window: tauri::WebviewWindow,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: ViewerTextRequest,
) -> Result<Option<Value>, ()> {
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
    let worker = Arc::clone(&connection);
    let selected = request.clone();
    let gate = lock.inner().clone();
    let owned_window = window.clone();
    let response = tauri::async_runtime::spawn_blocking(move || {
        let context = current_document_context(&worker, &selected.project_id).map_err(|_| ())?;
        worker.document_request_owned(NativeDocumentAction::ViewerText,
            json!({"root":worker.document_root(), "projectId":selected.project_id, "sessionId":context.session_id,
                "selector":selected.selector, "nodeId":selected.node_id, "offset":selected.offset}),
            &|| gate.finish_protected_action(ticket).is_ok() && crate::directory_window_handle(&owned_window) == Some(owner))
            .map_err(|_| ())
    }).await.map_err(|_| ())??;
    if !connection.is_current()
        || lock.finish_protected_action(ticket).is_err()
        || crate::directory_window_handle(&window) != Some(owner)
        || response.status != 200
        || response.content_type != "application/json"
        || response.body.len() > 32768
    {
        return Ok(None);
    }
    let value = serde_json::from_str::<Value>(&response.body).map_err(|_| ())?;
    if !text_matches(&value, &request) {
        return Ok(None);
    }
    lock.commit_protected_action(ticket, || {
        connection.publish_current(|| {
            if crate::directory_window_handle(&window) != Some(owner) {
                return Err("RO-DOCUMENT-VIEWER-DENIED");
            }
            Ok(Some(value))
        })
    })
    .map_err(|_| ())
}

struct PendingRange {
    owner: isize,
    connection: Arc<NativeImportConnection>,
    session: Mutex<Option<String>>,
    cancelled: AtomicBool,
    drained: AtomicBool,
}

type RequestKey = (String, String);

#[derive(Clone, Default)]
pub(crate) struct DocumentViewerManager {
    pending: Arc<Mutex<ViewerRequests>>,
}

#[derive(Default)]
struct ViewerRequests {
    active: BTreeMap<RequestKey, Arc<PendingRange>>,
    early_cancel: BTreeSet<(isize, RequestKey)>,
    cancellation_overflow: bool,
}

struct OwnedRequest {
    key: RequestKey,
    pending: Arc<PendingRange>,
    manager: DocumentViewerManager,
}

impl Drop for OwnedRequest {
    fn drop(&mut self) {
        self.pending.cancelled.store(true, Ordering::Release);
        if self
            .pending
            .session
            .lock()
            .is_ok_and(|session| session.is_none())
        {
            self.pending.drained.store(true, Ordering::Release);
        }
        // Unknown physical termination retains bounded admission ownership.
        // Dropping a native future cannot silently free an in-use Core read.
        if self.pending.drained.load(Ordering::Acquire)
            && let Ok(mut requests) = self.manager.pending.lock()
            && requests
                .active
                .get(&self.key)
                .is_some_and(|value| Arc::ptr_eq(value, &self.pending))
        {
            requests.active.remove(&self.key);
        }
    }
}

impl DocumentViewerManager {
    fn no_active_owner(&self, key: &RequestKey) -> bool {
        self.pending
            .lock()
            .is_ok_and(|requests| !requests.active.contains_key(key))
    }
    fn register(
        &self,
        key: RequestKey,
        owner: isize,
        connection: Arc<NativeImportConnection>,
    ) -> Result<OwnedRequest, bool> {
        let mut requests = self.pending.lock().map_err(|_| false)?;
        if requests.active.contains_key(&key) {
            return Err(false);
        }
        if requests.early_cancel.contains(&(owner, key.clone())) {
            // The original range itself observes this never-issued marker.
            // Keep it: a delayed duplicate cannot reuse the cancelled identity.
            return Err(true);
        }
        if requests.cancellation_overflow
            || requests.active.len() >= 64
            || requests
                .active
                .keys()
                .filter(|other| other.0 == key.0)
                .count()
                >= 9
        {
            return Err(true);
        }
        let pending = Arc::new(PendingRange {
            owner,
            connection,
            session: Mutex::new(None),
            cancelled: AtomicBool::new(false),
            drained: AtomicBool::new(false),
        });
        requests.active.insert(key.clone(), Arc::clone(&pending));
        Ok(OwnedRequest {
            key,
            pending,
            manager: self.clone(),
        })
    }

    fn cancel(&self, key: &RequestKey, owner: isize) -> Option<Arc<PendingRange>> {
        let mut requests = self.pending.lock().ok()?;
        let Some(pending) = requests.active.get(key).cloned() else {
            // Tauri may poll a cancellation before the already-issued range
            // future registers. Remember that exact owner/request without an
            // expiry that could admit delayed work. Overflow denies new work.
            if requests.early_cancel.len() < 256 {
                requests.early_cancel.insert((owner, key.clone()));
            } else {
                requests.cancellation_overflow = true;
            }
            return None;
        };
        if pending.owner != owner {
            return None;
        }
        pending.cancelled.store(true, Ordering::Release);
        // Preserve the cancelled identity even if it registered before its
        // current-context lookup, but never issued the Core range. Lease drop
        // may then prove no reader exists; a delayed duplicate still cannot run.
        if requests.early_cancel.len() < 256 {
            requests.early_cancel.insert((owner, key.clone()));
        } else {
            requests.cancellation_overflow = true;
        }
        Some(pending)
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct CoreDrainAck {
    schema_version: String,
    project_id: String,
    session_id: String,
    request_id: String,
    drained: bool,
}

fn drain_ack_matches(body: &str, key: &RequestKey, session: &str) -> bool {
    body.len() <= 8192
        && serde_json::from_str::<CoreDrainAck>(body).is_ok_and(|ack| {
            ack.schema_version == "1.0"
                && ack.project_id == key.0
                && ack.session_id == session
                && ack.request_id == key.1
                && ack.drained
        })
}

fn cancel_core(pending: &PendingRange, key: &RequestKey) -> bool {
    let Ok(session) = pending.session.lock().map(|value| value.clone()) else {
        return false;
    };
    if let Some(session) = session {
        let result = pending.connection.document_request(
            NativeDocumentAction::ViewerCancel,
            json!({"root":pending.connection.document_root(), "projectId":key.0,
                "sessionId":session, "requestId":key.1}),
        );
        return result.is_ok_and(|response| {
            response.status == 200
                && response.content_type == "application/json"
                && drain_ack_matches(&response.body, key, &session)
        });
    }
    // No Core range was issued; current-context lookup alone owns no source.
    true
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ViewerRangeFailure {
    schema_version: &'static str,
    project_id: String,
    request_id: String,
    drained: bool,
}

impl ViewerRangeFailure {
    fn new(request: &ViewerRangeRequest, drained: bool) -> Self {
        Self {
            schema_version: "1.0",
            project_id: request.project_id.clone(),
            request_id: request.request_id.clone(),
            drained,
        }
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct RangeResponse {
    schema_version: String,
    request_id: String,
    metadata: Value,
    start: u64,
    end: u64,
    bytes_base64: String,
}

fn metadata_matches(metadata: &Value, request: &ViewerSourceRequest) -> bool {
    let Some(fields) = metadata.as_object() else {
        return false;
    };
    if fields.len() != 2
        || !fields.contains_key("source")
        || !fields.contains_key("normalizedRevisionId")
    {
        return false;
    }
    let source = &metadata["source"];
    let Some(source_fields) = source.as_object() else {
        return false;
    };
    let identity_fields = [
        "attachmentId",
        "documentId",
        "documentRevisionId",
        "candidateId",
        "sourceAssertionRevisionId",
        "workId",
        "workRevisionId",
        "versionId",
        "versionRevisionId",
    ];
    if source_fields.len() != 14
        || identity_fields.iter().any(|key| {
            !source[*key]
                .as_str()
                .is_some_and(crate::supervisor::canonical_uuid_v7)
        })
        || !source["objectSha256"]
            .as_str()
            .is_some_and(canonical_digest)
        || !matches!(
            source["format"].as_str(),
            Some("pdf" | "jats" | "tei" | "xml" | "html" | "docx" | "plain-text")
        )
        || !source["provenance"].as_object().is_some_and(
            |origin| match source["provenance"]["kind"].as_str() {
                Some("local-import") => origin.len() == 1,
                Some("remote-acquisition") => {
                    origin.len() == 3
                        && source["provenance"]["locationId"]
                            .as_str()
                            .is_some_and(crate::supervisor::canonical_uuid_v7)
                        && source["provenance"]["receiptSha256"]
                            .as_str()
                            .is_some_and(canonical_digest)
                }
                _ => false,
            },
        )
    {
        return false;
    }
    source["projectId"].as_str() == Some(request.project_id.as_str())
        && source["attachmentId"].as_str() == Some(request.selector.attachment_id.as_str())
        && source["documentRevisionId"].as_str()
            == Some(request.selector.document_revision_id.as_str())
        && source["byteLength"]
            .as_u64()
            .is_some_and(|length| length > 0 && length <= MAX_SOURCE)
        && metadata["normalizedRevisionId"] == json!(request.selector.normalized_revision_id)
}

fn canonical_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn decode_range(body: &str, request: &ViewerRangeRequest) -> Result<Vec<u8>, ()> {
    if !request.valid() || body.len() > MAX_RESPONSE {
        return Err(());
    }
    let response: RangeResponse = serde_json::from_str(body).map_err(|_| ())?;
    let source_request = ViewerSourceRequest {
        schema_version: request.schema_version.clone(),
        project_id: request.project_id.clone(),
        selector: request.selector.clone(),
    };
    if response.schema_version != "1.0"
        || response.request_id != request.request_id
        || (response.start, response.end) != (request.start, request.end)
        || !metadata_matches(&response.metadata, &source_request)
        || !response.metadata["source"]["byteLength"]
            .as_u64()
            .is_some_and(|length| request.end <= length)
        || response.bytes_base64.len() > 1_398_104
    {
        return Err(());
    }
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(response.bytes_base64)
        .map_err(|_| ())?;
    if bytes.len() as u64 != request.end - request.start {
        return Err(());
    }
    Ok(bytes)
}

#[tauri::command]
pub(crate) async fn document_viewer_source(
    window: tauri::WebviewWindow,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: ViewerSourceRequest,
) -> Result<Option<Value>, ()> {
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
    let worker = Arc::clone(&connection);
    let selected = request.clone();
    let gate = lock.inner().clone();
    let owned_window = window.clone();
    let response = tauri::async_runtime::spawn_blocking(move || {
        let context = current_document_context(&worker, &selected.project_id).map_err(|_| ())?;
        worker
            .document_request_owned(
                NativeDocumentAction::ViewerSource,
                json!({"root":worker.document_root(), "projectId":selected.project_id,
                "sessionId":context.session_id, "selector":selected.selector}),
                &|| {
                    gate.finish_protected_action(ticket).is_ok()
                        && crate::directory_window_handle(&owned_window) == Some(owner)
                },
            )
            .map_err(|_| ())
    })
    .await
    .map_err(|_| ())??;
    if !connection.is_current()
        || lock.finish_protected_action(ticket).is_err()
        || crate::directory_window_handle(&window) != Some(owner)
        || response.status != 200
        || response.content_type != "application/json"
        || response.body.len() > 8192
    {
        return Ok(None);
    }
    let value = serde_json::from_str::<Value>(&response.body).map_err(|_| ())?;
    if !metadata_matches(&value, &request) {
        return Ok(None);
    }
    lock.commit_protected_action(ticket, || {
        connection.publish_current(|| {
            if crate::directory_window_handle(&window) != Some(owner) {
                return Err("RO-DOCUMENT-VIEWER-DENIED");
            }
            Ok(Some(value))
        })
    })
    .map_err(|_| ())
}

#[tauri::command]
pub(crate) async fn document_viewer_range(
    window: tauri::WebviewWindow,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    manager: State<'_, DocumentViewerManager>,
    request: ViewerRangeRequest,
) -> Result<tauri::ipc::Response, ViewerRangeFailure> {
    let denied = |drained| ViewerRangeFailure::new(&request, drained);
    let key = (request.project_id.clone(), request.request_id.clone());
    if !request.valid() {
        return Err(denied(manager.no_active_owner(&key)));
    }
    let owner = crate::directory_window_handle(&window)
        .ok_or_else(|| denied(manager.no_active_owner(&key)))?;
    let ticket = lock
        .begin_protected_action()
        .map_err(|_| denied(manager.no_active_owner(&key)))?;
    let connection = Arc::new(
        supervisor
            .native_document_connection(&request.project_id)
            .map_err(|_| denied(manager.no_active_owner(&key)))?,
    );
    let lease = manager
        .register(
            (request.project_id.clone(), request.request_id.clone()),
            owner,
            Arc::clone(&connection),
        )
        .map_err(denied)?;
    let pending = Arc::clone(&lease.pending);
    let selected = request.clone();
    let gate = lock.inner().clone();
    let owned_window = window.clone();
    let (result, drained) = tauri::async_runtime::spawn_blocking(move || {
        let result = (|| {
            let context = current_document_context(&pending.connection, &selected.project_id).map_err(|_| ())?;
            {
                let mut session = pending.session.lock().map_err(|_| ())?;
                if pending.cancelled.load(Ordering::Acquire) { return Err(()); }
                *session = Some(context.session_id.clone());
            }
            let response = pending.connection.document_request_owned(NativeDocumentAction::ViewerRange,
                json!({"root":pending.connection.document_root(), "projectId":selected.project_id,
                    "sessionId":context.session_id, "selector":selected.selector,
                    "requestId":selected.request_id, "start":selected.start, "end":selected.end}),
                &|| !pending.cancelled.load(Ordering::Acquire) && gate.finish_protected_action(ticket).is_ok()
                    && crate::directory_window_handle(&owned_window) == Some(owner)).map_err(|_| ())?;
            if response.status != 200 || response.content_type != "application/json" { return Err(()); }
            decode_range(&response.body, &selected)
        })();
        let drained = result.is_ok() || cancel_core(&pending, &(selected.project_id, selected.request_id));
        pending.drained.store(drained, Ordering::Release);
        (result, drained)
    }).await.map_err(|_| denied(false))?;
    let bytes = result.map_err(|_| denied(drained))?;
    if !connection.is_current()
        || lease.pending.cancelled.load(Ordering::Acquire)
        || lock.finish_protected_action(ticket).is_err()
        || crate::directory_window_handle(&window) != Some(owner)
    {
        return Err(denied(true));
    }
    // Raw IPC byte delivery avoids a renderer-side base64/source-sized copy.
    lock.commit_protected_action(ticket, || {
        connection.publish_current(|| {
            if lease.pending.cancelled.load(Ordering::Acquire)
                || crate::directory_window_handle(&window) != Some(owner)
            {
                return Err("RO-DOCUMENT-VIEWER-DENIED");
            }
            Ok(tauri::ipc::Response::new(bytes))
        })
    })
    .map_err(|_| denied(true))
}

#[tauri::command]
pub(crate) async fn document_viewer_cancel(
    window: tauri::WebviewWindow,
    manager: State<'_, DocumentViewerManager>,
    request: ViewerCancelRequest,
) -> Result<(), ()> {
    if request.schema_version != "1.0"
        || !crate::supervisor::canonical_project_id(&request.project_id)
        || !crate::supervisor::canonical_uuid_v7(&request.request_id)
    {
        return Err(());
    }
    let owner = crate::directory_window_handle(&window).ok_or(())?;
    let key = (request.project_id, request.request_id);
    // Stop only. The original range IPC carries its independently established
    // terminal disposition after the owning native worker acknowledges Core.
    let _ = manager.cancel(&key, owner);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request() -> ViewerRangeRequest {
        serde_json::from_value(json!({"schemaVersion":"1.0", "projectId":"00000000-0000-7000-8000-000000000001",
            "requestId":"00000000-0000-7000-8000-000000000002", "selector":{
                "attachmentId":"00000000-0000-7000-8000-000000000003",
                "documentRevisionId":"00000000-0000-7000-8000-000000000004", "normalizedRevisionId":null},
            "start":0, "end":4})).unwrap()
    }

    fn response(request: &ViewerRangeRequest) -> Value {
        let id = "00000000-0000-7000-8000-000000000008";
        json!({"schemaVersion":"1.0", "requestId":request.request_id, "start":0, "end":4,
            "metadata":{"source":{"projectId":request.project_id, "attachmentId":request.selector.attachment_id,
                "documentRevisionId":request.selector.document_revision_id, "byteLength":32,
                "documentId":id, "candidateId":id, "sourceAssertionRevisionId":id, "workId":id,
                "workRevisionId":id, "versionId":id, "versionRevisionId":id,
                "objectSha256":"a".repeat(64), "format":"pdf", "provenance":{"kind":"local-import"}},
                "normalizedRevisionId":null},
            "bytesBase64":"AAECAw=="})
    }

    #[test]
    fn bounded_binary_response_is_exact_and_substitution_denies() {
        let selected = request();
        let value = response(&selected);
        assert_eq!(
            decode_range(&value.to_string(), &selected).unwrap(),
            vec![0, 1, 2, 3]
        );
        for field in ["requestId", "schemaVersion", "start", "end", "bytesBase64"] {
            let mut changed = value.clone();
            changed[field] = json!("substituted");
            assert!(decode_range(&changed.to_string(), &selected).is_err());
        }
        let mut changed = value;
        changed["metadata"]["source"]["attachmentId"] = json!(selected.request_id);
        assert!(decode_range(&changed.to_string(), &selected).is_err());
    }

    #[test]
    fn renderer_authority_and_noninteger_ranges_are_rejected() {
        let selected = request();
        assert!(selected.valid());
        let base = json!({"schemaVersion":selected.schema_version, "projectId":selected.project_id,
            "selector":selected.selector, "requestId":selected.request_id, "start":0, "end":4});
        for field in ["root", "sessionId", "actorId", "url", "path", "rights"] {
            let mut changed = base.clone();
            changed[field] = json!("untrusted");
            assert!(serde_json::from_value::<ViewerRangeRequest>(changed).is_err());
        }
        for value in [json!(true), json!(1.5), json!(-1)] {
            let mut changed = base.clone();
            changed["start"] = value;
            assert!(serde_json::from_value::<ViewerRangeRequest>(changed).is_err());
        }
    }

    #[test]
    fn structured_text_is_correlated_and_bounded_before_delivery() {
        let mut range = request();
        range.selector.normalized_revision_id = Some("00000000-0000-7000-8000-000000000009".into());
        let request = ViewerTextRequest {
            schema_version: range.schema_version.clone(),
            project_id: range.project_id.clone(),
            selector: range.selector.clone(),
            node_id: range.request_id.clone(),
            offset: 0,
        };
        let mut metadata = response(&range)["metadata"].clone();
        metadata["normalizedRevisionId"] = json!(range.selector.normalized_revision_id);
        let value = json!({"metadata":metadata, "nodeId":request.node_id, "nodeKind":"paragraph", "pageNumber":1, "offset":0, "text":"Synthetic", "nextOffset":null});
        assert!(request.valid());
        assert!(text_matches(&value, &request));
        for field in ["nodeId", "nodeKind", "offset", "pageNumber", "nextOffset"] {
            let mut substituted = value.clone();
            substituted[field] = json!("substituted");
            assert!(!text_matches(&substituted, &request));
        }
        let mut oversized = value.clone();
        oversized["text"] = json!("x".repeat(4097));
        assert!(!text_matches(&oversized, &request));
        let mut injected = value;
        injected["path"] = json!("untrusted");
        assert!(!text_matches(&injected, &request));
    }

    #[test]
    fn native_cancel_is_bound_to_window_project_request_and_capacity() {
        let manager = DocumentViewerManager::default();
        let project = request().project_id;
        let connection = Arc::new(NativeImportConnection::unavailable_for_attachment_test(
            &project,
        ));
        let key = (project, request().request_id);
        let lease = manager
            .register(key.clone(), 42, Arc::clone(&connection))
            .unwrap();
        assert!(manager.cancel(&key, 43).is_none());
        assert!(manager.register(key.clone(), 42, connection).is_err());
        assert!(!lease.pending.cancelled.load(Ordering::Acquire));
        assert!(manager.cancel(&key, 42).is_some());
        assert!(lease.pending.cancelled.load(Ordering::Acquire));
        drop(lease);
        assert!(manager.cancel(&key, 42).is_none());
    }

    #[test]
    fn cancellation_before_registration_cannot_admit_delayed_owned_work() {
        let manager = DocumentViewerManager::default();
        let project = request().project_id;
        let connection = Arc::new(NativeImportConnection::unavailable_for_attachment_test(
            &project,
        ));
        let key = (project, request().request_id);
        assert!(manager.cancel(&key, 42).is_none());
        // A different window's independent request remains admissible.
        let other = manager
            .register(key.clone(), 43, Arc::clone(&connection))
            .unwrap();
        drop(other);
        assert!(
            manager
                .register(key.clone(), 42, Arc::clone(&connection))
                .is_err()
        );
        assert!(manager.register(key, 42, connection).is_err());
    }

    #[test]
    fn drain_ack_is_exact_and_unknown_owned_termination_retains_admission() {
        let request = request();
        let key = (request.project_id, request.request_id);
        let ack = json!({"schemaVersion":"1.0", "projectId":key.0,
            "sessionId":"native-session", "requestId":key.1, "drained":true});
        assert!(drain_ack_matches(&ack.to_string(), &key, "native-session"));
        for field in [
            "schemaVersion",
            "projectId",
            "sessionId",
            "requestId",
            "drained",
        ] {
            let mut changed = ack.clone();
            changed[field] = json!("substituted");
            assert!(!drain_ack_matches(
                &changed.to_string(),
                &key,
                "native-session"
            ));
        }
        let mut pending_ack = ack.clone();
        pending_ack["drained"] = json!(false);
        assert!(!drain_ack_matches(
            &pending_ack.to_string(),
            &key,
            "native-session"
        ));
        let mut injected = ack;
        injected["root"] = json!("untrusted");
        assert!(!drain_ack_matches(
            &injected.to_string(),
            &key,
            "native-session"
        ));

        let manager = DocumentViewerManager::default();
        let connection = Arc::new(NativeImportConnection::unavailable_for_attachment_test(
            &key.0,
        ));
        let lease = manager
            .register(key.clone(), 42, Arc::clone(&connection))
            .unwrap();
        *lease.pending.session.lock().unwrap() = Some("native-session".into());
        drop(lease);
        assert!(manager.register(key.clone(), 42, connection).is_err());
        assert!(manager.cancel(&key, 42).is_some());
    }

    #[test]
    fn cancelled_registered_but_never_issued_identity_cannot_be_replayed() {
        let manager = DocumentViewerManager::default();
        let request = request();
        let key = (request.project_id, request.request_id);
        let connection = Arc::new(NativeImportConnection::unavailable_for_attachment_test(
            &key.0,
        ));
        let lease = manager
            .register(key.clone(), 42, Arc::clone(&connection))
            .unwrap();
        assert!(lease.pending.session.lock().unwrap().is_none());
        assert!(manager.cancel(&key, 42).is_some());
        drop(lease);
        assert!(manager.register(key, 42, connection).is_err());
    }

    #[test]
    fn cancelled_active_or_unknown_owner_never_returns_a_drained_duplicate_verdict() {
        let manager = DocumentViewerManager::default();
        let request = request();
        let key = (request.project_id, request.request_id);
        let connection = Arc::new(NativeImportConnection::unavailable_for_attachment_test(
            &key.0,
        ));
        let lease = manager
            .register(key.clone(), 42, Arc::clone(&connection))
            .unwrap();
        *lease.pending.session.lock().unwrap() = Some("native-session".into());
        assert!(manager.cancel(&key, 42).is_some());
        assert!(!manager.no_active_owner(&key));
        assert!(matches!(
            manager.register(key.clone(), 42, Arc::clone(&connection)),
            Err(false)
        ));
        drop(lease);
        assert!(matches!(
            manager.register(key.clone(), 42, Arc::clone(&connection)),
            Err(false)
        ));

        let closed_key = (key.0.clone(), "00000000-0000-7000-8000-000000000009".into());
        let closed = manager
            .register(closed_key.clone(), 42, Arc::clone(&connection))
            .unwrap();
        *closed.pending.session.lock().unwrap() = Some("native-session".into());
        assert!(manager.cancel(&closed_key, 42).is_some());
        closed.pending.drained.store(true, Ordering::Release);
        drop(closed);
        assert!(matches!(
            manager.register(closed_key, 42, connection),
            Err(true)
        ));
    }
}
