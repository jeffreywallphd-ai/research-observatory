//! Private native source configuration. No renderer command accepts secret values.

use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::sync::{Arc, Mutex};

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub(crate) enum Provider {
    Openalex,
    Crossref,
    Unpaywall,
    SemanticScholar,
}

impl Provider {
    pub(crate) fn has_key(self) -> bool {
        matches!(self, Self::Openalex | Self::SemanticScholar)
    }
    pub(crate) fn has_contact(self) -> bool {
        self != Self::SemanticScholar
    }
    pub(crate) fn title(self) -> &'static str {
        match self {
            Self::Openalex => "Configure OpenAlex",
            Self::Crossref => "Configure Crossref",
            Self::Unpaywall => "Configure Unpaywall",
            Self::SemanticScholar => "Configure Semantic Scholar",
        }
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ConfigurationRequest {
    pub root: String,
    pub project_id: String,
    operation_id: String,
    provider_id: Provider,
}

fn hex32(value: &str) -> bool {
    value.len() == 32
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

pub(crate) fn decode_request(payload: &serde_json::Value) -> Option<ConfigurationRequest> {
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Envelope {
        request: ConfigurationRequest,
    }
    let Envelope { request } = serde_json::from_value(payload.clone()).ok()?;
    (crate::directory_picker::local_path_syntax(&request.root)
        && crate::supervisor::canonical_project_id(&request.project_id)
        && hex32(&request.operation_id))
    .then_some(request)
}

/// Public renderer source tests are deliberately a one-DOI observation. Core
/// still enforces the authoritative schema, current policy, rights and consent.
pub(crate) fn validate_public_request(path: &str, body: &str) -> bool {
    if body.len() > 32768 {
        return false;
    }
    let Ok(value) = serde_json::from_str::<serde_json::Value>(body) else {
        return false;
    };
    let exact = |v: &serde_json::Value, keys: &[&str]| {
        v.as_object()
            .is_some_and(|o| o.len() == keys.len() && keys.iter().all(|k| o.contains_key(*k)))
    };
    if !value["root"]
        .as_str()
        .is_some_and(crate::directory_picker::local_path_syntax)
    {
        return false;
    }
    match path {
        "/projects/connectors/recent" => exact(&value, &["root"]),
        "/projects/connectors/inspect" => {
            exact(&value, &["root", "previewId", "recordOffset"])
                && value["previewId"]
                    .as_str()
                    .is_some_and(crate::supervisor::canonical_uuid_v7)
                && value["recordOffset"].as_u64().is_some_and(|v| v < 1000)
        }
        "/projects/connectors/jobs/status" | "/projects/connectors/jobs/cancel" => {
            exact(&value, &["root", "jobId"])
                && value["jobId"]
                    .as_str()
                    .is_some_and(crate::supervisor::canonical_uuid_v7)
        }
        "/projects/connectors/confirmations" => {
            exact(&value, &["root", "previewId", "confirmation"])
                && value["previewId"]
                    .as_str()
                    .is_some_and(crate::supervisor::canonical_uuid_v7)
                && value["confirmation"].as_str().is_some_and(|v| {
                    !v.is_empty() && v.len() <= 128 && v.bytes().all(|b| (33..=126).contains(&b))
                })
        }
        "/projects/connectors/previews" => {
            let request = &value["request"];
            let retention = &value["retention"];
            if !exact(&value, &["root", "request", "retention"])
                || !exact(
                    request,
                    &[
                        "schemaVersion",
                        "projectId",
                        "invocationId",
                        "providerId",
                        "adapterVersion",
                        "sourceApiVersion",
                        "pageSize",
                        "cursor",
                        "policy",
                        "query",
                    ],
                )
                || !exact(retention, &["rights", "retainBody", "permittedFields"])
                || request["schemaVersion"] != "1.0"
                || request["pageSize"] != 1
                || !request["cursor"].is_null()
                || !request["projectId"]
                    .as_str()
                    .is_some_and(crate::supervisor::canonical_project_id)
                || !request["invocationId"]
                    .as_str()
                    .is_some_and(crate::supervisor::canonical_uuid_v7)
                || !matches!(
                    request["providerId"].as_str(),
                    Some("openalex" | "crossref" | "unpaywall" | "semantic-scholar")
                )
                || request["adapterVersion"] != "1.0.0"
                || request["sourceApiVersion"]
                    != match request["providerId"].as_str() {
                        Some("unpaywall") => serde_json::json!("2"),
                        Some("semantic-scholar") => serde_json::json!("1"),
                        _ => serde_json::Value::Null,
                    }
                || request["policy"]
                    != serde_json::json!({"maxInflight":1,"minimumIntervalMs":1000,"maximumAttempts":1,"timeoutMs":10000,"maximumResponseBytes":2097152,"maximumRetryAfterMs":10000,"cacheMode":"bypass","maximumFreshAgeMs":0,"rawRetention":"if-permitted"})
                || retention["retainBody"] != true
                || retention["permittedFields"] != serde_json::json!([])
            {
                return false;
            }
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
            if !exact(&retention["rights"], &actions)
                || !actions.iter().all(|action| {
                    retention["rights"][*action]
                        == if matches!(*action, "store" | "inspect") {
                            serde_json::json!({"value":"permitted","basis":"researcher-confirmed"})
                        } else {
                            serde_json::json!({"value":"unknown","basis":"not-reported"})
                        }
                })
            {
                return false;
            }
            let query = &request["query"];
            let identifier = if request["providerId"] == "unpaywall" {
                if !exact(query, &["kind", "identifier"]) || query["kind"] != "oa-resolution" {
                    return false;
                }
                &query["identifier"]
            } else {
                if !exact(query, &["kind", "identifiers"])
                    || query["kind"] != "lookup"
                    || query["identifiers"].as_array().is_none_or(|v| v.len() != 1)
                {
                    return false;
                }
                &query["identifiers"][0]
            };
            exact(identifier, &["scheme", "value"])
                && identifier["scheme"] == "doi"
                && identifier["value"].as_str().is_some_and(|v| {
                    if v.len() > 2048 || v.chars().any(|c| c.is_whitespace() || c.is_control()) {
                        return false;
                    }
                    v.strip_prefix("10.")
                        .and_then(|v| v.split_once('/'))
                        .is_some_and(|(prefix, suffix)| {
                            (4..=9).contains(&prefix.len())
                                && prefix.bytes().all(|b| b.is_ascii_digit())
                                && !suffix.is_empty()
                        })
                })
        }
        _ => false,
    }
}

pub(crate) fn terms_url(provider: Provider) -> &'static str {
    match provider {
        Provider::Openalex => "https://help.openalex.org/",
        Provider::Crossref => "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
        Provider::Unpaywall => "https://data.unpaywall.org/products/api",
        Provider::SemanticScholar => "https://www.semanticscholar.org/product/api",
    }
}

#[derive(Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "status", rename_all = "kebab-case")]
pub(crate) enum ConfigurationOutcome {
    Saved,
    Cancelled,
    Unavailable,
    Conflict,
    Rejected,
    SaveUnconfirmed,
}

fn after_dispatch(receipt: Option<ConfigurationOutcome>, current: bool) -> ConfigurationOutcome {
    if current {
        receipt.unwrap_or(ConfigurationOutcome::SaveUnconfirmed)
    } else {
        ConfigurationOutcome::SaveUnconfirmed
    }
}

#[derive(Default)]
struct OperationState {
    cancelled: bool,
    submitted: bool,
}
struct Active {
    id: String,
    state: Arc<Mutex<OperationState>>,
}
#[derive(Default)]
struct Admission {
    active: Option<Active>,
    cancelled_before_start: BTreeSet<String>,
    closed: bool,
}
#[derive(Clone, Default)]
pub(crate) struct ConfigurationManager {
    shared: Arc<Mutex<Admission>>,
}
struct Operation {
    manager: ConfigurationManager,
    state: Arc<Mutex<OperationState>>,
}

impl ConfigurationManager {
    fn begin(&self, id: &str) -> Option<Operation> {
        let mut admission = self.shared.lock().ok()?;
        if admission.cancelled_before_start.remove(id)
            || admission.closed
            || admission.active.is_some()
            || admission.cancelled_before_start.len() >= 256
        {
            return None;
        }
        let state = Arc::new(Mutex::new(OperationState::default()));
        admission.active = Some(Active {
            id: id.to_owned(),
            state: state.clone(),
        });
        Some(Operation {
            manager: self.clone(),
            state,
        })
    }
    pub(crate) fn cancel(&self, id: &str) {
        if !hex32(id) {
            return;
        }
        if let Ok(mut admission) = self.shared.lock() {
            if let Some(active) = admission.active.as_ref().filter(|active| active.id == id) {
                if let Ok(mut state) = active.state.lock() {
                    state.cancelled = true;
                }
            } else if admission.cancelled_before_start.len() < 256 {
                admission.cancelled_before_start.insert(id.to_owned());
            } else if !admission.cancelled_before_start.contains(id) {
                admission.closed = true;
                if let Some(active) = &admission.active
                    && let Ok(mut state) = active.state.lock()
                {
                    state.cancelled = true;
                }
            }
        }
    }
}

impl Operation {
    fn current(&self) -> bool {
        self.state.lock().is_ok_and(|state| !state.cancelled)
    }
    fn admit_save(&self) -> bool {
        let Ok(mut state) = self.state.lock() else {
            return false;
        };
        if state.cancelled || state.submitted {
            return false;
        }
        state.submitted = true;
        true
    }
}
impl Drop for Operation {
    fn drop(&mut self) {
        if let Ok(mut admission) = self.manager.shared.lock()
            && admission
                .active
                .as_ref()
                .is_some_and(|item| Arc::ptr_eq(&item.state, &self.state))
        {
            admission.active = None;
        }
    }
}

/// Fixed capacity avoids secret-bearing Vec reallocations during JSON encoding.
/// Windows edit controls and the OS may retain internal copies: this is bounded,
/// best-effort process-buffer clearing, not an OS/heap-erasure guarantee.
pub(crate) struct PrivateBytes(pub(crate) Vec<u8>);
impl PrivateBytes {
    pub(crate) fn text(&self) -> &str {
        std::str::from_utf8(&self.0).expect("validated ASCII")
    }
}
impl Drop for PrivateBytes {
    fn drop(&mut self) {
        for byte in &mut self.0 {
            unsafe {
                std::ptr::write_volatile(byte, 0);
            }
        }
        std::sync::atomic::compiler_fence(std::sync::atomic::Ordering::SeqCst);
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ConnectionStatus {
    provider_id: Provider,
    configuration: String,
    pub key_configured: bool,
    pub contact_configured: bool,
    version: Option<String>,
}

impl ConnectionStatus {
    fn parse(body: &str, provider: Provider) -> Option<Self> {
        let status: Self = serde_json::from_str(body).ok()?;
        (status.provider_id == provider
            && matches!(
                status.configuration.as_str(),
                "ready" | "not-configured" | "unavailable"
            )
            && status.version.as_ref().is_none_or(|v| hex32(v))
            && (!status.key_configured || provider.has_key())
            && (!status.contact_configured || provider.has_contact())
            && (!(status.key_configured || status.contact_configured) || status.version.is_some()))
        .then_some(status)
    }
}

pub(crate) struct Edit {
    pub key: Option<PrivateBytes>,
    pub contact: Option<PrivateBytes>,
    pub preserve_key: bool,
    pub preserve_contact: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct Address<'a> {
    root: &'a str,
    project_id: &'a str,
    provider_id: Provider,
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct Write<'a> {
    #[serde(flatten)]
    address: Address<'a>,
    key: Option<&'a str>,
    contact: Option<&'a str>,
    expected_version: Option<&'a str>,
    preserve_key: bool,
    preserve_contact: bool,
}

#[cfg(windows)]
pub(crate) fn configure(
    manager: ConfigurationManager,
    picker: crate::directory_picker::DirectoryPickerManager,
    supervisor: crate::supervisor::RuntimeSupervisor,
    security: crate::application_lock::ApplicationLockManager,
    ticket: u64,
    owner: isize,
    request: ConfigurationRequest,
) -> ConfigurationOutcome {
    let Some(operation) = manager.begin(&request.operation_id) else {
        return ConfigurationOutcome::Unavailable;
    };
    let Ok(connection) = supervisor.native_import_connection(&request.root, &request.project_id)
    else {
        return ConfigurationOutcome::Unavailable;
    };
    picker
        .with_native_dialog(owner, |dialog_current| {
            let current = || {
                dialog_current()
                    && operation.current()
                    && security.finish_protected_action(ticket).is_ok()
                    && connection.is_current()
            };
            if !current() {
                return ConfigurationOutcome::Cancelled;
            }
            let address = || Address {
                root: &request.root,
                project_id: &request.project_id,
                provider_id: request.provider_id,
            };
            let Ok(body) = serde_json::to_vec(&address()) else {
                return ConfigurationOutcome::Unavailable;
            };
            let status = connection
                .configuration_request(false, &body)
                .ok()
                .filter(|r| r.status == 200)
                .and_then(|r| ConnectionStatus::parse(&r.body, request.provider_id));
            let Some(status) = status.filter(|s| s.configuration != "unavailable") else {
                return ConfigurationOutcome::Unavailable;
            };
            if !current() {
                return ConfigurationOutcome::Cancelled;
            }
            let edit = match crate::connector_configuration_dialog::show(
                owner,
                request.provider_id,
                &status,
                &current,
            ) {
                Ok(Some(edit)) => edit,
                Ok(None) => return ConfigurationOutcome::Cancelled,
                Err(()) => return ConfigurationOutcome::Unavailable,
            };
            // Maximum path 4096 + values 2*1024 plus escaping and envelope. Reject
            // oversize locally before dispatch; no secret is ever formatted/logged.
            let mut body = PrivateBytes(Vec::with_capacity(32768));
            let write = Write {
                address: address(),
                key: edit.key.as_ref().map(PrivateBytes::text),
                contact: edit.contact.as_ref().map(PrivateBytes::text),
                expected_version: status.version.as_deref(),
                preserve_key: edit.preserve_key,
                preserve_contact: edit.preserve_contact,
            };
            if serde_json::to_writer(&mut body.0, &write).is_err() || body.0.len() > 8192 {
                return ConfigurationOutcome::Rejected;
            }
            if !current() {
                return ConfigurationOutcome::Cancelled;
            }
            // The mutex fences only dispatch admission, never cross-process I/O.
            if !security
                .commit_protected_action(ticket, || Ok(operation.admit_save()))
                .unwrap_or(false)
            {
                return ConfigurationOutcome::Cancelled;
            }
            let response = connection.configuration_request(true, &body.0).ok();
            drop(body);
            drop(edit);
            let receipt = response.and_then(|r| {
                if r.status == 200 {
                    ConnectionStatus::parse(&r.body, request.provider_id)
                        .filter(|s| {
                            s.version.is_some()
                                && s.version != status.version
                                && s.configuration != "unavailable"
                        })
                        .map(|_| ConfigurationOutcome::Saved)
                } else {
                    let problem: serde_json::Value = serde_json::from_str(&r.body).ok()?;
                    match (r.status, problem["code"].as_str()) {
                        (409, Some("RO-CORE-CONNECTOR-CONFIGURATION-CONFLICT")) => {
                            Some(ConfigurationOutcome::Conflict)
                        }
                        (422, Some("RO-CORE-CONNECTOR-INVALID-REQUEST")) => {
                            Some(ConfigurationOutcome::Rejected)
                        }
                        _ => None,
                    }
                }
            });
            after_dispatch(receipt, current())
        })
        .unwrap_or(ConfigurationOutcome::Unavailable)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn public_source_test_admission_preserves_the_fixed_contract() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../tests/fixtures/scholarly-metadata/source-test-request.v1.json"
        ))
        .unwrap();
        assert!(validate_public_request(
            "/projects/connectors/previews",
            &fixture.to_string()
        ));
        for section in ["request", "retention"] {
            let mut changed = fixture.clone();
            changed[section]["key"] = serde_json::json!("synthetic");
            assert!(!validate_public_request(
                "/projects/connectors/previews",
                &changed.to_string()
            ));
        }
        let mut changed = fixture.clone();
        changed["request"]["policy"]["maximumAttempts"] = serde_json::json!(3);
        assert!(!validate_public_request(
            "/projects/connectors/previews",
            &changed.to_string()
        ));
        for route in [
            "/native/connectors/configuration/status",
            "/native/connectors/configuration/replace",
        ] {
            assert!(!validate_public_request(route, &fixture.to_string()));
        }
    }

    #[test]
    fn source_inspection_is_read_only_bounded_and_has_no_caller_authority() {
        let command = serde_json::json!({"root":"C:/Research/synthetic","previewId":"01900000-0000-7000-8000-000000000001","recordOffset":0});
        assert!(validate_public_request(
            "/projects/connectors/inspect",
            &command.to_string()
        ));
        for bad in [
            serde_json::json!(-1),
            serde_json::json!(1000),
            serde_json::json!(true),
        ] {
            let mut changed = command.clone();
            changed["recordOffset"] = bad;
            assert!(!validate_public_request(
                "/projects/connectors/inspect",
                &changed.to_string()
            ));
        }
        let mut changed = command;
        changed["confirmation"] = serde_json::json!("synthetic");
        assert!(!validate_public_request(
            "/projects/connectors/inspect",
            &changed.to_string()
        ));
        assert!(validate_public_request(
            "/projects/connectors/recent",
            r#"{"root":"C:/Research/synthetic"}"#
        ));
    }

    #[test]
    fn status_projection_rejects_value_leaks_and_wrong_provider() {
        let status = serde_json::json!({"providerId":"unpaywall","configuration":"ready","keyConfigured":false,"contactConfigured":true,"version":"a".repeat(32)});
        assert!(ConnectionStatus::parse(&status.to_string(), Provider::Unpaywall).is_some());
        assert!(ConnectionStatus::parse(&status.to_string(), Provider::Crossref).is_none());
        let mut changed = status.clone();
        changed["contact"] = serde_json::json!("synthetic@example.invalid");
        assert!(ConnectionStatus::parse(&changed.to_string(), Provider::Unpaywall).is_none());
        let mut changed = status.clone();
        changed["version"] = serde_json::Value::Null;
        assert!(ConnectionStatus::parse(&changed.to_string(), Provider::Unpaywall).is_none());
    }

    #[test]
    fn request_is_closed_and_never_accepts_credentials() {
        let request = serde_json::json!({"request": {
            "operationId": "a".repeat(32), "root": "C:\\synthetic",
            "projectId": "01900000-0000-7000-8000-000000000001",
            "providerId": "unpaywall"
        }});
        assert!(decode_request(&request).is_some());
        for field in ["key", "contact", "url", "expectedVersion"] {
            let mut bad = request.clone();
            bad["request"][field] = serde_json::json!("synthetic");
            assert!(decode_request(&bad).is_none());
        }
        let mut bad = request.clone();
        bad["request"]["providerId"] = serde_json::json!("untrusted");
        assert!(decode_request(&bad).is_none());
    }

    #[test]
    fn cancellation_and_save_admission_have_one_order() {
        let manager = ConfigurationManager::default();
        let first = manager.begin(&"a".repeat(32)).unwrap();
        assert!(manager.begin(&"b".repeat(32)).is_none());
        manager.cancel(&"c".repeat(32));
        assert!(first.current());
        manager.cancel(&"a".repeat(32));
        assert!(!first.admit_save());
        drop(first);
        let second = manager.begin(&"b".repeat(32)).unwrap();
        assert!(second.admit_save());
        assert!(!second.admit_save());
        manager.cancel(&"b".repeat(32));
        assert!(!second.current());
        assert_eq!(
            after_dispatch(None, false),
            ConfigurationOutcome::SaveUnconfirmed
        );
    }

    #[test]
    fn cancellation_before_worker_start_is_not_lost_or_evicted() {
        let manager = ConfigurationManager::default();
        let id = "d".repeat(32);
        manager.cancel(&id);
        assert!(manager.begin(&id).is_none());
        for index in 0..257 {
            manager.cancel(&format!("{index:032x}"));
        }
        assert!(manager.begin(&"e".repeat(32)).is_none());
    }

    #[test]
    fn dropped_or_stale_acknowledgment_cannot_claim_cancellation() {
        assert_eq!(
            after_dispatch(None, true),
            ConfigurationOutcome::SaveUnconfirmed
        );
        assert_eq!(
            after_dispatch(Some(ConfigurationOutcome::Saved), false),
            ConfigurationOutcome::SaveUnconfirmed
        );
        assert_eq!(
            after_dispatch(Some(ConfigurationOutcome::Saved), true),
            ConfigurationOutcome::Saved
        );
        assert_eq!(
            after_dispatch(Some(ConfigurationOutcome::Conflict), true),
            ConfigurationOutcome::Conflict
        );
    }
}
