//! Fixed, native-owned attachment actions. Renderer IPC carries exact IDs only.

use crate::application_lock::ApplicationLockManager;
use crate::directory_picker::{DirectoryPickerManager, PickerFailure};
use crate::document_runtime::{self, DocumentSelection, DocumentStageOutcome};
use crate::import_source::HeldImportSource;
use crate::supervisor::{NativeDocumentAction, NativeImportConnection, RuntimeSupervisor};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::sync::{Arc, Mutex};
use tauri::{Emitter, Manager, State};

const RESULT_EVENT: &str = "document_attachment_result";

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct CoreCopyLocation {
    location_id: String,
    project_id: String,
    source_assertion_revision_id: String,
    source_revision_id: String,
    address: Value,
    source_sha256: String,
    provider: String,
    location_key: String,
    url: String,
    license: Option<String>,
    version: Option<String>,
    location_sha256: String,
}

impl CoreCopyLocation {
    fn safe_metadata(&self, selection: &AttachmentSelection) -> Option<Value> {
        let url = tauri::Url::parse(&self.url).ok()?;
        let host = url.host_str()?;
        (self.project_id == selection.project_id
            && self.source_assertion_revision_id == selection.source_assertion_revision_id
            && crate::supervisor::canonical_uuid_v7(&self.location_id)
            && crate::supervisor::canonical_uuid_v7(&self.source_revision_id)
            && lower_hex(&self.location_sha256, 64)
            && lower_hex(&self.source_sha256, 64)
            && self.address.is_object()
            && !self.location_key.is_empty()
            && self.location_key.len() <= 128
            && url.scheme() == "https"
            && url.username().is_empty()
            && url.password().is_none()
            && url.fragment().is_none()
            && self.url.len() <= 8192
            && host.len() <= 253
            && self.provider.len() <= 64
            && self.license.as_ref().is_none_or(|s| s.len() <= 4096)
            && self.version.as_ref().is_none_or(|s| s.len() <= 256))
        .then(|| {
            json!({"copyId":self.location_id,"copySha256":self.location_sha256,
            "provider":self.provider,"host":host,"license":self.license,"version":self.version})
        })
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct CoreCopies {
    locations: Vec<CoreCopyLocation>,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct RetainedCandidate {
    candidate_id: String,
    source_name: String,
    original_operation_id: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CoreRetained {
    retained: Vec<RetainedCandidate>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct CoreCopyPreview {
    preview_id: String,
    location: CoreCopyLocation,
    selection: Value,
    provider_policy_revision_id: String,
    confirmation_sha256: String,
    confirmation: String,
}

struct NativeCopyReview {
    preview: CoreCopyPreview,
    selection: AttachmentSelection,
    session_id: String,
    connection: Arc<NativeImportConnection>,
    owner: isize,
    ticket: u64,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct CopiesRequest {
    schema_version: String,
    selection: AttachmentSelection,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct CopyReviewRequest {
    schema_version: String,
    selection: AttachmentSelection,
    copy_id: String,
    copy_sha256: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct CopyDownloadRequest {
    schema_version: String,
    selection: AttachmentSelection,
    review_id: String,
    operation_id: String,
    match_confirmed: bool,
    permitted_use: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct CandidateRecoveryRequest {
    schema_version: String,
    selection: AttachmentSelection,
    operation_id: String,
    candidate_id: String,
    original_operation_id: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct AccessNeedRequest {
    schema_version: String,
    selection: AttachmentSelection,
    copy_id: Option<String>,
    copy_sha256: Option<String>,
    command_id: String,
    kind: String,
    channel: String,
}

fn association_fields(selection: &AttachmentSelection) -> Value {
    let mut fields = selection.core_fields();
    fields.as_object_mut().unwrap().remove("projectId");
    fields
}

fn copy_core_selection(selection: &AttachmentSelection, copy_id: &str, copy_sha256: &str) -> Value {
    let mut result = selection.core_fields();
    result.as_object_mut().unwrap().remove("projectId");
    result["locationId"] = copy_id.into();
    result["locationSha256"] = copy_sha256.into();
    result["expectedSha256"] = Value::Null;
    result["redirectHosts"] = json!([]);
    result
}

fn json_core_response<T: serde::de::DeserializeOwned>(
    response: crate::supervisor::CoreApiResponse,
) -> Result<T, ()> {
    if response.status != 200
        || response.content_type != "application/json"
        || response.body.len() > 262_144
    {
        return Err(());
    }
    serde_json::from_str(&response.body).map_err(|_| ())
}

#[tauri::command]
pub(crate) async fn document_acquisition_copies(
    window: tauri::WebviewWindow,
    manager: State<'_, DocumentAttachmentManager>,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: CopiesRequest,
) -> Result<Option<Value>, ()> {
    if request.schema_version != "1.0" || !request.selection.valid() || !manager.installed() {
        return Ok(None);
    }
    let owner = crate::directory_window_handle(&window).ok_or(())?;
    let ticket = lock.begin_protected_action().map_err(|_| ())?;
    let connection = Arc::new(
        supervisor
            .native_document_connection(&request.selection.project_id)
            .map_err(|_| ())?,
    );
    let worker = Arc::clone(&connection);
    let project = request.selection.project_id.clone();
    let source = request.selection.source_assertion_revision_id.clone();
    let association = association_fields(&request.selection);
    let (copies, retained): (CoreCopies, CoreRetained) = tauri::async_runtime::spawn_blocking(move || {
        let context = document_runtime::current_document_context(&worker, &project).map_err(|_| ())?;
        let copies = json_core_response(worker.document_request(NativeDocumentAction::Copies,
            json!({"root":worker.document_root(),"projectId":project,"sessionId":context.session_id,
                "sourceAssertionRevisionId":source})).map_err(|_| ())?)?;
        let retained = json_core_response(worker.document_request(NativeDocumentAction::Retained,
            json!({"root":worker.document_root(),"projectId":project,"sessionId":context.session_id,
                "selection":association})).map_err(|_| ())?)?;
        Ok::<_, ()>((copies, retained))
    }).await.map_err(|_| ())??;
    if !connection.is_current()
        || lock.finish_protected_action(ticket).is_err()
        || crate::directory_window_handle(&window) != Some(owner)
        || copies.locations.len() > 100
        || retained.retained.len() > 50
        || retained.retained.iter().any(|candidate| {
            !crate::supervisor::canonical_uuid_v7(&candidate.candidate_id)
                || !crate::supervisor::canonical_uuid_v7(&candidate.original_operation_id)
                || !safe_name(&candidate.source_name)
        })
    {
        return Ok(None);
    }
    let metadata: Option<Vec<Value>> = copies
        .locations
        .iter()
        .map(|copy| copy.safe_metadata(&request.selection))
        .collect();
    Ok(metadata.map(|copies| json!({"schemaVersion":"1.0","selection":request.selection,"copies":copies,"retained":retained.retained})))
}

#[tauri::command]
pub(crate) async fn document_acquisition_access_need(
    window: tauri::WebviewWindow,
    manager: State<'_, DocumentAttachmentManager>,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: AccessNeedRequest,
) -> Result<Option<Value>, ()> {
    if request.schema_version != "1.0"
        || !request.selection.valid()
        || !manager.installed()
        || !crate::supervisor::canonical_uuid_v7(&request.command_id)
        || request.copy_id.is_some() != request.copy_sha256.is_some()
        || request
            .copy_id
            .as_ref()
            .is_some_and(|id| !crate::supervisor::canonical_uuid_v7(id))
        || request
            .copy_sha256
            .as_ref()
            .is_some_and(|sha| !lower_hex(sha, 64))
        || ![
            "unknown",
            "unavailable",
            "rights-denied",
            "entitlement-required",
        ]
        .contains(&request.kind.as_str())
        || !["manual", "institutional"].contains(&request.channel.as_str())
    {
        return Ok(None);
    }
    let owner = crate::directory_window_handle(&window).ok_or(())?;
    let ticket = lock.begin_protected_action().map_err(|_| ())?;
    let connection = Arc::new(
        supervisor
            .native_document_connection(&request.selection.project_id)
            .map_err(|_| ())?,
    );
    let worker = Arc::clone(&connection);
    let project = request.selection.project_id.clone();
    let mut selection = association_fields(&request.selection);
    selection["locationId"] = json!(request.copy_id);
    selection["locationSha256"] = json!(request.copy_sha256);
    let command_id = request.command_id.clone();
    let worker_lock = lock.inner().clone();
    let worker_window = window.clone();
    let result: Value = tauri::async_runtime::spawn_blocking(move || {
        let context = document_runtime::current_document_context(&worker, &project).map_err(|_| ())?;
        json_core_response(worker.document_request_owned(NativeDocumentAction::AccessNeed,
            json!({"root":worker.document_root(),"projectId":project,"sessionId":context.session_id,
                "selection":selection,"commandId":command_id,"kind":request.kind,"channel":request.channel}),
            &|| worker.is_current() && worker_lock.finish_protected_action(ticket).is_ok()
                && crate::directory_window_handle(&worker_window) == Some(owner)).map_err(|_| ())?)
    }).await.map_err(|_| ())??;
    if !connection.is_current()
        || lock.finish_protected_action(ticket).is_err()
        || crate::directory_window_handle(&window) != Some(owner)
        || result.as_object().is_none_or(|value| value.len() != 5)
        || !result["annotationId"]
            .as_str()
            .is_some_and(crate::supervisor::canonical_uuid_v7)
        || !result["revisionId"]
            .as_str()
            .is_some_and(crate::supervisor::canonical_uuid_v7)
    {
        return Ok(None);
    }
    Ok(Some(
        json!({"schemaVersion":"1.0","status":"recorded","commandId":request.command_id}),
    ))
}

fn decode_remote_candidate(
    response: crate::supervisor::CoreApiResponse,
    active: &ActiveAttachment,
) -> Result<DocumentStageOutcome, PickerFailure> {
    if response.status != 200 {
        return document_runtime::decode_stage_response(response, None, &active.document, "");
    }
    let candidate: document_runtime::DocumentCandidate =
        json_core_response(response).map_err(|_| PickerFailure::Failed)?;
    if candidate.project_id != active.selection.project_id
        || candidate.source_assertion_revision_id != active.selection.source_assertion_revision_id
        || candidate.work_id != active.selection.work_id
        || candidate.work_revision_id != active.selection.work_revision_id
        || candidate.version_id != active.selection.version_id
        || candidate.version_revision_id != active.selection.version_revision_id
        || !crate::supervisor::canonical_uuid_v7(&candidate.candidate_id)
        || !lower_hex(&candidate.candidate_sha256, 64)
        || !lower_hex(&candidate.object_sha256, 64)
        || !candidate.confirmation_required
        || !candidate.rights_subject.is_object()
    {
        return Err(PickerFailure::Failed);
    }
    Ok(DocumentStageOutcome::Candidate(candidate))
}

#[tauri::command]
pub(crate) async fn document_acquisition_recover(
    window: tauri::WebviewWindow,
    manager: State<'_, DocumentAttachmentManager>,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: CandidateRecoveryRequest,
) -> Result<Value, ()> {
    let unavailable = || begin_outcome(&request.operation_id, "unavailable", None);
    if request.schema_version != "1.0"
        || !request.selection.valid()
        || !manager.installed()
        || [
            &request.operation_id,
            &request.candidate_id,
            &request.original_operation_id,
        ]
        .iter()
        .any(|id| !crate::supervisor::canonical_uuid_v7(id))
        || request.operation_id == request.original_operation_id
    {
        return Ok(unavailable());
    }
    let owner = crate::directory_window_handle(&window).ok_or(())?;
    let ticket = lock.begin_protected_action().map_err(|_| ())?;
    let connection = Arc::new(
        supervisor
            .native_document_connection(&request.selection.project_id)
            .map_err(|_| ())?,
    );
    let worker = Arc::clone(&connection);
    let project = request.selection.project_id.clone();
    let context = tauri::async_runtime::spawn_blocking(move || {
        document_runtime::current_document_context(&worker, &project)
    })
    .await
    .map_err(|_| ())?
    .map_err(|_| ())?;
    if !connection.is_current()
        || lock.finish_protected_action(ticket).is_err()
        || crate::directory_window_handle(&window) != Some(owner)
    {
        return Ok(unavailable());
    }
    {
        let mut state = manager.shared.lock().map_err(|_| ())?;
        if let Some(old) = state.active.as_ref() {
            if old.selection != request.selection
                || old
                    .candidate
                    .as_ref()
                    .is_none_or(|candidate| candidate.0 != request.candidate_id)
                || old.commit_request.is_some()
                || old.staging
                || old.cancelling
            {
                return Ok(unavailable());
            }
            // Task Center navigation retains the inspected copy. Re-review
            // releases only this exact native binding, without cancelling the
            // immutable candidate or reviving its earlier confirmation.
            state.generation = state.generation.saturating_add(1);
            state.active = None;
        }
    }
    let active = ActiveAttachment {
        operation_id: request.operation_id.clone(),
        mode: AttachmentMode::Remote,
        selection: request.selection.clone(),
        document: request.selection.document(
            connection.document_root().into(),
            request.operation_id.clone(),
        ),
        session_id: context.session_id.clone(),
        owner,
        ticket,
        connection,
        candidate: None,
        commit_request: None,
        generation: 0,
        staging: true,
        cancelling: false,
    };
    if !manager.activate(active) {
        return Ok(unavailable());
    }
    let active = manager.current(&request.operation_id).ok_or(())?;
    let worker_manager = manager.inner().clone();
    let worker_window = window.clone();
    let worker_lock = lock.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let authorized = || {
            worker_manager.current(&active.operation_id).is_some()
                && active.connection.is_current()
                && worker_lock.finish_protected_action(active.ticket).is_ok()
                && crate::directory_window_handle(&worker_window) == Some(owner)
        };
        let outcome = (|| {
            let original = active.connection.document_request_owned(NativeDocumentAction::Candidate,
                json!({"root":active.connection.document_root(),"projectId":active.selection.project_id,
                    "sessionId":active.session_id,"candidateId":request.candidate_id}), &authorized).map_err(|_| PickerFailure::Unavailable)?;
            let DocumentStageOutcome::Candidate(candidate) =
                decode_remote_candidate(original, &active)?
            else {
                return Err(PickerFailure::Failed);
            };
            if candidate.candidate_id != request.candidate_id {
                return Err(PickerFailure::Failed);
            }
            let response = active.connection.document_request_owned(NativeDocumentAction::Recover,
                json!({"root":active.connection.document_root(),"projectId":active.selection.project_id,
                    "sessionId":active.session_id,"candidateId":request.candidate_id,"originalOperationId":request.original_operation_id,
                    "recoveryOperationId":active.operation_id,"confirmationSha256":candidate.candidate_sha256,
                    "selection":association_fields(&active.selection)}), &authorized).map_err(|_| PickerFailure::Unavailable)?;
            let recovered = decode_remote_candidate(response, &active)?;
            if let DocumentStageOutcome::Candidate(returned) = &recovered {
                if returned.candidate_id != candidate.candidate_id
                    || returned.candidate_sha256 != candidate.candidate_sha256
                    || returned.object_sha256 != candidate.object_sha256
                {
                    return Err(PickerFailure::Failed);
                }
            }
            Ok(recovered)
        })();
        finish_stage(&worker_manager, &worker_window, &active, outcome);
    });
    Ok(begin_outcome(
        &request.operation_id,
        "armed",
        Some(&context.session_id),
    ))
}

#[tauri::command]
pub(crate) async fn document_acquisition_review(
    window: tauri::WebviewWindow,
    manager: State<'_, DocumentAttachmentManager>,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: CopyReviewRequest,
) -> Result<Option<Value>, ()> {
    if request.schema_version != "1.0"
        || !request.selection.valid()
        || !manager.installed()
        || !crate::supervisor::canonical_uuid_v7(&request.copy_id)
        || !lower_hex(&request.copy_sha256, 64)
    {
        return Ok(None);
    }
    let owner = crate::directory_window_handle(&window).ok_or(())?;
    let ticket = lock.begin_protected_action().map_err(|_| ())?;
    let generation = {
        let mut state = manager.shared.lock().map_err(|_| ())?;
        if state
            .active
            .as_ref()
            .is_some_and(|active| active.connection.is_current())
        {
            return Ok(None);
        }
        state.generation = state.generation.saturating_add(1);
        state.review = None;
        state.generation
    };
    let connection = Arc::new(
        supervisor
            .native_document_connection(&request.selection.project_id)
            .map_err(|_| ())?,
    );
    let worker = Arc::clone(&connection);
    let project = request.selection.project_id.clone();
    let selection = copy_core_selection(&request.selection, &request.copy_id, &request.copy_sha256);
    let expected = selection.clone();
    let (session_id, preview): (String, CoreCopyPreview) =
        tauri::async_runtime::spawn_blocking(move || {
            let context =
                document_runtime::current_document_context(&worker, &project).map_err(|_| ())?;
            let preview = json_core_response(worker.document_request(NativeDocumentAction::Preview,
            json!({"root":worker.document_root(),"projectId":project,"sessionId":context.session_id,
                "selection":selection})).map_err(|_| ())?)?;
            Ok::<_, ()>((context.session_id, preview))
        })
        .await
        .map_err(|_| ())??;
    if !connection.is_current()
        || lock.finish_protected_action(ticket).is_err()
        || crate::directory_window_handle(&window) != Some(owner)
        || preview.selection != expected
        || !crate::supervisor::canonical_uuid_v7(&preview.preview_id)
        || !crate::supervisor::canonical_uuid_v7(&preview.provider_policy_revision_id)
        || !lower_hex(&preview.confirmation_sha256, 64)
        || !preview
            .confirmation
            .starts_with(&format!("acquire-copy:{}:", preview.preview_id))
        || !lower_hex(preview.confirmation.rsplit(':').next().unwrap_or(""), 32)
        || preview.location.location_id != request.copy_id
        || preview.location.location_sha256 != request.copy_sha256
    {
        return Ok(None);
    }
    let copy = preview
        .location
        .safe_metadata(&request.selection)
        .ok_or(())?;
    let output = json!({"schemaVersion":"1.0","selection":request.selection,"reviewId":preview.preview_id,
        "copy":copy,"redirectHosts":[],"storeInspect":"allowed","egress":"confirmed-preview-required"});
    lock.commit_protected_action(ticket, || {
        let mut state = manager
            .shared
            .lock()
            .map_err(|_| "RO-DOCUMENT-STATE-UNAVAILABLE")?;
        if state.generation != generation
            || !state.installed
            || !connection.is_current()
            || crate::directory_window_handle(&window) != Some(owner)
        {
            return Err("RO-DOCUMENT-SESSION-UNAVAILABLE");
        }
        state.review = Some(NativeCopyReview {
            preview,
            selection: request.selection,
            session_id,
            connection,
            owner,
            ticket,
        });
        Ok(())
    })
    .map_err(|_| ())?;
    Ok(Some(output))
}

#[tauri::command]
pub(crate) fn document_acquisition_clear_review(manager: State<'_, DocumentAttachmentManager>) {
    if let Ok(mut state) = manager.shared.lock() {
        if state.active.is_none() {
            state.generation = state.generation.saturating_add(1);
            state.review = None;
        }
    }
}

fn consume_copy_review(
    manager: &DocumentAttachmentManager,
    lock: &ApplicationLockManager,
    request: &CopyDownloadRequest,
    owner: Option<isize>,
    snapshot: (u64, u64),
) -> Result<NativeCopyReview, &'static str> {
    let (ticket, generation) = snapshot;
    // Match review publication and late stage completion: application lock
    // first, then attachment state.
    lock.commit_protected_action(ticket, || {
        let mut state = manager
            .shared
            .lock()
            .map_err(|_| "RO-DOCUMENT-STATE-UNAVAILABLE")?;
        let Some(review) = state.review.as_ref() else {
            return Err("RO-DOCUMENT-SESSION-UNAVAILABLE");
        };
        if review.preview.preview_id != request.review_id
            || review.selection != request.selection
            || review.ticket != ticket
            || state.generation != generation
            || !state.installed
            || state.active.is_some()
            || !review.connection.is_current()
            || owner != Some(review.owner)
        {
            return Err("RO-DOCUMENT-SESSION-UNAVAILABLE");
        }
        Ok(state.review.take().unwrap())
    })
}

#[tauri::command]
pub(crate) async fn document_acquisition_download(
    window: tauri::WebviewWindow,
    manager: State<'_, DocumentAttachmentManager>,
    lock: State<'_, ApplicationLockManager>,
    request: CopyDownloadRequest,
) -> Result<Value, ()> {
    let unavailable = || begin_outcome(&request.operation_id, "unavailable", None);
    if request.schema_version != "1.0"
        || !request.selection.valid()
        || !crate::supervisor::canonical_uuid_v7(&request.operation_id)
        || !request.match_confirmed
        || request.permitted_use != "project-only"
    {
        return Ok(unavailable());
    }
    let (ticket, generation) = {
        let state = manager.shared.lock().map_err(|_| ())?;
        let Some(review) = state.review.as_ref() else {
            return Ok(unavailable());
        };
        (review.ticket, state.generation)
    };
    let review = consume_copy_review(
        &manager,
        &lock,
        &request,
        crate::directory_window_handle(&window),
        (ticket, generation),
    );
    let Ok(review) = review else {
        return Ok(unavailable());
    };
    let session_id = review.session_id.clone();
    let active = ActiveAttachment {
        operation_id: request.operation_id.clone(),
        mode: AttachmentMode::Remote,
        selection: request.selection.clone(),
        document: request.selection.document(
            review.connection.document_root().into(),
            request.operation_id.clone(),
        ),
        session_id: session_id.clone(),
        owner: review.owner,
        ticket: review.ticket,
        connection: review.connection,
        candidate: None,
        commit_request: None,
        generation: 0,
        staging: true,
        cancelling: false,
    };
    if !manager.activate(active) {
        return Ok(unavailable());
    }
    let active = manager.current(&request.operation_id).ok_or(())?;
    let worker_manager = manager.inner().clone();
    let worker_window = window.clone();
    let worker_lock = lock.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let authorized = || {
            worker_manager.current(&active.operation_id).is_some()
                && worker_lock.finish_protected_action(active.ticket).is_ok()
                && crate::directory_window_handle(&worker_window) == Some(active.owner)
                && active.connection.is_current()
        };
        let outcome = active.connection.document_request_owned(NativeDocumentAction::Download,
            json!({"root":active.connection.document_root(),"projectId":active.selection.project_id,
                "sessionId":active.session_id,"previewId":review.preview.preview_id,
                "confirmation":review.preview.confirmation,"operationId":active.operation_id}), &authorized)
            .map_err(|_| PickerFailure::Unavailable)
            .and_then(|response| decode_remote_candidate(response, &active));
        finish_stage(&worker_manager, &worker_window, &active, outcome);
    });
    Ok(begin_outcome(
        &request.operation_id,
        "armed",
        Some(&session_id),
    ))
}

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct AttachmentSelection {
    pub project_id: String,
    pub work_id: String,
    pub work_revision_id: String,
    pub version_id: String,
    pub version_revision_id: String,
    pub source_assertion_revision_id: String,
}

impl AttachmentSelection {
    fn valid(&self) -> bool {
        crate::supervisor::canonical_project_id(&self.project_id)
            && [
                &self.work_id,
                &self.work_revision_id,
                &self.version_id,
                &self.version_revision_id,
                &self.source_assertion_revision_id,
            ]
            .iter()
            .all(|id| crate::supervisor::canonical_uuid_v7(id))
    }

    fn document(&self, root: String, operation_id: String) -> DocumentSelection {
        DocumentSelection {
            root,
            project_id: self.project_id.clone(),
            operation_id,
            declared_media_type: None,
            source_assertion_revision_id: self.source_assertion_revision_id.clone(),
            work_id: self.work_id.clone(),
            work_revision_id: self.work_revision_id.clone(),
            version_id: self.version_id.clone(),
            version_revision_id: self.version_revision_id.clone(),
        }
    }

    fn core_fields(&self) -> Value {
        json!({
            "projectId": self.project_id,
            "sourceAssertionRevisionId": self.source_assertion_revision_id,
            "workId": self.work_id,
            "workRevisionId": self.work_revision_id,
            "versionId": self.version_id,
            "versionRevisionId": self.version_revision_id,
        })
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "lowercase")]
pub(crate) enum AttachmentMode {
    Choose,
    Drop,
    Remote,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct BeginRequest {
    schema_version: String,
    mode: AttachmentMode,
    operation_id: String,
    selection: AttachmentSelection,
}

impl BeginRequest {
    fn valid(&self) -> bool {
        self.schema_version == "1.0"
            && matches!(self.mode, AttachmentMode::Choose | AttachmentMode::Drop)
            && crate::supervisor::canonical_uuid_v7(&self.operation_id)
            && self.selection.valid()
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct CommitRequest {
    schema_version: String,
    operation_id: String,
    session_id: String,
    candidate_id: String,
    confirmation_sha256: String,
    command_id: String,
    selection: AttachmentSelection,
    match_confirmed: bool,
    permitted_use: String,
}

impl CommitRequest {
    fn valid(&self) -> bool {
        self.schema_version == "1.0"
            && self.selection.valid()
            && [&self.operation_id, &self.candidate_id, &self.command_id]
                .iter()
                .all(|id| crate::supervisor::canonical_uuid_v7(id))
            && lower_hex(&self.session_id, 32)
            && lower_hex(&self.confirmation_sha256, 64)
            && self.match_confirmed
            && self.permitted_use == "project-only"
    }
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct CancelRequest {
    schema_version: String,
    operation_id: String,
    session_id: Option<String>,
    candidate_id: Option<String>,
}

impl CancelRequest {
    fn valid(&self) -> bool {
        self.schema_version == "1.0"
            && crate::supervisor::canonical_uuid_v7(&self.operation_id)
            && self
                .session_id
                .as_deref()
                .is_none_or(|id| lower_hex(id, 32))
            && self
                .candidate_id
                .as_deref()
                .is_none_or(crate::supervisor::canonical_uuid_v7)
    }
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct StatusRequest {
    schema_version: String,
    selection: AttachmentSelection,
    operation_id: Option<String>,
    command_id: Option<String>,
}

impl StatusRequest {
    fn valid(&self) -> bool {
        self.schema_version == "1.0"
            && self.selection.valid()
            && self
                .operation_id
                .as_deref()
                .is_none_or(crate::supervisor::canonical_uuid_v7)
            && self
                .command_id
                .as_deref()
                .is_none_or(crate::supervisor::canonical_uuid_v7)
            && (self.command_id.is_none() || self.operation_id.is_some())
    }
}

fn lower_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn safe_name(value: &str) -> bool {
    !value.is_empty()
        && value.chars().count() <= 255
        && value != "."
        && value != ".."
        && !value
            .chars()
            .any(|ch| ch.is_control() || ch == '/' || ch == '\\')
}

fn problem_code(code: &str) -> &'static str {
    match code {
        "RO-CORE-DOCUMENT-UNSUPPORTED-FORMAT" => "unsupported-format",
        "RO-CORE-DOCUMENT-PASSWORD-PROTECTED" => "password-protected",
        "RO-CORE-DOCUMENT-OVERSIZE" => "oversize",
        "RO-CORE-DOCUMENT-UNSAFE-CONTENT" => "unsafe-content",
        "RO-CORE-DOCUMENT-MALFORMED-CONTENT" => "malformed-content",
        "RO-CORE-DOCUMENT-FORMAT-MISMATCH" => "format-mismatch",
        "RO-CORE-DOCUMENT-RIGHTS-DENIED" => "rights-denied",
        "RO-CORE-DOCUMENT-ASSOCIATION-STALE" => "association-stale",
        "RO-CORE-DOCUMENT-AUTHORITY-CHANGED" => "authority-changed",
        "RO-CORE-DOCUMENT-WORKER-UNAVAILABLE" => "worker-unavailable",
        "RO-CORE-DOCUMENT-STORAGE-PRESSURE" => "storage-pressure",
        "RO-CORE-DOCUMENT-CANDIDATE-UNAVAILABLE" => "candidate-unavailable",
        "RO-CORE-DOCUMENT-CANCELLED" => "interrupted",
        "RO-CORE-DOCUMENT-CLEANUP-REQUIRED" => "cleanup-required",
        "RO-CORE-DOCUMENT-COPY-UNAVAILABLE" => "copy-unavailable",
        "RO-CORE-DOCUMENT-ACCESS-DENIED" => "access-denied",
        "RO-CORE-DOCUMENT-DESTINATION-DENIED" => "destination-denied",
        "RO-CORE-DOCUMENT-NETWORK-UNAVAILABLE" => "network-unavailable",
        "RO-CORE-DOCUMENT-DOWNLOAD-FAILED" => "download-failed",
        _ => "unavailable",
    }
}

fn core_problem(response: &crate::supervisor::CoreApiResponse) -> Option<&'static str> {
    if response.status < 400
        || response.content_type != "application/problem+json"
        || response.body.len() > 2048
    {
        return None;
    }
    let problem: document_runtime::DocumentProblem = serde_json::from_str(&response.body).ok()?;
    (problem.status == response.status
        && problem.trace_id == response.trace_id
        && problem.code.starts_with("RO-CORE-DOCUMENT-"))
    .then(|| problem_code(&problem.code))
}

#[derive(Clone)]
struct ActiveAttachment {
    operation_id: String,
    mode: AttachmentMode,
    selection: AttachmentSelection,
    document: DocumentSelection,
    session_id: String,
    owner: isize,
    ticket: u64,
    connection: Arc<NativeImportConnection>,
    candidate: Option<(String, String)>,
    commit_request: Option<CommitRequest>,
    generation: u64,
    staging: bool,
    cancelling: bool,
}

#[derive(Default)]
struct AttachmentState {
    installed: bool,
    generation: u64,
    active: Option<ActiveAttachment>,
    review: Option<NativeCopyReview>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ClearedNativeOperation {
    BeforeCandidate,
    WithCandidate,
}

impl AttachmentState {
    fn accepts_stage_generation(&self, generation: u64) -> bool {
        self.installed && self.generation == generation
    }

    fn matches_operation(&self, expected: &ActiveAttachment) -> bool {
        self.installed
            && self.generation == expected.generation
            && self.active.as_ref().is_some_and(|current| {
                current.generation == expected.generation
                    && current.operation_id == expected.operation_id
                    && current.session_id == expected.session_id
                    && current.selection == expected.selection
                    && Arc::ptr_eq(&current.connection, &expected.connection)
            })
    }
}

#[derive(Clone, Default)]
pub(crate) struct DocumentAttachmentManager {
    shared: Arc<Mutex<AttachmentState>>,
}

impl DocumentAttachmentManager {
    #[cfg(feature = "integration-harness")]
    pub(crate) fn fixture_is_idle(&self) -> bool {
        self.shared.lock().is_ok_and(|state| state.active.is_none())
    }

    pub(crate) fn set_installed(&self, installed: bool) {
        if let Ok(mut state) = self.shared.lock() {
            state.installed = installed;
            if !installed {
                state.generation = state.generation.saturating_add(1);
                state.active = None;
                state.review = None;
            }
        }
    }

    pub(crate) fn installed(&self) -> bool {
        self.shared.lock().is_ok_and(|state| state.installed)
    }

    pub(crate) fn cancel_all(&self) {
        if let Ok(mut state) = self.shared.lock() {
            state.generation = state.generation.saturating_add(1);
            state.active = None;
            state.review = None;
        }
    }

    fn activate(&self, mut active: ActiveAttachment) -> bool {
        let Ok(mut state) = self.shared.lock() else {
            return false;
        };
        if !state.installed
            || state
                .active
                .as_ref()
                .is_some_and(|existing| existing.connection.is_current())
        {
            return false;
        }
        state.generation = state.generation.saturating_add(1);
        active.generation = state.generation;
        state.review = None;
        state.active = Some(active);
        true
    }

    fn current(&self, operation_id: &str) -> Option<ActiveAttachment> {
        let state = self.shared.lock().ok()?;
        let active = state.active.as_ref()?;
        (state.installed
            && active.operation_id == operation_id
            && active.generation == state.generation
            && active.connection.is_current())
        .then(|| active.clone())
    }

    fn reserve_cancel(&self, expected: &ActiveAttachment) -> bool {
        let Ok(mut state) = self.shared.lock() else {
            return false;
        };
        if !state.matches_operation(expected) {
            return false;
        }
        let current = state.active.as_mut().unwrap();
        if current.candidate != expected.candidate
            || current.staging
            || current.cancelling
            || current.commit_request.is_some()
        {
            return false;
        }
        current.cancelling = true;
        true
    }

    fn reserve_commit(&self, expected: &ActiveAttachment, request: &CommitRequest) -> bool {
        let Ok(mut state) = self.shared.lock() else {
            return false;
        };
        if !state.matches_operation(expected) {
            return false;
        }
        let current = state.active.as_mut().unwrap();
        if current.candidate != expected.candidate
            || current.staging
            || current.cancelling
            || current
                .commit_request
                .as_ref()
                .is_some_and(|saved| saved != request)
        {
            return false;
        }
        current.commit_request = Some(request.clone());
        true
    }

    /// Discard only the operation that produced the result. An old Core reply
    /// may arrive after a project switch has admitted a new operation.
    fn clear_exact(
        &self,
        expected: &ActiveAttachment,
        committed_request: Option<&CommitRequest>,
        cancelling: bool,
        picker: Option<&DirectoryPickerManager>,
    ) -> Option<ClearedNativeOperation> {
        let Ok(mut state) = self.shared.lock() else {
            return None;
        };
        if !state.matches_operation(expected) {
            return None;
        }
        let current = state.active.as_ref().unwrap();
        if current.commit_request.as_ref() != committed_request || current.cancelling != cancelling
        {
            return None;
        }
        let disposition = if current.candidate.is_some() {
            ClearedNativeOperation::WithCandidate
        } else {
            ClearedNativeOperation::BeforeCandidate
        };
        if current.mode == AttachmentMode::Choose
            && current.candidate.is_none()
            && let Some(picker) = picker
        {
            // Keep new attachment admission closed while cancelling the
            // chooser. A late chooser result is fenced by the generation.
            picker.cancel_pending();
        }
        state.generation = state.generation.saturating_add(1);
        state.active = None;
        Some(disposition)
    }

    pub(crate) fn armed_drop(&self) -> Option<String> {
        let state = self.shared.lock().ok()?;
        let active = state.active.as_ref()?;
        (state.installed
            && active.mode == AttachmentMode::Drop
            && active.candidate.is_none()
            && !active.staging
            && !active.cancelling
            && active.connection.is_current())
        .then(|| active.operation_id.clone())
    }
}

fn begin_outcome(operation_id: &str, status: &str, session_id: Option<&str>) -> Value {
    if let Some(session_id) = session_id {
        json!({"schemaVersion":"1.0","status":status,"operationId":operation_id,"sessionId":session_id})
    } else {
        json!({"schemaVersion":"1.0","status":status,"operationId":operation_id})
    }
}

fn event_for_stage(
    active: &ActiveAttachment,
    outcome: Result<DocumentStageOutcome, PickerFailure>,
) -> Value {
    let common = json!({"schemaVersion":"1.0","operationId":active.operation_id,
        "sessionId":active.session_id,"selection":active.selection});
    let mut event = common;
    match outcome {
        Ok(DocumentStageOutcome::Candidate(candidate))
            if safe_name(&candidate.source_name)
                && (1..=128 * 1024 * 1024).contains(&candidate.byte_length) =>
        {
            let format = if candidate.format == "plain-text" {
                "txt"
            } else {
                candidate.format.as_str()
            };
            if !["pdf", "jats", "tei", "xml", "html", "docx", "txt"].contains(&format) {
                event["status"] = "rejected".into();
                event["code"] = "unsupported-format".into();
            } else {
                event["status"] = "candidate".into();
                event["candidate"] = json!({"candidateId":candidate.candidate_id,"sourceName":candidate.source_name,
                    "byteLength":candidate.byte_length,"format":format,"confirmationSha256":candidate.candidate_sha256,
                    "confirmationRequired":true});
            }
        }
        Ok(DocumentStageOutcome::Rejected(problem)) => {
            event["status"] = "rejected".into();
            event["code"] = problem_code(&problem.code).into();
        }
        Err(PickerFailure::Cancelled) => {
            event["status"] = "cancelled".into();
        }
        Err(PickerFailure::DocumentOversize) => {
            event["status"] = "rejected".into();
            event["code"] = "oversize".into();
        }
        Err(PickerFailure::DocumentEmpty) => {
            event["status"] = "rejected".into();
            event["code"] = "malformed-content".into();
        }
        _ => {
            event["status"] = "rejected".into();
            event["code"] = "unavailable".into();
        }
    }
    event
}

fn finish_stage(
    manager: &DocumentAttachmentManager,
    window: &tauri::WebviewWindow,
    active: &ActiveAttachment,
    outcome: Result<DocumentStageOutcome, PickerFailure>,
) {
    let event = event_for_stage(active, outcome);
    #[cfg(feature = "integration-harness")]
    let (probe_status, probe_code, probe_candidate) = (
        event["status"].as_str().unwrap_or("unavailable").to_owned(),
        event["code"].as_str().map(str::to_owned),
        event["candidate"]["candidateId"]
            .as_str()
            .map(str::to_owned),
    );
    #[cfg(feature = "integration-harness")]
    let (closure_entered, event_emitted) =
        (std::cell::Cell::new(false), std::cell::Cell::new(false));
    let stage_result = window
        .state::<ApplicationLockManager>()
        .commit_protected_action(active.ticket, || {
            #[cfg(feature = "integration-harness")]
            closure_entered.set(true);
            let mut state = manager
                .shared
                .lock()
                .map_err(|_| "RO-DOCUMENT-STATE-UNAVAILABLE")?;
            if !state.accepts_stage_generation(active.generation)
                || crate::directory_window_handle(window) != Some(active.owner)
                || !active.connection.is_current()
            {
                return Err("RO-DOCUMENT-SESSION-UNAVAILABLE");
            }
            let Some(current) = state.active.as_mut() else {
                return Err("RO-DOCUMENT-OPERATION-UNAVAILABLE");
            };
            if current.operation_id != active.operation_id
                || current.generation != active.generation
                || current.session_id != active.session_id
            {
                return Err("RO-DOCUMENT-OPERATION-UNAVAILABLE");
            }
            current.staging = false;
            if event["status"] == "candidate" {
                current.candidate = Some((
                    event["candidate"]["candidateId"]
                        .as_str()
                        .unwrap()
                        .to_owned(),
                    event["candidate"]["confirmationSha256"]
                        .as_str()
                        .unwrap()
                        .to_owned(),
                ));
            } else {
                state.active = None;
            }
            if window.emit(RESULT_EVENT, event).is_err() {
                state.generation = state.generation.saturating_add(1);
                state.active = None;
                return Err("RO-DOCUMENT-EVENT-UNAVAILABLE");
            }
            #[cfg(feature = "integration-harness")]
            event_emitted.set(true);
            #[cfg(feature = "integration-harness")]
            if state
                .active
                .as_ref()
                .is_some_and(|item| item.candidate.is_some())
            {
                crate::document_drop::record_candidate();
            }
            Ok(())
        });
    #[cfg(feature = "integration-harness")]
    crate::directory_integration_harness::observe_document_stage_finish(
        &active.operation_id,
        &probe_status,
        probe_code.as_deref(),
        probe_candidate.as_deref(),
        closure_entered.get(),
        event_emitted.get(),
        stage_result.as_ref().err().copied(),
    );
    #[cfg(not(feature = "integration-harness"))]
    let _ = stage_result;
}

#[tauri::command]
pub(crate) fn document_attachment_capabilities(
    window: tauri::WebviewWindow,
    manager: State<'_, DocumentAttachmentManager>,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    project_id: String,
) -> Value {
    let ready = crate::supervisor::canonical_project_id(&project_id)
        && manager.installed()
        && crate::directory_window_handle(&window).is_some()
        && lock.begin_protected_action().is_ok()
        && supervisor.native_document_connection(&project_id).is_ok();
    json!({"schemaVersion":"1.0","status":if ready {"ready"} else {"unavailable"},"projectId":project_id})
}

#[tauri::command]
pub(crate) async fn document_attachment_begin(
    window: tauri::WebviewWindow,
    manager: State<'_, DocumentAttachmentManager>,
    supervisor: State<'_, RuntimeSupervisor>,
    picker: State<'_, DirectoryPickerManager>,
    lock: State<'_, ApplicationLockManager>,
    request: BeginRequest,
) -> Result<Value, ()> {
    let unavailable = || begin_outcome(&request.operation_id, "unavailable", None);
    if !request.valid() || !manager.installed() {
        return Ok(unavailable());
    }
    let Some(owner) = crate::directory_window_handle(&window) else {
        return Ok(unavailable());
    };
    let Ok(ticket) = lock.begin_protected_action() else {
        return Ok(unavailable());
    };
    let Ok(connection) = supervisor.native_document_connection(&request.selection.project_id)
    else {
        return Ok(unavailable());
    };
    let connection = Arc::new(connection);
    let context_connection = Arc::clone(&connection);
    let project_id = request.selection.project_id.clone();
    let Ok(Ok(context)) = tauri::async_runtime::spawn_blocking(move || {
        document_runtime::current_document_context(&context_connection, &project_id)
    })
    .await
    else {
        return Ok(unavailable());
    };
    if crate::directory_window_handle(&window) != Some(owner)
        || lock.finish_protected_action(ticket).is_err()
        || !connection.is_current()
    {
        return Ok(unavailable());
    }
    let active = ActiveAttachment {
        operation_id: request.operation_id.clone(),
        mode: request.mode,
        selection: request.selection.clone(),
        document: request.selection.document(
            connection.document_root().to_owned(),
            request.operation_id.clone(),
        ),
        session_id: context.session_id.clone(),
        owner,
        ticket,
        connection,
        candidate: None,
        commit_request: None,
        generation: 0,
        staging: false,
        cancelling: false,
    };
    if !manager.activate(active) {
        return Ok(unavailable());
    }
    if request.mode == AttachmentMode::Choose {
        let Some(active) = manager.current(&request.operation_id) else {
            return Ok(unavailable());
        };
        let (worker_manager, worker_window, worker_picker, worker_lock) = (
            manager.inner().clone(),
            window.clone(),
            picker.inner().clone(),
            lock.inner().clone(),
        );
        tauri::async_runtime::spawn_blocking(move || {
            let outcome = document_runtime::stage_selected_document(
                worker_picker,
                Arc::clone(&active.connection),
                active.session_id.clone(),
                worker_lock,
                active.ticket,
                active.owner,
                active.document.clone(),
            );
            finish_stage(&worker_manager, &worker_window, &active, outcome);
        });
    }
    Ok(begin_outcome(
        &request.operation_id,
        "armed",
        Some(&context.session_id),
    ))
}

/// Called only by the native OLE target with a held file, never by renderer IPC.
pub(crate) fn stage_dropped_source(
    manager: &DocumentAttachmentManager,
    window: &tauri::WebviewWindow,
    source: HeldImportSource,
) -> bool {
    let Some(operation_id) = manager.armed_drop() else {
        return false;
    };
    let active = {
        let Ok(mut state) = manager.shared.lock() else {
            return false;
        };
        let Some(active) = state.active.as_mut() else {
            return false;
        };
        if active.operation_id != operation_id || active.staging {
            return false;
        }
        active.staging = true;
        active.clone()
    };
    if crate::directory_window_handle(window) != Some(active.owner)
        || window
            .state::<ApplicationLockManager>()
            .finish_protected_action(active.ticket)
            .is_err()
    {
        manager.clear_exact(&active, None, false, None);
        return false;
    }
    let (worker_manager, worker_window) = (manager.clone(), window.clone());
    #[cfg(feature = "integration-harness")]
    crate::directory_integration_harness::observe_document_transport_phase("spawn-scheduled", None);
    tauri::async_runtime::spawn_blocking(move || {
        #[cfg(feature = "integration-harness")]
        crate::directory_integration_harness::observe_document_transport_phase("body-start", None);
        let security = worker_window
            .state::<ApplicationLockManager>()
            .inner()
            .clone();
        let authorized = || {
            security.finish_protected_action(active.ticket).is_ok()
                && active.connection.is_current()
                && worker_manager.current(&active.operation_id).is_some()
        };
        let outcome = document_runtime::stage_held_document(
            &active.connection,
            &active.session_id,
            source,
            &active.document,
            authorized,
        );
        #[cfg(feature = "integration-harness")]
        crate::directory_integration_harness::observe_document_transport_phase(
            "finish-invoked",
            None,
        );
        finish_stage(&worker_manager, &worker_window, &active, outcome);
    });
    #[cfg(feature = "integration-harness")]
    crate::document_drop::record_held_stage();
    true
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct CoreStatus {
    state: String,
    project_id: String,
    source_assertion_revision_id: String,
    work_id: String,
    work_revision_id: String,
    version_id: String,
    version_revision_id: String,
    operation_id: Option<String>,
    command_id: Option<String>,
    candidate_id: Option<String>,
    attachment_id: Option<String>,
    document_revision_id: Option<String>,
    #[serde(default)]
    intake_code: Option<String>,
}

fn decode_core_status(
    response: crate::supervisor::CoreApiResponse,
    request: &StatusRequest,
) -> Option<CoreStatus> {
    if response.status != 200
        || response.content_type != "application/json"
        || response.body.len() > 8192
    {
        return None;
    }
    let status: CoreStatus = serde_json::from_str(&response.body).ok()?;
    let same = status.project_id == request.selection.project_id
        && status.source_assertion_revision_id == request.selection.source_assertion_revision_id
        && status.work_id == request.selection.work_id
        && status.work_revision_id == request.selection.work_revision_id
        && status.version_id == request.selection.version_id
        && status.version_revision_id == request.selection.version_revision_id;
    let ids_valid = [
        status.operation_id.as_deref(),
        status.command_id.as_deref(),
        status.candidate_id.as_deref(),
        status.attachment_id.as_deref(),
        status.document_revision_id.as_deref(),
    ]
    .into_iter()
    .flatten()
    .all(crate::supervisor::canonical_uuid_v7);
    let stale_session_without_command = status.state == "stale-session"
        && request.operation_id.is_some()
        && status.operation_id == request.operation_id
        && status.command_id.is_none()
        && status.candidate_id.is_some()
        && status.attachment_id.is_none()
        && status.document_revision_id.is_none();
    if !same
        || !ids_valid
        || (status.state.starts_with("intake-") != status.intake_code.is_some())
        || status.intake_code.as_ref().is_some_and(|code| {
            code.is_empty()
                || code.len() > 64
                || !code
                    .bytes()
                    .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
                || status.operation_id.is_none()
                || status.command_id.is_some()
                || status.candidate_id.is_some()
                || status.attachment_id.is_some()
                || status.document_revision_id.is_some()
        })
        || (request
            .operation_id
            .as_ref()
            .is_some_and(|id| status.operation_id.as_ref() != Some(id))
            && status.state != "legacy")
        || (request
            .command_id
            .as_ref()
            .is_some_and(|id| status.command_id.as_ref() != Some(id))
            && status.state != "legacy"
            && !stale_session_without_command)
    {
        return None;
    }
    Some(status)
}

fn renderer_status(
    status: CoreStatus,
    request: &StatusRequest,
    current_session: &str,
    manager: &DocumentAttachmentManager,
) -> Value {
    let mut result = json!({"schemaVersion":"1.0","status":"unavailable",
        "selection":request.selection,"operationId":status.operation_id,"commandId":status.command_id,
        "attachmentId":null,"documentRevisionId":null,"code":"candidate-unavailable","retryRequest":null});
    match status.state.as_str() {
        "intake-running" => match status.intake_code.as_deref() {
            Some("intake-downloading") => {
                result["status"] = "downloading".into();
                result["code"] = Value::Null;
            }
            Some("intake-validating") => {
                result["status"] = "validating".into();
                result["code"] = Value::Null;
            }
            _ => {
                result["code"] = "interrupted".into();
            }
        },
        "intake-failed" => {
            result["status"] = "failed".into();
            result["code"] = match status.intake_code.as_deref() {
                Some("acquisition-cleanup-required") => "cleanup-required",
                Some("acquisition-rights-denied") => "rights-denied",
                Some("acquisition-unavailable") => "copy-unavailable",
                Some("acquisition-access-denied") => "access-denied",
                Some(
                    "acquisition-redirect-denied"
                    | "acquisition-destination-denied"
                    | "acquisition-egress-denied",
                ) => "destination-denied",
                Some("acquisition-response-too-large") => "oversize",
                Some("acquisition-content-type-denied") => "format-mismatch",
                Some("acquisition-network-unavailable") => "network-unavailable",
                Some(
                    "acquisition-policy-changed"
                    | "acquisition-preview-stale"
                    | "acquisition-authority-changed",
                ) => "authority-changed",
                Some(
                    "attempts-exhausted"
                    | "lease-expired"
                    | "acquisition-cancelled"
                    | "acquisition-network-timeout",
                ) => "interrupted",
                _ => "download-failed",
            }
            .into();
        }
        "intake-cancelled" => {
            result["status"] = "cancelled".into();
            result["code"] = Value::Null;
        }
        "metadata-only"
            if status.operation_id.is_none()
                && status.command_id.is_none()
                && status.attachment_id.is_none() =>
        {
            result["status"] = "metadata-only".into();
            result["code"] = Value::Null;
        }
        "candidate"
            if status.operation_id.is_some()
                && status.command_id.is_none()
                && status.candidate_id.is_some()
                && status.attachment_id.is_none()
                && manager
                    .current(status.operation_id.as_deref().unwrap())
                    .is_some_and(|active| {
                        active.session_id == current_session
                            && active.selection == request.selection
                    }) =>
        {
            result["status"] = "candidate".into();
            result["code"] = Value::Null;
        }
        "committed"
            if status.operation_id.is_some()
                && status.command_id.is_some()
                && status.attachment_id.is_some()
                && status.document_revision_id.is_some() =>
        {
            result["status"] = "processing".into();
            result["attachmentId"] = status.attachment_id.unwrap().into();
            result["documentRevisionId"] = status.document_revision_id.unwrap().into();
            result["code"] = Value::Null;
        }
        "cancelled" if status.operation_id.is_some() && status.attachment_id.is_none() => {
            result["status"] = "cancelled".into();
            result["code"] = Value::Null;
        }
        "unresolved"
            if status.operation_id.is_some()
                && status.command_id.is_some()
                && status.attachment_id.is_none() =>
        {
            if let Some(active) = manager.current(status.operation_id.as_deref().unwrap())
                && active.session_id == current_session
                && active.selection == request.selection
                && let Some(saved) = active.commit_request
                && Some(&saved.command_id) == status.command_id.as_ref()
            {
                result["status"] = "unconfirmed".into();
                result["code"] = Value::Null;
                result["retryRequest"] = serde_json::to_value(saved).unwrap_or(Value::Null);
            }
        }
        "stale-session"
            if status.operation_id.is_some()
                && status.command_id.is_none()
                && status.candidate_id.is_some()
                && status.attachment_id.is_none()
                && status.document_revision_id.is_none() =>
        {
            // An old Core session cannot replay an unresolved decision. Keep
            // the command null, but return an exact terminal operation status
            // so the pane can discard its local saved retry and choose anew.
            result["code"] = "interrupted".into();
        }
        // A prior v22 assertion or missing operation is never evidence of
        // metadata-only or a readable local copy.
        "legacy" | "unavailable" => {}
        _ => {}
    }
    result
}

#[tauri::command]
pub(crate) async fn document_attachment_status(
    window: tauri::WebviewWindow,
    manager: State<'_, DocumentAttachmentManager>,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: StatusRequest,
) -> Result<Option<Value>, ()> {
    if !request.valid() || !manager.installed() || crate::directory_window_handle(&window).is_none()
    {
        return Ok(None);
    }
    let ticket = lock.begin_protected_action().map_err(|_| ())?;
    let connection = Arc::new(
        supervisor
            .native_document_connection(&request.selection.project_id)
            .map_err(|_| ())?,
    );
    let worker_connection = Arc::clone(&connection);
    let selection = request.selection.clone();
    let manager = manager.inner().clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        let context =
            document_runtime::current_document_context(&worker_connection, &selection.project_id)
                .map_err(|_| ())?;
        let mut body = selection.core_fields();
        body["root"] = worker_connection.document_root().into();
        body["sessionId"] = context.session_id.clone().into();
        body["operationId"] = serde_json::to_value(&request.operation_id).map_err(|_| ())?;
        body["commandId"] = serde_json::to_value(&request.command_id).map_err(|_| ())?;
        let response = worker_connection
            .document_request(NativeDocumentAction::Status, body)
            .map_err(|_| ())?;
        let core = decode_core_status(response, &request).ok_or(())?;
        Ok::<_, ()>(renderer_status(
            core,
            &request,
            &context.session_id,
            &manager,
        ))
    })
    .await
    .map_err(|_| ())??;
    if lock.finish_protected_action(ticket).is_err()
        || crate::directory_window_handle(&window).is_none()
        || !connection.is_current()
    {
        return Ok(None);
    }
    Ok(Some(result))
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct CoreAttachment {
    attachment_id: String,
    document_id: String,
    document_revision_id: String,
    candidate_id: String,
    work_id: String,
    work_revision_id: String,
    version_id: String,
    version_revision_id: String,
    source_assertion_revision_id: String,
    object_sha256: String,
    rights_policy_revision_id: String,
    provenance_event_id: String,
    outbox_id: String,
}

fn decode_core_attachment(
    response: &crate::supervisor::CoreApiResponse,
    request: &CommitRequest,
) -> Option<(String, String)> {
    if response.status != 200
        || response.content_type != "application/json"
        || response.body.len() > 8192
    {
        return None;
    }
    let found: CoreAttachment = serde_json::from_str(&response.body).ok()?;
    let ids = [
        &found.attachment_id,
        &found.document_id,
        &found.document_revision_id,
        &found.candidate_id,
        &found.work_id,
        &found.work_revision_id,
        &found.version_id,
        &found.version_revision_id,
        &found.source_assertion_revision_id,
        &found.rights_policy_revision_id,
        &found.provenance_event_id,
        &found.outbox_id,
    ];
    (ids.into_iter()
        .all(|id| crate::supervisor::canonical_uuid_v7(id))
        && lower_hex(&found.object_sha256, 64)
        && found.candidate_id == request.candidate_id
        && found.work_id == request.selection.work_id
        && found.work_revision_id == request.selection.work_revision_id
        && found.version_id == request.selection.version_id
        && found.version_revision_id == request.selection.version_revision_id
        && found.source_assertion_revision_id == request.selection.source_assertion_revision_id)
        .then_some((found.attachment_id, found.document_revision_id))
}

fn attachment_outcome(active: &ActiveAttachment, status: &str, code: Option<&str>) -> Value {
    let mut result = json!({"schemaVersion":"1.0","status":status,
        "operationId":active.operation_id,"sessionId":active.session_id,
        "selection":active.selection});
    if let Some(code) = code {
        result["code"] = code.into();
    }
    result
}

enum CandidateCancelReceipt {
    Confirmed,
    Rejected(&'static str),
    Unconfirmed,
}

fn candidate_cancel_receipt(
    response: Option<&crate::supervisor::CoreApiResponse>,
) -> CandidateCancelReceipt {
    match response {
        Some(response) if response.status == 204 && response.body.is_empty() => {
            CandidateCancelReceipt::Confirmed
        }
        Some(response) => core_problem(response).map_or(
            CandidateCancelReceipt::Unconfirmed,
            CandidateCancelReceipt::Rejected,
        ),
        None => CandidateCancelReceipt::Unconfirmed,
    }
}

#[tauri::command]
pub(crate) async fn document_attachment_cancel(
    window: tauri::WebviewWindow,
    manager: State<'_, DocumentAttachmentManager>,
    picker: State<'_, DirectoryPickerManager>,
    lock: State<'_, ApplicationLockManager>,
    request: CancelRequest,
) -> Result<Option<Value>, ()> {
    if !request.valid() || crate::directory_window_handle(&window).is_none() {
        return Ok(None);
    }
    let Some(active) = manager.current(&request.operation_id) else {
        return Ok(None);
    };
    if request
        .session_id
        .as_ref()
        .is_some_and(|id| id != &active.session_id)
        || request
            .candidate_id
            .as_ref()
            .is_some_and(|id| active.candidate.as_ref().map(|item| &item.0) != Some(id))
        || active.commit_request.is_some()
    {
        return Ok(None);
    }
    if active.candidate.is_none() {
        // A running stage may leave an orphan for T03 cleanup, but a delayed
        // result cannot be advertised after this native cancellation.
        let cleared = lock
            .commit_protected_action(active.ticket, || {
                if crate::directory_window_handle(&window) != Some(active.owner)
                    || !active.connection.is_current()
                {
                    return Err("RO-DOCUMENT-SESSION-UNAVAILABLE");
                }
                Ok(manager.clear_exact(&active, None, false, Some(&picker)))
            })
            .ok()
            .flatten();
        return Ok((cleared == Some(ClearedNativeOperation::BeforeCandidate)
            && active.connection.is_current())
        .then(|| attachment_outcome(&active, "cancelled", None)));
    }
    if !manager.reserve_cancel(&active) {
        return Ok(None);
    }
    if lock.finish_protected_action(active.ticket).is_err()
        || crate::directory_window_handle(&window) != Some(active.owner)
        || !active.connection.is_current()
    {
        manager.clear_exact(&active, None, true, None);
        return Ok(None);
    }
    let body = json!({"root":active.connection.document_root(),"projectId":active.selection.project_id,
        "sessionId":active.session_id,"operationId":active.operation_id,
        "candidateId":active.candidate.as_ref().unwrap().0});
    let connection = Arc::clone(&active.connection);
    let response = tauri::async_runtime::spawn_blocking(move || {
        connection.document_request(NativeDocumentAction::Cancel, body)
    })
    .await
    .ok()
    .and_then(Result::ok);
    let can_deliver = lock.finish_protected_action(active.ticket).is_ok()
        && crate::directory_window_handle(&window) == Some(active.owner)
        && active.connection.is_current();
    match candidate_cancel_receipt(response.as_ref()) {
        CandidateCancelReceipt::Confirmed => {
            let cleared = manager.clear_exact(&active, None, true, None);
            Ok((cleared == Some(ClearedNativeOperation::WithCandidate)
                && can_deliver
                && active.connection.is_current())
            .then(|| attachment_outcome(&active, "cancelled", None)))
        }
        CandidateCancelReceipt::Rejected(code) => {
            // A denied Core cancel may leave only an encrypted unassociated
            // stage for T03 cleanup. Clear the native admission without
            // claiming that Core cancelled it.
            let cleared = manager.clear_exact(&active, None, true, None);
            Ok((cleared == Some(ClearedNativeOperation::WithCandidate)
                && can_deliver
                && active.connection.is_current())
            .then(|| attachment_outcome(&active, "rejected", Some(code))))
        }
        CandidateCancelReceipt::Unconfirmed => {
            manager.clear_exact(&active, None, true, None);
            Ok(None)
        }
    }
}

#[tauri::command]
pub(crate) async fn document_attachment_commit(
    window: tauri::WebviewWindow,
    manager: State<'_, DocumentAttachmentManager>,
    lock: State<'_, ApplicationLockManager>,
    request: CommitRequest,
) -> Result<Option<Value>, ()> {
    if !request.valid() {
        return Ok(None);
    }
    let Some(active) = manager.current(&request.operation_id) else {
        return Ok(None);
    };
    if active.selection != request.selection
        || active.session_id != request.session_id
        || active.candidate.as_ref()
            != Some(&(
                request.candidate_id.clone(),
                request.confirmation_sha256.clone(),
            ))
        || crate::directory_window_handle(&window) != Some(active.owner)
        || lock.finish_protected_action(active.ticket).is_err()
    {
        return Ok(None);
    }
    if !manager.reserve_commit(&active, &request) {
        return Ok(None);
    }
    let mut body = request.selection.core_fields();
    body["root"] = active.connection.document_root().into();
    body["sessionId"] = request.session_id.clone().into();
    body["operationId"] = request.operation_id.clone().into();
    body["candidateId"] = request.candidate_id.clone().into();
    body["confirmationSha256"] = request.confirmation_sha256.clone().into();
    body["commandId"] = request.command_id.clone().into();
    body["matchConfirmed"] = true.into();
    body["permittedUse"] = "project-only".into();
    let connection = Arc::clone(&active.connection);
    let response = tauri::async_runtime::spawn_blocking(move || {
        connection.document_request(NativeDocumentAction::Commit, body)
    })
    .await
    .ok()
    .and_then(Result::ok);
    if manager.current(&request.operation_id).is_none()
        || lock.finish_protected_action(active.ticket).is_err()
        || crate::directory_window_handle(&window) != Some(active.owner)
    {
        return Ok(None);
    }
    let Some(response) = response else {
        return Ok(None);
    };
    if let Some((attachment_id, document_revision_id)) = decode_core_attachment(&response, &request)
    {
        if manager.clear_exact(&active, Some(&request), false, None)
            != Some(ClearedNativeOperation::WithCandidate)
            || !active.connection.is_current()
        {
            return Ok(None);
        }
        let mut result = attachment_outcome(&active, "attached", None);
        result["candidateId"] = request.candidate_id.clone().into();
        result["attachmentId"] = attachment_id.into();
        result["documentRevisionId"] = document_revision_id.into();
        #[cfg(feature = "integration-harness")]
        crate::directory_integration_harness::observe_document_commit(
            &window,
            &serde_json::to_value(&request).unwrap_or(Value::Null),
            &result,
        );
        Ok(Some(result))
    } else if let Some(code) = core_problem(&response) {
        Ok((manager.clear_exact(&active, Some(&request), false, None)
            == Some(ClearedNativeOperation::WithCandidate)
            && active.connection.is_current())
        .then(|| attachment_outcome(&active, "rejected", Some(code))))
    } else {
        // Preserve the exact command for same-session status/retry after an
        // ambiguous response. Never turn a transport/decoder failure into a
        // success or a fresh attachment command.
        Ok(None)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pending_download_lock_wait_does_not_hold_attachment_state_or_block_cancellation() {
        use std::{sync::mpsc, thread, time::Duration};
        let fixture_parent = std::env::temp_dir().canonicalize().unwrap();
        let fixture_name = format!(
            "ro-document-lock-order-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        );
        let root = fixture_parent.join(&fixture_name);
        std::fs::create_dir(&root).unwrap();
        let lock = ApplicationLockManager::new(&root);
        let ticket = lock.begin_protected_action().unwrap();
        let manager = DocumentAttachmentManager::default();
        manager.set_installed(true);
        let generation = manager.shared.lock().unwrap().generation;
        let (held_tx, held_rx) = mpsc::channel();
        let (release_tx, release_rx) = mpsc::channel();
        let held_lock = lock.clone();
        let completion = thread::spawn(move || {
            held_lock.commit_protected_action(ticket, || {
                held_tx.send(()).unwrap();
                release_rx.recv_timeout(Duration::from_secs(3)).unwrap();
                Ok(())
            })
        });
        held_rx.recv_timeout(Duration::from_secs(2)).unwrap();
        let request: CopyDownloadRequest = serde_json::from_value(json!({"schemaVersion":"1.0","selection":selection(),
            "reviewId":"01900000-0000-7000-8000-000000000008",
            "operationId":"01900000-0000-7000-8000-000000000009","matchConfirmed":true,"permittedUse":"project-only"})).unwrap();
        let worker_manager = manager.clone();
        let worker_lock = lock.clone();
        let (started_tx, started_rx) = mpsc::channel();
        let download = thread::spawn(move || {
            started_tx.send(()).unwrap();
            consume_copy_review(
                &worker_manager,
                &worker_lock,
                &request,
                Some(1),
                (ticket, generation),
            )
            .is_err()
        });
        started_rx.recv_timeout(Duration::from_secs(2)).unwrap();
        thread::sleep(Duration::from_millis(50));
        let cancel_manager = manager.clone();
        let (cancel_tx, cancel_rx) = mpsc::channel();
        let cancellation = thread::spawn(move || {
            cancel_manager.cancel_all();
            cancel_tx.send(()).unwrap();
        });
        let cancelled_without_application_lock =
            cancel_rx.recv_timeout(Duration::from_millis(500)).is_ok();
        release_tx.send(()).unwrap();
        completion.join().unwrap().unwrap();
        assert!(download.join().unwrap());
        cancellation.join().unwrap();
        assert!(
            cancelled_without_application_lock,
            "download held attachment state while waiting for application lock"
        );
        assert!(manager.shared.lock().unwrap().active.is_none());
        assert!(lock.begin_protected_action().is_ok());
        // Only the uniquely owned policy fixture directory is removed.
        drop(lock);
        assert_eq!(
            root.canonicalize().unwrap(),
            fixture_parent.join(fixture_name)
        );
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn exact_intake_status_preserves_phase_and_cleanup_denial_without_availability() {
        let request: StatusRequest =
            serde_json::from_value(json!({"schemaVersion":"1.0","selection":selection(),
            "operationId":"01900000-0000-7000-8000-000000000007","commandId":null}))
            .unwrap();
        let manager = DocumentAttachmentManager::default();
        for (state, code, expected_status, expected_code) in [
            (
                "intake-running",
                "intake-downloading",
                "downloading",
                Value::Null,
            ),
            (
                "intake-running",
                "intake-validating",
                "validating",
                Value::Null,
            ),
            (
                "intake-failed",
                "acquisition-cleanup-required",
                "failed",
                json!("cleanup-required"),
            ),
            (
                "intake-failed",
                "attempts-exhausted",
                "failed",
                json!("interrupted"),
            ),
        ] {
            let mut body = selection();
            body["state"] = state.into();
            body["operationId"] = request.operation_id.clone().unwrap().into();
            body["commandId"] = Value::Null;
            body["candidateId"] = Value::Null;
            body["attachmentId"] = Value::Null;
            body["documentRevisionId"] = Value::Null;
            body["intakeCode"] = code.into();
            let response = crate::supervisor::CoreApiResponse {
                status: 200,
                content_type: "application/json".into(),
                trace_id: String::new(),
                etag: None,
                body: body.to_string(),
            };
            let status = decode_core_status(response.clone(), &request).unwrap();
            let projected = renderer_status(status, &request, &"a".repeat(32), &manager);
            assert_eq!(projected["status"], expected_status);
            assert_eq!(projected["code"], expected_code);
            assert!(projected["attachmentId"].is_null() && projected["retryRequest"].is_null());
            body["attachmentId"] = "01900000-0000-7000-8000-000000000009".into();
            assert!(
                decode_core_status(
                    crate::supervisor::CoreApiResponse {
                        body: body.to_string(),
                        ..response
                    },
                    &request
                )
                .is_none()
            );
        }
    }

    #[test]
    fn remote_mode_cannot_enter_the_picker_or_drop_begin_route() {
        let request = json!({"schemaVersion":"1.0","mode":"remote",
            "operationId":"01900000-0000-7000-8000-000000000007","selection":selection()});
        assert!(
            !serde_json::from_value::<BeginRequest>(request)
                .unwrap()
                .valid()
        );
    }

    #[test]
    fn copy_review_and_download_do_not_accept_renderer_urls_or_secrets() {
        let review = json!({"schemaVersion":"1.0","selection":selection(),
            "copyId":"01900000-0000-7000-8000-000000000007","copySha256":"a".repeat(64)});
        let download = json!({"schemaVersion":"1.0","selection":selection(),
            "reviewId":"01900000-0000-7000-8000-000000000008",
            "operationId":"01900000-0000-7000-8000-000000000009","matchConfirmed":true,"permittedUse":"project-only"});
        for field in [
            "url",
            "path",
            "confirmation",
            "actorId",
            "cookies",
            "redirectHosts",
        ] {
            let mut altered = review.clone();
            altered[field] = json!("untrusted");
            assert!(serde_json::from_value::<CopyReviewRequest>(altered).is_err());
            let mut altered = download.clone();
            altered[field] = json!("untrusted");
            assert!(serde_json::from_value::<CopyDownloadRequest>(altered).is_err());
        }
    }

    #[test]
    fn safe_copy_projection_strips_url_and_keeps_unknown_license_and_version() {
        let selected: AttachmentSelection = serde_json::from_value(selection()).unwrap();
        let mut location = CoreCopyLocation {
            location_id: "01900000-0000-7000-8000-000000000007".into(),
            project_id: selected.project_id.clone(),
            source_assertion_revision_id: selected.source_assertion_revision_id.clone(),
            source_revision_id: "01900000-0000-7000-8000-000000000008".into(),
            address: json!({"kind":"synthetic"}),
            source_sha256: "a".repeat(64),
            provider: "Synthetic provider".into(),
            location_key: "copy-one".into(),
            url: "https://oa.example.invalid/opaque-copy".into(),
            license: None,
            version: None,
            location_sha256: "b".repeat(64),
        };
        let projection = location.safe_metadata(&selected).unwrap();
        assert_eq!(projection["host"], "oa.example.invalid");
        assert!(projection.get("url").is_none());
        assert!(projection["license"].is_null() && projection["version"].is_null());
        location.url = "https://user:secret@oa.example.invalid/copy".into();
        assert!(location.safe_metadata(&selected).is_none());
    }

    fn selection() -> Value {
        json!({"projectId":"01900000-0000-7000-8000-000000000001",
            "workId":"01900000-0000-7000-8000-000000000002",
            "workRevisionId":"01900000-0000-7000-8000-000000000003",
            "versionId":"01900000-0000-7000-8000-000000000004",
            "versionRevisionId":"01900000-0000-7000-8000-000000000005",
            "sourceAssertionRevisionId":"01900000-0000-7000-8000-000000000006"})
    }

    fn synthetic_active(operation_id: &str, with_candidate: bool) -> ActiveAttachment {
        let selection: AttachmentSelection = serde_json::from_value(selection()).unwrap();
        ActiveAttachment {
            operation_id: operation_id.into(),
            mode: AttachmentMode::Drop,
            document: selection
                .document("C:/synthetic-attachment-test".into(), operation_id.into()),
            connection: Arc::new(NativeImportConnection::unavailable_for_attachment_test(
                &selection.project_id,
            )),
            selection,
            session_id: "a".repeat(32),
            owner: 1,
            ticket: 1,
            candidate: with_candidate.then(|| {
                (
                    "01900000-0000-7000-8000-000000000008".into(),
                    "b".repeat(64),
                )
            }),
            commit_request: None,
            generation: 0,
            staging: false,
            cancelling: false,
        }
    }

    fn synthetic_commit(operation_id: &str) -> CommitRequest {
        serde_json::from_value(json!({"schemaVersion":"1.0","operationId":operation_id,
            "sessionId":"a".repeat(32),"candidateId":"01900000-0000-7000-8000-000000000008",
            "confirmationSha256":"b".repeat(64),"commandId":"01900000-0000-7000-8000-000000000009",
            "selection":selection(),"matchConfirmed":true,"permittedUse":"project-only"}))
        .unwrap()
    }

    #[test]
    fn delayed_cancel_and_commit_cannot_clear_a_new_operation() {
        let manager = DocumentAttachmentManager::default();
        manager.set_installed(true);
        let old_id = "01900000-0000-7000-8000-000000000007";
        let new_id = "01900000-0000-7000-8000-00000000000a";
        assert!(manager.activate(synthetic_active(old_id, false)));
        let old = manager.shared.lock().unwrap().active.clone().unwrap();
        // The synthetic connection is deliberately no longer selected. A new
        // project may install B while A's Core reply is still in flight.
        assert!(manager.activate(synthetic_active(new_id, false)));
        assert!(manager.clear_exact(&old, None, false, None).is_none());
        assert!(
            manager
                .clear_exact(&old, Some(&synthetic_commit(old_id)), false, None)
                .is_none()
        );
        assert_eq!(
            manager
                .shared
                .lock()
                .unwrap()
                .active
                .as_ref()
                .unwrap()
                .operation_id,
            new_id
        );
    }

    #[test]
    fn cancel_and_commit_reservations_are_exclusive_and_ambiguous_cancel_reopens_native_admission()
    {
        let manager = DocumentAttachmentManager::default();
        manager.set_installed(true);
        let operation_id = "01900000-0000-7000-8000-000000000007";
        let commit = synthetic_commit(operation_id);
        assert!(manager.activate(synthetic_active(operation_id, true)));
        let active = manager.shared.lock().unwrap().active.clone().unwrap();
        assert!(manager.reserve_commit(&active, &commit));
        assert!(!manager.reserve_cancel(&active));
        assert!(manager.clear_exact(&active, None, false, None).is_none());
        assert_eq!(
            manager.clear_exact(&active, Some(&commit), false, None),
            Some(ClearedNativeOperation::WithCandidate)
        );

        assert!(manager.activate(synthetic_active(operation_id, true)));
        let active = manager.shared.lock().unwrap().active.clone().unwrap();
        assert!(manager.reserve_cancel(&active));
        assert!(!manager.reserve_commit(&active, &commit));
        assert!(matches!(
            candidate_cancel_receipt(None),
            CandidateCancelReceipt::Unconfirmed
        ));
        assert_eq!(
            manager.clear_exact(&active, None, true, None),
            Some(ClearedNativeOperation::WithCandidate)
        );
        assert!(manager.shared.lock().unwrap().active.is_none());
        assert!(manager.activate(synthetic_active(
            "01900000-0000-7000-8000-00000000000a",
            false
        )));
    }

    #[test]
    fn candidate_racing_native_only_cancel_is_not_reported_as_confirmed_core_cancel() {
        let manager = DocumentAttachmentManager::default();
        manager.set_installed(true);
        let operation_id = "01900000-0000-7000-8000-000000000007";
        assert!(manager.activate(synthetic_active(operation_id, false)));
        let before_stage_finishes = manager.shared.lock().unwrap().active.clone().unwrap();
        manager
            .shared
            .lock()
            .unwrap()
            .active
            .as_mut()
            .unwrap()
            .candidate = Some((
            "01900000-0000-7000-8000-000000000008".into(),
            "b".repeat(64),
        ));
        let cleared = manager.clear_exact(&before_stage_finishes, None, false, None);
        assert_eq!(cleared, Some(ClearedNativeOperation::WithCandidate));
        assert_ne!(cleared, Some(ClearedNativeOperation::BeforeCandidate));
        assert!(manager.shared.lock().unwrap().active.is_none());
    }

    #[test]
    fn strict_renderer_request_accepts_exact_ids_but_no_path_or_authority_fields() {
        let good = json!({"schemaVersion":"1.0","mode":"drop",
            "operationId":"01900000-0000-7000-8000-000000000007","selection":selection()});
        assert!(
            serde_json::from_value::<BeginRequest>(good.clone())
                .unwrap()
                .valid()
        );
        for (key, value) in [
            ("path", json!("C:/private.pdf")),
            ("root", json!("C:/project")),
            ("bytes", json!([37, 80, 68, 70])),
            ("sessionId", json!("a".repeat(32))),
        ] {
            let mut invalid = good.clone();
            invalid[key] = value;
            assert!(
                serde_json::from_value::<BeginRequest>(invalid).is_err(),
                "{key}"
            );
        }
        let mut invalid = good;
        invalid["selection"]["workRevisionId"] = "stale-or-invalid".into();
        assert!(
            !serde_json::from_value::<BeginRequest>(invalid)
                .unwrap()
                .valid()
        );
    }

    #[test]
    fn commit_requires_researcher_confirmation_and_project_only_literal() {
        let good = json!({"schemaVersion":"1.0","operationId":"01900000-0000-7000-8000-000000000007",
            "sessionId":"a".repeat(32),"candidateId":"01900000-0000-7000-8000-000000000008",
            "confirmationSha256":"b".repeat(64),"commandId":"01900000-0000-7000-8000-000000000009",
            "selection":selection(),"matchConfirmed":true,"permittedUse":"project-only"});
        assert!(
            serde_json::from_value::<CommitRequest>(good.clone())
                .unwrap()
                .valid()
        );
        for (key, value) in [
            ("matchConfirmed", json!(false)),
            ("permittedUse", json!("unknown")),
        ] {
            let mut invalid = good.clone();
            invalid[key] = value;
            assert!(
                !serde_json::from_value::<CommitRequest>(invalid)
                    .unwrap()
                    .valid()
            );
        }
        let mut invalid = good;
        invalid["rightsSubject"] = json!({"sourceId":"forged"});
        assert!(serde_json::from_value::<CommitRequest>(invalid).is_err());
    }

    #[test]
    fn failed_candidate_cancel_receipt_never_confirms_core_cancellation() {
        let response = crate::supervisor::CoreApiResponse {
            status: 204,
            content_type: String::new(),
            trace_id: String::new(),
            etag: None,
            body: String::new(),
        };
        assert!(matches!(
            candidate_cancel_receipt(Some(&response)),
            CandidateCancelReceipt::Confirmed
        ));
        assert!(matches!(
            candidate_cancel_receipt(None),
            CandidateCancelReceipt::Unconfirmed
        ));
        let malformed = crate::supervisor::CoreApiResponse {
            body: "unexpected".into(),
            ..response
        };
        assert!(matches!(
            candidate_cancel_receipt(Some(&malformed)),
            CandidateCancelReceipt::Unconfirmed
        ));
        // An absent or malformed reply cannot be reported as a confirmed
        // Core cancellation. Its native admission may be discarded for T03
        // orphan cleanup, as covered by the reservation test above.
    }

    #[test]
    fn cancellation_generation_fences_late_stage_publication() {
        let manager = DocumentAttachmentManager::default();
        manager.set_installed(true);
        let generation = manager.shared.lock().unwrap().generation;
        assert!(
            manager
                .shared
                .lock()
                .unwrap()
                .accepts_stage_generation(generation)
        );
        manager.cancel_all();
        assert!(
            !manager
                .shared
                .lock()
                .unwrap()
                .accepts_stage_generation(generation)
        );
        let next = manager.shared.lock().unwrap().generation;
        manager.set_installed(false);
        assert!(
            !manager
                .shared
                .lock()
                .unwrap()
                .accepts_stage_generation(next)
        );
    }

    #[test]
    fn exact_core_status_never_claims_reader_available_or_relabels_legacy_as_missing() {
        let operation = "01900000-0000-7000-8000-000000000007";
        let command = "01900000-0000-7000-8000-000000000008";
        let attachment = "01900000-0000-7000-8000-000000000009";
        let revision = "01900000-0000-7000-8000-00000000000a";
        let request: StatusRequest = serde_json::from_value(json!({"schemaVersion":"1.0",
            "selection":selection(),"operationId":operation,"commandId":command}))
        .unwrap();
        let mut body = request.selection.core_fields();
        body["state"] = "committed".into();
        body["operationId"] = operation.into();
        body["commandId"] = command.into();
        body["candidateId"] = Value::Null;
        body["attachmentId"] = attachment.into();
        body["documentRevisionId"] = revision.into();
        let response = crate::supervisor::CoreApiResponse {
            status: 200,
            content_type: "application/json".into(),
            trace_id: String::new(),
            etag: None,
            body: body.to_string(),
        };
        let found = decode_core_status(response.clone(), &request).unwrap();
        assert_eq!(
            renderer_status(
                found,
                &request,
                &"a".repeat(32),
                &DocumentAttachmentManager::default()
            )["status"],
            "processing"
        );
        let mut substituted = body.clone();
        substituted["workRevisionId"] = "01900000-0000-7000-8000-00000000000b".into();
        assert!(
            decode_core_status(
                crate::supervisor::CoreApiResponse {
                    body: substituted.to_string(),
                    ..response.clone()
                },
                &request
            )
            .is_none()
        );
        let legacy_request: StatusRequest = serde_json::from_value(json!({"schemaVersion":"1.0",
            "selection":selection(),"operationId":null,"commandId":null}))
        .unwrap();
        body["state"] = "legacy".into();
        body["operationId"] = Value::Null;
        let legacy = decode_core_status(
            crate::supervisor::CoreApiResponse {
                body: body.to_string(),
                ..response
            },
            &legacy_request,
        )
        .unwrap();
        assert_eq!(
            renderer_status(
                legacy,
                &legacy_request,
                &"a".repeat(32),
                &DocumentAttachmentManager::default()
            )["status"],
            "unavailable"
        );
    }

    #[test]
    fn stale_session_terminal_status_releases_only_exact_old_operation_without_retry() {
        let operation = "01900000-0000-7000-8000-000000000007";
        let command = "01900000-0000-7000-8000-000000000008";
        let request: StatusRequest = serde_json::from_value(json!({"schemaVersion":"1.0",
            "selection":selection(),"operationId":operation,"commandId":command}))
        .unwrap();
        let mut body = request.selection.core_fields();
        body["state"] = "stale-session".into();
        body["operationId"] = operation.into();
        body["commandId"] = Value::Null;
        body["candidateId"] = "01900000-0000-7000-8000-000000000009".into();
        body["attachmentId"] = Value::Null;
        body["documentRevisionId"] = Value::Null;
        let response = crate::supervisor::CoreApiResponse {
            status: 200,
            content_type: "application/json".into(),
            trace_id: String::new(),
            etag: None,
            body: body.to_string(),
        };
        let found = decode_core_status(response.clone(), &request).unwrap();
        let result = renderer_status(
            found,
            &request,
            &"a".repeat(32),
            &DocumentAttachmentManager::default(),
        );
        assert_eq!(result["status"], "unavailable");
        assert_eq!(result["code"], "interrupted");
        assert_eq!(result["operationId"], operation);
        assert!(result["commandId"].is_null());
        assert!(result["retryRequest"].is_null());
        for (field, value) in [
            ("state", json!("unavailable")),
            ("operationId", json!("01900000-0000-7000-8000-00000000000a")),
            ("commandId", json!("01900000-0000-7000-8000-00000000000b")),
            (
                "workRevisionId",
                json!("01900000-0000-7000-8000-00000000000c"),
            ),
        ] {
            let mut wrong = body.clone();
            wrong[field] = value;
            assert!(
                decode_core_status(
                    crate::supervisor::CoreApiResponse {
                        body: wrong.to_string(),
                        ..response.clone()
                    },
                    &request
                )
                .is_none(),
                "{field} must not resolve an old decision"
            );
        }
    }
}
