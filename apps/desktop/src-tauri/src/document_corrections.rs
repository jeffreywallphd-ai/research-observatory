//! Closed human-correction IPC. Native supplies the current root and session.
use crate::application_lock::ApplicationLockManager;
use crate::document_runtime::current_document_context;
use crate::supervisor::{NativeDocumentAction, RuntimeSupervisor};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::sync::Arc;
use tauri::State;

fn id(value: &str) -> bool {
    crate::supervisor::canonical_uuid_v7(value)
}
fn sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn text(value: &str, max: usize) -> bool {
    !value.trim().is_empty() && value.chars().count() <= max
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Region {
    kind: String,
    page_index: u16,
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
    unit: String,
    origin: String,
    frame: String,
}
impl Region {
    fn valid(&self) -> bool {
        self.kind == "page-region"
            && self.page_index < 500
            && self.unit == "points"
            && self.origin == "top-left"
            && self.frame == "unrotated-source-page"
            && [self.x0, self.y0, self.x1, self.y1]
                .iter()
                .all(|v| v.is_finite() && *v >= 0.0)
            && self.x0 <= self.x1
            && self.y0 <= self.y1
    }
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(
    tag = "op",
    rename_all = "kebab-case",
    rename_all_fields = "camelCase",
    deny_unknown_fields
)]
enum Operation {
    Relabel {
        node_id: String,
        expected_node_sha256: String,
        label: String,
    },
    Reorder {
        node_id: String,
        expected_node_sha256: String,
        before_node_id: Option<String>,
    },
    Split {
        node_id: String,
        expected_node_sha256: String,
        at: u64,
    },
    Merge {
        node_id: String,
        expected_node_sha256: String,
        with_node_id: String,
        expected_with_node_sha256: String,
    },
    ReferenceRematch {
        node_id: String,
        expected_node_sha256: String,
        reference_id: String,
        expected_reference_sha256: String,
        work_id: String,
        work_revision_id: String,
    },
    AdjustAnchor {
        node_id: String,
        expected_node_sha256: String,
        locator: Region,
    },
    Exclude {
        node_id: String,
        expected_node_sha256: String,
    },
}
impl Operation {
    fn valid(&self) -> bool {
        let (node, digest, extra) = match self {
            Self::Relabel {
                node_id,
                expected_node_sha256,
                label,
            } => (node_id, expected_node_sha256, text(label, 160)),
            Self::Reorder {
                node_id,
                expected_node_sha256,
                before_node_id,
            } => (
                node_id,
                expected_node_sha256,
                before_node_id.as_deref().is_none_or(id),
            ),
            Self::Split {
                node_id,
                expected_node_sha256,
                at,
            } => (node_id, expected_node_sha256, *at <= 1_000_000),
            Self::Merge {
                node_id,
                expected_node_sha256,
                with_node_id,
                expected_with_node_sha256,
            } => (
                node_id,
                expected_node_sha256,
                id(with_node_id) && sha(expected_with_node_sha256),
            ),
            Self::ReferenceRematch {
                node_id,
                expected_node_sha256,
                reference_id,
                expected_reference_sha256,
                work_id,
                work_revision_id,
            } => (
                node_id,
                expected_node_sha256,
                id(reference_id)
                    && sha(expected_reference_sha256)
                    && id(work_id)
                    && id(work_revision_id),
            ),
            Self::AdjustAnchor {
                node_id,
                expected_node_sha256,
                locator,
            } => (node_id, expected_node_sha256, locator.valid()),
            Self::Exclude {
                node_id,
                expected_node_sha256,
            } => (node_id, expected_node_sha256, true),
        };
        id(node) && sha(digest) && extra
    }
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Patch {
    schema_version: String,
    base_revision_id: String,
    expected_structure_sha256: String,
    operations: Vec<Operation>,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Save {
    schema_version: String,
    command_id: String,
    draft_id: Option<String>,
    expected_draft_revision_id: Option<String>,
    patch: Patch,
    rationale: String,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Accept {
    schema_version: String,
    command_id: String,
    draft_revision_id: String,
    expected_current_revision_id: String,
    confirmation_sha256: String,
    decision: String,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Discard {
    schema_version: String,
    command_id: String,
    draft_revision_id: String,
    confirmation_sha256: String,
    rationale: String,
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
        after_job_id: Option<String>,
    },
    Page {
        revision_id: String,
        draft_revision_id: Option<String>,
        offset: u16,
    },
    Save {
        correction: Save,
    },
    Accept {
        acceptance: Accept,
    },
    Discard {
        discard: Discard,
    },
    Draft {
        draft_revision_id: String,
    },
    Impact {
        draft_revision_id: String,
    },
    Targets {
        after_work_id: Option<String>,
    },
    Quality {
        job_id: String,
    },
}
impl Command {
    fn valid(&self) -> bool {
        match self {
            Self::Queue { after_job_id } => after_job_id.as_deref().is_none_or(id),
            Self::Targets { after_work_id } => after_work_id.as_deref().is_none_or(id),
            Self::Page {
                revision_id,
                draft_revision_id,
                offset,
            } => id(revision_id) && draft_revision_id.as_deref().is_none_or(id) && *offset < 10000,
            Self::Quality { job_id } => id(job_id),
            Self::Draft { draft_revision_id } | Self::Impact { draft_revision_id } => {
                id(draft_revision_id)
            }
            Self::Save { correction: c } => {
                c.schema_version == "1.0"
                    && id(&c.command_id)
                    && text(&c.rationale, 1000)
                    && (c.draft_id.is_some() == c.expected_draft_revision_id.is_some())
                    && c.draft_id.as_deref().is_none_or(id)
                    && c.expected_draft_revision_id.as_deref().is_none_or(id)
                    && c.patch.schema_version == "1.0"
                    && id(&c.patch.base_revision_id)
                    && sha(&c.patch.expected_structure_sha256)
                    && c.patch.operations.len() <= 32
                    && c.patch.operations.iter().all(Operation::valid)
            }
            Self::Accept { acceptance: a } => {
                a.schema_version == "1.0"
                    && id(&a.command_id)
                    && id(&a.draft_revision_id)
                    && id(&a.expected_current_revision_id)
                    && sha(&a.confirmation_sha256)
                    && a.decision == "accept-correction"
            }
            Self::Discard { discard: d } => {
                d.schema_version == "1.0"
                    && id(&d.command_id)
                    && id(&d.draft_revision_id)
                    && sha(&d.confirmation_sha256)
                    && text(&d.rationale, 1000)
            }
        }
    }
    fn route(&self) -> NativeDocumentAction {
        match self {
            Self::Queue { .. } => NativeDocumentAction::CorrectionQueue,
            Self::Page { .. } => NativeDocumentAction::CorrectionPage,
            Self::Save { .. } => NativeDocumentAction::CorrectionSave,
            Self::Accept { .. } => NativeDocumentAction::CorrectionAccept,
            Self::Discard { .. } => NativeDocumentAction::CorrectionDiscard,
            Self::Draft { .. } => NativeDocumentAction::CorrectionDraft,
            Self::Impact { .. } => NativeDocumentAction::CorrectionImpact,
            Self::Targets { .. } => NativeDocumentAction::CorrectionTargets,
            Self::Quality { .. } => NativeDocumentAction::ParseQuality,
        }
    }
    fn matches(&self, v: &Value, project: &str) -> bool {
        let record = &v["record"];
        match self {
            Self::Quality { job_id } => {
                v["source"]["projectId"] == project
                    && v["jobId"] == *job_id
                    && v["assessment"]["scholarlyVerification"] == "unverified"
            }
            Self::Save { correction } => {
                record["projectId"] == project
                    && record["commandId"] == correction.command_id
                    && record["patch"]["baseRevisionId"] == correction.patch.base_revision_id
            }
            Self::Discard { discard } => {
                record["projectId"] == project
                    && record["commandId"] == discard.command_id
                    && record["previousDraftRevisionId"] == discard.draft_revision_id
                    && record["state"] == "discarded"
            }
            Self::Draft { draft_revision_id } => {
                record["projectId"] == project && record["revisionId"] == *draft_revision_id
            }
            Self::Page { revision_id, .. } => {
                v["projectId"] == project
                    && v["revisionId"] == *revision_id
                    && v["scholarlyVerification"] == "unverified"
            }
            Self::Accept { acceptance } => {
                v["projectId"] == project
                    && v["previousRevisionId"] == acceptance.expected_current_revision_id
                    && v["scholarlyVerification"] == "unverified"
            }
            Self::Impact { draft_revision_id } => {
                v["projectId"] == project
                    && v["draftRevisionId"] == *draft_revision_id
                    && v["state"] == "prospective-rechecked-at-acceptance"
            }
            Self::Queue { .. } | Self::Targets { .. } => {
                v["projectId"] == project && v["schemaVersion"] == "1.0"
            }
        }
    }
}
#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct CorrectionRequest {
    schema_version: String,
    project_id: String,
    command: Command,
}

#[tauri::command]
pub(crate) async fn document_correction_request(
    window: tauri::WebviewWindow,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: CorrectionRequest,
) -> Result<Option<Value>, String> {
    let denied = || "correction-unavailable".to_string();
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
            .map_err(|_| "correction-unavailable".to_string())?;
        let mut body = serde_json::to_value(&selected.command)
            .map_err(|_| "correction-unavailable".to_string())?;
        let fields = body
            .as_object_mut()
            .ok_or_else(|| "correction-unavailable".to_string())?;
        fields.remove("action");
        fields.insert("root".into(), json!(worker.document_root()));
        fields.insert("projectId".into(), json!(selected.project_id));
        fields.insert("sessionId".into(), json!(context.session_id));
        worker
            .document_request_owned(selected.command.route(), body, &|| {
                gate.finish_protected_action(ticket).is_ok()
                    && crate::directory_window_handle(&owned_window) == Some(owner)
            })
            .map_err(|_| "correction-outcome-unknown".to_string())
    })
    .await
    .map_err(|_| "correction-outcome-unknown".to_string())??;
    if !connection.is_current()
        || lock.finish_protected_action(ticket).is_err()
        || crate::directory_window_handle(&window) != Some(owner)
    {
        return Ok(None);
    }
    if response.status != 200
        || response.content_type != "application/json"
        || response.body.len() > 131072
    {
        return Err(denied());
    }
    let value: Value = serde_json::from_str(&response.body).map_err(|_| denied())?;
    if !request.command.matches(&value, &request.project_id) {
        return Err(denied());
    }
    lock.commit_protected_action(ticket, || {
        connection.publish_current(|| {
            if crate::directory_window_handle(&window) != Some(owner) {
                return Err("RO-DOCUMENT-CORRECTION-DENIED");
            }
            Ok(Some(value))
        })
    })
    .map_err(|_| denied())
}

#[cfg(test)]
mod tests {
    use super::*;
    const ID: &str = "019a0010-1234-7123-8123-123456789abc";
    #[test]
    fn closed_authority_and_bounds() {
        assert!(serde_json::from_value::<CorrectionRequest>(json!({"schemaVersion":"1.0","projectId":"project-local","command":{"action":"queue","afterJobId":null},"root":"injected"})).is_err());
        assert!(serde_json::from_value::<Command>(json!({"action":"accept","acceptance":{"schemaVersion":"1.0","commandId":ID,"draftRevisionId":ID,"expectedCurrentRevisionId":ID,"confirmationSha256":"a".repeat(64),"decision":"accept-correction","actorId":ID}})).is_err());
        let bad: Command = serde_json::from_value(
            json!({"action":"page","revisionId":ID,"draftRevisionId":null,"offset":10000}),
        )
        .unwrap();
        assert!(!bad.valid());
        let good: Operation = serde_json::from_value(json!({"op":"relabel","nodeId":ID,"expectedNodeSha256":"a".repeat(64),"label":"Human label"})).unwrap();
        assert!(good.valid());
        assert!(serde_json::from_value::<Operation>(json!({"op":"relabel","nodeId":ID,"expectedNodeSha256":"a".repeat(64),"label":"Human label","authority":"grant"})).is_err());
    }
}

#[cfg(all(test, feature = "integration-harness"))]
mod windows_integration_tests;
