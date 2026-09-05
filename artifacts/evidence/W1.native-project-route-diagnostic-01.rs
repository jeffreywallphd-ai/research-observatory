// Read-only native validator probe. Supervisor has no Core configuration;
// requests cannot start Core or access project data.
extern crate research_observatory_desktop_lib;
use research_observatory_desktop_lib::supervisor::{CoreApiRequest, RuntimeSupervisor};

fn main() {
    let supervisor = RuntimeSupervisor::new(Err("DIAGNOSTIC_NO_CORE_CONFIGURATION"));
    for (method, path, body) in [
        ("GET", "/healthz", None),
        ("GET", "/runtime/version", None),
        ("GET", "/workflow-profiles/catalog", None),
        ("POST", "/projects/open", Some(r#"{"root":"C:/Synthetic-No-IO/project"}"#)),
        ("POST", "/projects/provenance/lineage", Some(r#"{"root":"C:/Synthetic-No-IO/project","revisionId":"01900000-0000-7000-8000-000000000001","direction":"ancestors","cursor":0,"pageSize":50,"maxDepth":8}"#)),
    ] {
        let request = CoreApiRequest {
            method: method.to_owned(), path: path.to_owned(),
            body: body.map(str::to_owned), if_match: None, idempotency_key: None,
        };
        println!("{} {} => {:?}", method, path, supervisor.api_request(&request).map(|_| ()));
    }
}
