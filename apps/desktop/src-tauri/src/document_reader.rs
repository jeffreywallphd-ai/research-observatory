//! Fixed reader IPC: opaque selectors only; native owns root/session/token.

use crate::application_lock::ApplicationLockManager;
use crate::document_runtime::current_document_context;
use crate::supervisor::{NativeDocumentAction, RuntimeSupervisor};
use serde::Deserialize;
use serde_json::{Value, json};
use std::sync::Arc;
use tauri::State;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ReaderRevisionsRequest {
    schema_version: String,
    project_id: String,
    attachment_id: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ReaderOutlineRequest {
    schema_version: String,
    project_id: String,
    revision_id: String,
    after_node_id: Option<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct AnchorListRequest {
    schema_version: String,
    project_id: String,
    revision_id: String,
    after_id: Option<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct AnchorReadRequest {
    schema_version: String,
    project_id: String,
    anchor_id: String,
    expected_revision_id: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct CodepointRange {
    start: u64,
    end: u64,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct AnchorSelection {
    schema_version: String,
    revision_id: String,
    node_id: String,
    normalized_range: Option<CodepointRange>,
}

impl AnchorSelection {
    fn valid(&self) -> bool {
        self.schema_version == "1.0"
            && uuid(&self.revision_id)
            && uuid(&self.node_id)
            && self.normalized_range.as_ref().is_none_or(|range| {
                range.start < range.end
                    && range.end <= 9_007_199_254_740_991
                    && range.end - range.start <= 2048
            })
    }

    fn core(&self) -> Value {
        json!({"schemaVersion":"1.0", "revisionId":self.revision_id,"nodeId":self.node_id,
            "normalizedRange":self.normalized_range.as_ref().map(|range| json!({"start":range.start,"end":range.end}))})
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct AnchorCreateRequest {
    schema_version: String,
    project_id: String,
    command_id: String,
    selection: AnchorSelection,
}

fn uuid(value: &str) -> bool {
    crate::supervisor::canonical_uuid_v7(value)
}

fn project(schema: &str, id: &str) -> bool {
    schema == "1.0" && crate::supervisor::canonical_project_id(id)
}

async fn request(
    window: tauri::WebviewWindow,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    project_id: String,
    action: NativeDocumentAction,
    fields: Value,
) -> Result<Option<Value>, ()> {
    let owner = crate::directory_window_handle(&window).ok_or(())?;
    let ticket = lock.begin_protected_action().map_err(|_| ())?;
    let connection = Arc::new(
        supervisor
            .native_document_connection(&project_id)
            .map_err(|_| ())?,
    );
    let worker = Arc::clone(&connection);
    let response = tauri::async_runtime::spawn_blocking(move || {
        let context = current_document_context(&worker, &project_id).map_err(|_| ())?;
        let mut body = fields.as_object().ok_or(())?.clone();
        body.insert("root".into(), worker.document_root().into());
        body.insert("projectId".into(), project_id.into());
        body.insert("sessionId".into(), context.session_id.into());
        worker
            .document_request(action, Value::Object(body))
            .map_err(|_| ())
    })
    .await
    .map_err(|_| ())??;
    if !connection.is_current()
        || lock.finish_protected_action(ticket).is_err()
        || crate::directory_window_handle(&window) != Some(owner)
        || response.status != 200
        || response.content_type != "application/json"
        || response.body.len() > 131_072
    {
        return Ok(None);
    }
    serde_json::from_str(&response.body)
        .map(Some)
        .map_err(|_| ())
}

#[tauri::command]
pub(crate) async fn document_reader_revisions(
    window: tauri::WebviewWindow,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: ReaderRevisionsRequest,
) -> Result<Option<Value>, ()> {
    if !project(&request.schema_version, &request.project_id) || !uuid(&request.attachment_id) {
        return Ok(None);
    }
    self::request(
        window,
        supervisor,
        lock,
        request.project_id,
        NativeDocumentAction::ReaderRevisions,
        json!({"attachmentId":request.attachment_id}),
    )
    .await
}

#[tauri::command]
pub(crate) async fn document_reader_outline(
    window: tauri::WebviewWindow,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: ReaderOutlineRequest,
) -> Result<Option<Value>, ()> {
    if !project(&request.schema_version, &request.project_id)
        || !uuid(&request.revision_id)
        || request.after_node_id.as_ref().is_some_and(|id| !uuid(id))
    {
        return Ok(None);
    }
    self::request(
        window,
        supervisor,
        lock,
        request.project_id,
        NativeDocumentAction::ReaderOutline,
        json!({"revisionId":request.revision_id,"afterNodeId":request.after_node_id,"limit":50}),
    )
    .await
}

#[tauri::command]
pub(crate) async fn document_reader_anchor_create(
    window: tauri::WebviewWindow,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: AnchorCreateRequest,
) -> Result<Option<Value>, ()> {
    if !project(&request.schema_version, &request.project_id)
        || !uuid(&request.command_id)
        || !request.selection.valid()
    {
        return Ok(None);
    }
    self::request(
        window,
        supervisor,
        lock,
        request.project_id,
        NativeDocumentAction::AnchorCreate,
        json!({"commandId":request.command_id,"selection":request.selection.core()}),
    )
    .await
}

#[tauri::command]
pub(crate) async fn document_reader_anchor_read(
    window: tauri::WebviewWindow,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: AnchorReadRequest,
) -> Result<Option<Value>, ()> {
    if !project(&request.schema_version, &request.project_id)
        || !uuid(&request.anchor_id)
        || !uuid(&request.expected_revision_id)
    {
        return Ok(None);
    }
    self::request(
        window,
        supervisor,
        lock,
        request.project_id,
        NativeDocumentAction::AnchorRead,
        json!({"anchorId":request.anchor_id,"expectedRevisionId":request.expected_revision_id}),
    )
    .await
}

#[tauri::command]
pub(crate) async fn document_reader_anchor_list(
    window: tauri::WebviewWindow,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: AnchorListRequest,
) -> Result<Option<Value>, ()> {
    if !project(&request.schema_version, &request.project_id)
        || !uuid(&request.revision_id)
        || request.after_id.as_ref().is_some_and(|id| !uuid(id))
    {
        return Ok(None);
    }
    self::request(
        window,
        supervisor,
        lock,
        request.project_id,
        NativeDocumentAction::AnchorList,
        json!({"revisionId":request.revision_id,"afterId":request.after_id,"limit":100}),
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn renderer_cannot_supply_root_actor_quote_or_geometry_authority() {
        let project = "00000000-0000-7000-8000-000000000001";
        let base = json!({"schemaVersion":"1.0","projectId":project,"commandId":project,
                         "selection":{"schemaVersion":"1.0","revisionId":project,"nodeId":project,
                         "normalizedRange":{"start":5,"end":6}}});
        let valid: AnchorCreateRequest = serde_json::from_value(base.clone()).unwrap();
        assert!(valid.selection.valid());
        for key in ["root", "actorId", "quote", "pageRegion"] {
            let mut changed = base.clone();
            changed[key] = json!("untrusted");
            assert!(serde_json::from_value::<AnchorCreateRequest>(changed).is_err());
        }
        let mut bad = base.clone();
        bad["selection"]["normalizedRange"]["end"] = json!(2054);
        assert!(
            !serde_json::from_value::<AnchorCreateRequest>(bad)
                .unwrap()
                .selection
                .valid()
        );
        let mut bad = base;
        bad["selection"]["quote"] = json!("untrusted");
        assert!(serde_json::from_value::<AnchorCreateRequest>(bad).is_err());
    }
}
