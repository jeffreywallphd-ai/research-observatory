use crate::application_lock::ApplicationLockManager;
use crate::document_runtime::current_document_context;
use crate::supervisor::{NativeDocumentAction, RuntimeSupervisor};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::sync::Arc;
use tauri::State;

fn id(value: &str) -> bool {
    crate::supervisor::canonical_uuid_v7(value)
}
fn sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}
fn rationale(value: &str) -> bool {
    !value.trim().is_empty()
        && value.chars().count() <= 1000
        && !value
            .chars()
            .any(|ch| ch.is_control() && ch != '\n' && ch != '\t')
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Batch {
    schema_version: String,
    command_id: String,
    base_revision_ids: Vec<String>,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Mapping {
    obligation_id: String,
    node_id: String,
    related_node_id: Option<String>,
    reference_id: Option<String>,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Reconciliation {
    schema_version: String,
    command_id: String,
    comparison_revision_id: String,
    expected_plan_revision_id: Option<String>,
    rationale: String,
    mappings: Vec<Mapping>,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Acceptance {
    schema_version: String,
    command_id: String,
    plan_revision_id: String,
    expected_current_revision_id: String,
    confirmation_sha256: String,
    expected_graph_sha256: String,
    decision: String,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Continuation {
    schema_version: String,
    command_id: String,
    batch_revision_id: String,
    item_id: String,
    expected_job_id: Option<String>,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Cancellation {
    schema_version: String,
    command_id: String,
    batch_revision_id: String,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(
    tag = "action",
    rename_all = "kebab-case",
    rename_all_fields = "camelCase",
    deny_unknown_fields
)]
enum Command {
    Queue {
        after_batch_id: Option<String>,
    },
    Create {
        batch: Batch,
    },
    Read {
        batch_revision_id: String,
    },
    ReadImpact {
        batch_revision_id: String,
        item_id: String,
    },
    Compare {
        batch_revision_id: String,
        item_id: String,
        offset: u32,
    },
    Reconcile {
        reconciliation: Reconciliation,
    },
    Accept {
        acceptance: Acceptance,
    },
    Continue {
        continuation: Continuation,
    },
    Cancel {
        cancellation: Cancellation,
    },
    ResumeImpact {
        batch_revision_id: String,
        item_id: String,
        expected_checkpoint_sha256: String,
    },
}
impl Command {
    fn valid(&self) -> bool {
        match self {
            Self::Queue { after_batch_id } => after_batch_id.as_deref().is_none_or(id),
            Self::Create { batch: b } => {
                b.schema_version == "1.0"
                    && id(&b.command_id)
                    && (1..=10).contains(&b.base_revision_ids.len())
                    && b.base_revision_ids.iter().all(|value| id(value))
                    && b.base_revision_ids
                        .iter()
                        .enumerate()
                        .all(|(index, value)| !b.base_revision_ids[..index].contains(value))
            }
            Self::Read { batch_revision_id } => id(batch_revision_id),
            Self::ReadImpact {
                batch_revision_id,
                item_id,
            } => id(batch_revision_id) && id(item_id),
            Self::Compare {
                batch_revision_id,
                item_id,
                offset,
            } => id(batch_revision_id) && id(item_id) && *offset <= 100000,
            Self::Reconcile { reconciliation: r } => {
                r.schema_version == "1.0"
                    && id(&r.command_id)
                    && id(&r.comparison_revision_id)
                    && r.expected_plan_revision_id.as_deref().is_none_or(id)
                    && rationale(&r.rationale)
                    && r.mappings.len() <= 32
                    && r.mappings.iter().all(|mapping| {
                        sha(&mapping.obligation_id)
                            && id(&mapping.node_id)
                            && mapping.related_node_id.as_deref().is_none_or(id)
                            && mapping.reference_id.as_deref().is_none_or(id)
                    })
                    && r.mappings.iter().enumerate().all(|(index, mapping)| {
                        !r.mappings[..index]
                            .iter()
                            .any(|other| other.obligation_id == mapping.obligation_id)
                    })
            }
            Self::Accept { acceptance: a } => {
                a.schema_version == "1.0"
                    && id(&a.command_id)
                    && id(&a.plan_revision_id)
                    && id(&a.expected_current_revision_id)
                    && sha(&a.confirmation_sha256)
                    && sha(&a.expected_graph_sha256)
                    && a.decision == "accept-reparse"
            }
            Self::Continue { continuation: c } => {
                c.schema_version == "1.0"
                    && id(&c.command_id)
                    && id(&c.batch_revision_id)
                    && id(&c.item_id)
                    && c.expected_job_id.as_deref().is_none_or(id)
            }
            Self::Cancel { cancellation: c } => {
                c.schema_version == "1.0" && id(&c.command_id) && id(&c.batch_revision_id)
            }
            Self::ResumeImpact {
                batch_revision_id,
                item_id,
                expected_checkpoint_sha256,
            } => id(batch_revision_id) && id(item_id) && sha(expected_checkpoint_sha256),
        }
    }
    fn writes(&self) -> bool {
        !matches!(
            self,
            Self::Queue { .. } | Self::Read { .. } | Self::ReadImpact { .. } | Self::Compare { .. }
        )
    }
    fn route(&self) -> NativeDocumentAction {
        match self {
            Self::Queue { .. } => NativeDocumentAction::ReprocessingQueue,
            Self::Create { .. } => NativeDocumentAction::ReprocessingCreate,
            Self::Read { .. } => NativeDocumentAction::ReprocessingRead,
            Self::ReadImpact { .. } => NativeDocumentAction::ReprocessingReadImpact,
            Self::Compare { .. } => NativeDocumentAction::ReprocessingCompare,
            Self::Reconcile { .. } => NativeDocumentAction::ReprocessingReconcile,
            Self::Accept { .. } => NativeDocumentAction::ReprocessingAccept,
            Self::Continue { .. } => NativeDocumentAction::ReprocessingContinue,
            Self::Cancel { .. } => NativeDocumentAction::ReprocessingCancel,
            Self::ResumeImpact { .. } => NativeDocumentAction::ReprocessingResumeImpact,
        }
    }
    fn matches(&self, value: &Value, project: &str) -> bool {
        if value["schemaVersion"] != "1.0" || value["projectId"] != project {
            return false;
        }
        match self {
            Self::Queue { .. } => value["items"].as_array().is_some_and(|items| {
                items.len() <= 10 && items.iter().all(|item| item["projectId"] == project)
            }),
            Self::Create { batch } => value["items"].as_array().is_some_and(|items| {
                items.len() == batch.base_revision_ids.len()
                    && items
                        .iter()
                        .zip(&batch.base_revision_ids)
                        .all(|(item, base)| item["baseRevisionId"] == *base)
            }),
            Self::Read { batch_revision_id } => value["batchRevisionId"] == *batch_revision_id,
            Self::ReadImpact { item_id, .. } => {
                value["itemId"] == *item_id
                    && value["batchRevisionId"].as_str().is_some_and(id)
                    && value["scholarlyVerification"] == "unverified"
            }
            Self::Compare {
                batch_revision_id,
                item_id,
                ..
            }
            | Self::ResumeImpact {
                batch_revision_id,
                item_id,
                ..
            } => {
                value["batchRevisionId"] == *batch_revision_id
                    && value["itemId"] == *item_id
                    && value["scholarlyVerification"] == "unverified"
            }
            Self::Reconcile { reconciliation } => {
                value["comparisonRevisionId"] == reconciliation.comparison_revision_id
                    && value["planRevisionId"].as_str().is_some_and(id)
                    && value["scholarlyVerification"] == "unverified"
            }
            Self::Accept { acceptance } => {
                value["previousRevisionId"] == acceptance.expected_current_revision_id
                    && value["revisionId"].as_str().is_some_and(id)
                    && value["revisionId"] != value["previousRevisionId"]
                    && value["scholarlyVerification"] == "unverified"
            }
            Self::Continue { continuation } => {
                value["batchRevisionId"].as_str().is_some_and(id)
                    && value["batchRevisionId"] != continuation.batch_revision_id
                    && value["items"].as_array().is_some_and(|items| {
                        items
                            .iter()
                            .any(|item| item["itemId"] == continuation.item_id)
                    })
            }
            Self::Cancel { cancellation } => {
                value["batchRevisionId"].as_str().is_some_and(id)
                    && value["batchRevisionId"] != cancellation.batch_revision_id
                    && value["state"] == "cancelled"
            }
        }
    }
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ReprocessingRequest {
    schema_version: String,
    project_id: String,
    command: Command,
}

#[tauri::command]
pub(crate) async fn document_reprocessing_request(
    window: tauri::WebviewWindow,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: ReprocessingRequest,
) -> Result<Option<Value>, String> {
    let denied = || "reprocessing-unavailable".to_string();
    let lost = || {
        if request.command.writes() {
            "reprocessing-outcome-unknown"
        } else {
            "reprocessing-unavailable"
        }
        .to_string()
    };
    if request.schema_version != "1.0"
        || !crate::supervisor::canonical_project_id(&request.project_id)
        || !request.command.valid()
    {
        return Err(denied());
    }
    let owner = crate::directory_window_handle(&window).ok_or_else(denied)?;
    let ticket = lock.begin_protected_action().map_err(|_| denied())?;
    let connection = Arc::new(
        supervisor
            .native_document_connection(&request.project_id)
            .map_err(|_| denied())?,
    );
    let worker = Arc::clone(&connection);
    let selected = request.clone();
    let gate = lock.inner().clone();
    let owned_window = window.clone();
    let response = tauri::async_runtime::spawn_blocking(move || {
        let context = current_document_context(&worker, &selected.project_id)
            .map_err(|_| "reprocessing-unavailable".to_string())?;
        let mut body = serde_json::to_value(&selected.command)
            .map_err(|_| "reprocessing-unavailable".to_string())?;
        let fields = body
            .as_object_mut()
            .ok_or_else(|| "reprocessing-unavailable".to_string())?;
        fields.remove("action");
        fields.insert("root".into(), json!(worker.document_root()));
        fields.insert("projectId".into(), json!(selected.project_id));
        fields.insert("sessionId".into(), json!(context.session_id));
        worker
            .document_request_owned(selected.command.route(), body, &|| {
                gate.finish_protected_action(ticket).is_ok()
                    && crate::directory_window_handle(&owned_window) == Some(owner)
            })
            .map_err(|_| {
                if selected.command.writes() {
                    "reprocessing-outcome-unknown"
                } else {
                    "reprocessing-unavailable"
                }
                .to_string()
            })
    })
    .await
    .map_err(|_| lost())??;
    if !connection.is_current()
        || lock.finish_protected_action(ticket).is_err()
        || crate::directory_window_handle(&window) != Some(owner)
    {
        return Ok(None);
    }
    if response.status != 200 {
        return Err(if response.status >= 500 {
            lost()
        } else {
            denied()
        });
    }
    if response.content_type != "application/json" || response.body.len() > 131072 {
        return Err(lost());
    }
    let value: Value = serde_json::from_str(&response.body).map_err(|_| lost())?;
    if !request.command.matches(&value, &request.project_id) {
        return Err(lost());
    }
    lock.commit_protected_action(ticket, || {
        connection.publish_current(|| {
            if crate::directory_window_handle(&window) != Some(owner) {
                return Err("RO-DOCUMENT-REPROCESSING-DENIED");
            }
            Ok(Some(value))
        })
    })
    .map_err(|_| lost())
}

#[cfg(test)]
mod tests {
    use super::*;
    const ID: &str = "019a0010-1234-7123-8123-123456789abc";
    #[test]
    fn authority_is_native_and_request_bounds_are_closed() {
        assert!(serde_json::from_value::<ReprocessingRequest>(json!({"schemaVersion":"1.0","projectId":"project-local","command":{"action":"queue","afterBatchId":null},"root":"injected"})).is_err());
        assert!(serde_json::from_value::<Command>(json!({"action":"accept","acceptance":{"schemaVersion":"1.0","commandId":ID,"planRevisionId":ID,"expectedCurrentRevisionId":ID,"confirmationSha256":"a".repeat(64),"expectedGraphSha256":"b".repeat(64),"decision":"accept-reparse","actorId":ID}})).is_err());
        let acceptance: Command = serde_json::from_value(json!({"action":"accept","acceptance":{"schemaVersion":"1.0","commandId":ID,"planRevisionId":ID,"expectedCurrentRevisionId":ID,"confirmationSha256":"a".repeat(64),"expectedGraphSha256":"b".repeat(64),"decision":"accept-reparse"}})).unwrap();
        assert!(acceptance.valid() && acceptance.writes());
        let duplicate: Command = serde_json::from_value(json!({"action":"create","batch":{"schemaVersion":"1.0","commandId":ID,"baseRevisionIds":[ID,ID]}})).unwrap();
        assert!(!duplicate.valid());
        let oversized: Command = serde_json::from_value(json!({"action":"create","batch":{"schemaVersion":"1.0","commandId":ID,"baseRevisionIds":vec![ID;11]}})).unwrap();
        assert!(!oversized.valid());
        let page: Command = serde_json::from_value(
            json!({"action":"compare","batchRevisionId":ID,"itemId":ID,"offset":100001}),
        )
        .unwrap();
        assert!(!page.valid());
        assert!(!rationale(" ") && !sha(&"A".repeat(64)));
    }
}

#[cfg(all(test, feature = "integration-harness"))]
mod windows_integration_tests;
