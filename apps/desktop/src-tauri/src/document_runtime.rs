//! Native-only document attachment intake. No renderer path or file handle crosses this boundary.

use crate::application_lock::ApplicationLockManager;
use crate::directory_picker::{DirectoryPickerManager, PickerFailure};
use crate::import_source::{HeldImportSource, SourceSeal};
use crate::supervisor::{
    CoreApiResponse, DocumentStageSelection, NativeImportConnection, RuntimeSupervisor,
};
use serde::Deserialize;
use std::sync::Arc;

#[derive(Clone)]
pub(crate) struct DocumentSelection {
    pub root: String,
    pub project_id: String,
    pub declared_media_type: Option<String>,
    pub source_assertion_revision_id: String,
    pub work_id: String,
    pub work_revision_id: String,
    pub version_id: String,
    pub version_revision_id: String,
}

impl DocumentSelection {
    fn valid(&self) -> bool {
        crate::directory_picker::local_path_syntax(&self.root)
            && crate::supervisor::canonical_project_id(&self.project_id)
            && self
                .declared_media_type
                .as_ref()
                .is_none_or(|value| !value.is_empty() && value.len() <= 200)
            && [
                &self.source_assertion_revision_id,
                &self.work_id,
                &self.work_revision_id,
                &self.version_id,
                &self.version_revision_id,
            ]
            .iter()
            .all(|value| crate::supervisor::canonical_uuid_v7(value))
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct DocumentContext {
    project_id: String,
    session_id: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct DocumentCandidate {
    pub candidate_id: String,
    pub project_id: String,
    pub source_assertion_revision_id: String,
    pub work_id: String,
    pub work_revision_id: String,
    pub version_id: String,
    pub version_revision_id: String,
    pub object_sha256: String,
    pub byte_length: u64,
    pub format: String,
    pub media_type: String,
    pub source_name: String,
    pub confirmation_required: bool,
    pub candidate_sha256: String,
    pub rights_subject: serde_json::Value,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct DocumentProblem {
    pub r#type: String,
    pub title: String,
    pub status: u16,
    pub detail: String,
    pub code: String,
    pub trace_id: String,
    pub retryable: bool,
    pub remediation: String,
}

#[derive(Debug)]
pub(crate) enum DocumentStageOutcome {
    Candidate(DocumentCandidate),
    Rejected(DocumentProblem),
}

fn lower_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn decode_candidate(
    response: CoreApiResponse,
    seal: &SourceSeal,
    request: &DocumentSelection,
    source_name: &str,
) -> Result<DocumentCandidate, PickerFailure> {
    if response.status != 200
        || response.content_type != "application/json"
        || response.body.len() > 16_384
    {
        return Err(PickerFailure::Failed);
    }
    let candidate: DocumentCandidate =
        serde_json::from_str(&response.body).map_err(|_| PickerFailure::Failed)?;
    if !crate::supervisor::canonical_uuid_v7(&candidate.candidate_id)
        || candidate.project_id != request.project_id
        || candidate.source_assertion_revision_id != request.source_assertion_revision_id
        || candidate.work_id != request.work_id
        || candidate.work_revision_id != request.work_revision_id
        || candidate.version_id != request.version_id
        || candidate.version_revision_id != request.version_revision_id
        || candidate.object_sha256 != seal.source_sha256
        || candidate.byte_length != seal.byte_length
        || candidate.source_name != source_name
        || !candidate.confirmation_required
        || !lower_hex(&candidate.candidate_sha256, 64)
        || !candidate.rights_subject.is_object()
        || candidate.format.is_empty()
        || candidate.media_type.is_empty()
    {
        return Err(PickerFailure::Failed);
    }
    Ok(candidate)
}

pub(crate) fn decode_stage_response(
    response: CoreApiResponse,
    seal: Option<&SourceSeal>,
    request: &DocumentSelection,
    source_name: &str,
) -> Result<DocumentStageOutcome, PickerFailure> {
    if response.status == 200 {
        return decode_candidate(
            response,
            seal.ok_or(PickerFailure::Failed)?,
            request,
            source_name,
        )
        .map(DocumentStageOutcome::Candidate);
    }
    if response.content_type != "application/problem+json" || response.body.len() > 2048 {
        return Err(PickerFailure::Failed);
    }
    let problem: DocumentProblem =
        serde_json::from_str(&response.body).map_err(|_| PickerFailure::Failed)?;
    if problem.status != response.status
        || problem.trace_id != response.trace_id
        || !problem.code.starts_with("RO-CORE-")
        || problem.code.len() > 100
        || !problem
            .code
            .bytes()
            .all(|byte| byte.is_ascii_uppercase() || byte.is_ascii_digit() || byte == b'-')
        || problem.r#type
            != format!(
                "urn:research-observatory:problem:{}",
                problem
                    .code
                    .trim_start_matches("RO-CORE-")
                    .to_ascii_lowercase()
            )
        || problem.title.is_empty()
        || problem.title.len() > 120
        || problem.detail.is_empty()
        || problem.detail.len() > 500
        || problem.remediation.is_empty()
        || problem.remediation.len() > 240
    {
        return Err(PickerFailure::Failed);
    }
    Ok(DocumentStageOutcome::Rejected(problem))
}

/// The same pinned-handle path serves a native picker selection and a future
/// OS file-drop selection. The caller must retain its original project/lock
/// authority for the entire transfer; no renderer-supplied path is accepted.
pub(crate) fn stage_held_document(
    connection: &NativeImportConnection,
    session_id: &str,
    source: HeldImportSource,
    request: &DocumentSelection,
    authorized: impl Fn() -> bool,
) -> Result<DocumentStageOutcome, PickerFailure> {
    let source_name = source.basename().to_owned();
    let selection = DocumentStageSelection {
        session_id: session_id.to_owned(),
        declared_media_type: request.declared_media_type.clone(),
        source_assertion_revision_id: request.source_assertion_revision_id.clone(),
        work_id: request.work_id.clone(),
        work_revision_id: request.work_revision_id.clone(),
        version_id: request.version_id.clone(),
        version_revision_id: request.version_revision_id.clone(),
    };
    let (response, seal) = connection
        .document_stage(source, &selection, || authorized())
        .map_err(|_| {
            if authorized() && connection.is_current() {
                PickerFailure::Failed
            } else {
                PickerFailure::Cancelled
            }
        })?;
    if !authorized() || !connection.is_current() {
        return Err(PickerFailure::Cancelled);
    }
    decode_stage_response(response, seal.as_ref(), request, &source_name)
}

pub(crate) fn stage_selected_document(
    picker: DirectoryPickerManager,
    supervisor: RuntimeSupervisor,
    lock: ApplicationLockManager,
    ticket: u64,
    owner: isize,
    request: DocumentSelection,
) -> Result<DocumentStageOutcome, PickerFailure> {
    if !request.valid() {
        return Err(PickerFailure::Failed);
    }
    if lock.finish_protected_action(ticket).is_err() || !picker.is_open() {
        return Err(PickerFailure::Cancelled);
    }
    let connection = Arc::new(
        supervisor
            .native_import_connection(&request.root, &request.project_id)
            .map_err(|_| PickerFailure::Unavailable)?,
    );
    let response = connection
        .document_context()
        .map_err(|_| PickerFailure::Unavailable)?;
    if response.status != 200
        || response.content_type != "application/json"
        || response.body.len() > 4096
    {
        return Err(PickerFailure::Failed);
    }
    let context: DocumentContext =
        serde_json::from_str(&response.body).map_err(|_| PickerFailure::Failed)?;
    if context.project_id != request.project_id || !lower_hex(&context.session_id, 32) {
        return Err(PickerFailure::Failed);
    }
    let checking_picker = picker.clone();
    let checking_lock = lock.clone();
    let checking_connection = Arc::clone(&connection);
    picker.document_source(
        owner,
        move || {
            checking_picker.is_open()
                && checking_lock.finish_protected_action(ticket).is_ok()
                && checking_connection.is_current()
        },
        move |source, authorized| {
            stage_held_document(&connection, &context.session_id, source, &request, || {
                authorized()
            })
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn selection() -> DocumentSelection {
        DocumentSelection {
            root: "C:/Synthetic/project".into(),
            project_id: "01900000-0000-7000-8000-000000000001".into(),
            declared_media_type: Some("application/pdf".into()),
            source_assertion_revision_id: "01900000-0000-7000-8000-000000000002".into(),
            work_id: "01900000-0000-7000-8000-000000000003".into(),
            work_revision_id: "01900000-0000-7000-8000-000000000004".into(),
            version_id: "01900000-0000-7000-8000-000000000005".into(),
            version_revision_id: "01900000-0000-7000-8000-000000000006".into(),
        }
    }

    #[test]
    fn candidate_requires_exact_held_digest_length_and_selection() {
        let request = selection();
        assert!(request.valid());
        let mut empty_media = request.clone();
        empty_media.declared_media_type = Some(String::new());
        assert!(!empty_media.valid());
        let seal = SourceSeal {
            source_sha256: "a".repeat(64),
            byte_length: 42,
            chunk_count: 1,
        };
        let value = serde_json::json!({
            "candidateId":"01900000-0000-7000-8000-000000000007",
            "projectId":request.project_id,
            "sourceAssertionRevisionId":request.source_assertion_revision_id,
            "workId":request.work_id,
            "workRevisionId":request.work_revision_id,
            "versionId":request.version_id,
            "versionRevisionId":request.version_revision_id,
            "objectSha256":seal.source_sha256,
            "byteLength":seal.byte_length,
            "format":"pdf",
            "mediaType":"application/pdf",
            "sourceName":"synthetic.pdf",
            "confirmationRequired":true,
            "candidateSha256":"b".repeat(64),
            "rightsSubject":{},
        });
        let response = |body: serde_json::Value| CoreApiResponse {
            status: 200,
            content_type: "application/json".into(),
            trace_id: "c".repeat(32),
            etag: None,
            body: body.to_string(),
        };
        assert!(
            decode_candidate(response(value.clone()), &seal, &request, "synthetic.pdf").is_ok()
        );
        for key in [
            "objectSha256",
            "byteLength",
            "versionRevisionId",
            "sourceName",
        ] {
            let mut altered = value.clone();
            altered[key] = if key == "byteLength" {
                43.into()
            } else {
                "wrong".into()
            };
            assert!(
                decode_candidate(response(altered), &seal, &request, "synthetic.pdf").is_err(),
                "{key}"
            );
        }
    }

    #[test]
    fn stage_failure_retains_only_a_correlated_bounded_core_problem() {
        let request = selection();
        let seal = SourceSeal {
            source_sha256: "a".repeat(64),
            byte_length: 42,
            chunk_count: 1,
        };
        let problem = serde_json::json!({
            "type":"urn:research-observatory:problem:document-password-protected",
            "title":"Document attachment needs attention",
            "status":422,
            "detail":"The selected document is password protected.",
            "code":"RO-CORE-DOCUMENT-PASSWORD-PROTECTED",
            "traceId":"c".repeat(32),
            "retryable":false,
            "remediation":"Choose a safe supported copy and retry."
        });
        let response = |body: serde_json::Value| CoreApiResponse {
            status: 422,
            content_type: "application/problem+json".into(),
            trace_id: "c".repeat(32),
            etag: None,
            body: body.to_string(),
        };
        let accepted = decode_stage_response(
            response(problem.clone()),
            Some(&seal),
            &request,
            "synthetic.pdf",
        )
        .unwrap();
        assert!(
            matches!(accepted, DocumentStageOutcome::Rejected(value) if value.code == "RO-CORE-DOCUMENT-PASSWORD-PROTECTED")
        );
        let mut altered = problem;
        altered["traceId"] = "d".repeat(32).into();
        assert!(
            decode_stage_response(response(altered), Some(&seal), &request, "synthetic.pdf")
                .is_err()
        );
    }
}
