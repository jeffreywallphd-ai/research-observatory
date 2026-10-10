//! Opt-in production component -> actual Wry/Native/Core/encrypted outcome.
//! Authored parser output, test page host; no packaged installation/model claim.
use super::*;
use crate::supervisor::{CoreApiRequest, RuntimeState, SupervisorConfig};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Manager, WebviewUrl};

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Report {
    schema_version: String,
    passed: bool,
    phase: String,
}
#[derive(Default)]
struct Completion(Mutex<Option<Report>>);
#[tauri::command]
fn correction_witness_complete(
    report: Report,
    state: State<'_, Completion>,
) -> Result<(), &'static str> {
    if report.schema_version != "1.0"
        || ![
            "mount",
            "proposal",
            "acceptance",
            "reader",
            "return",
            "complete",
        ]
        .contains(&report.phase.as_str())
    {
        return Err("witness-report-invalid");
    }
    let mut value = state.0.lock().map_err(|_| "witness-report-invalid")?;
    if value.is_some() {
        return Err("witness-report-duplicate");
    }
    *value = Some(report);
    Ok(())
}
fn exercise(window: tauri::WebviewWindow, receipt: Value) {
    let supervisor = window.state::<RuntimeSupervisor>();
    let deadline = Instant::now() + Duration::from_secs(60);
    while supervisor.status().state != RuntimeState::Ready {
        assert!(Instant::now() < deadline, "actual Core ready");
        std::thread::sleep(Duration::from_millis(25));
    }
    let opened = supervisor
        .api_request(&CoreApiRequest {
            method: "POST".into(),
            path: "/projects/open".into(),
            body: Some(json!({"root":receipt["root"]}).to_string()),
            if_match: None,
            idempotency_key: None,
        })
        .unwrap();
    assert_eq!(opened.status, 200);
    let project: Value = serde_json::from_str(&opened.body).unwrap();
    let selection = json!({"projectId":receipt["projectId"],"revisionId":receipt["originalRevisionId"],"jobId":receipt["jobId"],"draftRevisionId":null});
    window.eval(&format!("(async()=>{{while(!window.__QUALITY_NATIVE_WITNESS__)await new Promise(r=>setTimeout(r,25));await window.__QUALITY_NATIVE_WITNESS__.run({project},{selection});}})()" )).unwrap();
    let deadline = Instant::now() + Duration::from_secs(150);
    loop {
        let completion = window.state::<Completion>();
        let report = completion.0.lock().unwrap();
        if let Some(report) = report.as_ref() {
            assert!(
                report.passed,
                "actual production UI witness stopped at {}",
                report.phase
            );
            assert_eq!(report.phase, "complete");
            break;
        }
        assert!(
            Instant::now() < deadline,
            "actual rendered control journey settles"
        );
        drop(report);
        std::thread::sleep(Duration::from_millis(25));
    }
    let call = |command: Command| {
        tauri::async_runtime::block_on(document_correction_request(
            window.clone(),
            window.state(),
            window.state(),
            CorrectionRequest {
                schema_version: "1.0".into(),
                project_id: receipt["projectId"].as_str().unwrap().into(),
                command,
            },
        ))
        .unwrap()
        .unwrap()
    };
    let queue = call(Command::Queue { after_job_id: None });
    let accepted_id = queue["items"]
        .as_array()
        .unwrap()
        .iter()
        .find(|i| i["jobId"] == receipt["jobId"])
        .unwrap()["revisionId"]
        .as_str()
        .unwrap()
        .to_string();
    assert_ne!(accepted_id, receipt["originalRevisionId"].as_str().unwrap());
    let accepted = call(Command::Page {
        revision_id: accepted_id.clone(),
        draft_revision_id: None,
        offset: 0,
    });
    assert_eq!(
        accepted["nodes"][0]["label"],
        "SYNTHETIC Native human label"
    );
    assert_eq!(accepted["machineRevisionId"], receipt["originalRevisionId"]);
    assert_eq!(accepted["source"]["objectSha256"], receipt["sourceSha256"]);
    assert_eq!(
        accepted["acceptedDecision"]["record"]["rationale"],
        "SYNTHETIC Native human rationale"
    );
    assert_eq!(
        accepted["acceptedDecision"]["record"]["authoredActorType"],
        "human"
    );
    let original = call(Command::Page {
        revision_id: receipt["originalRevisionId"].as_str().unwrap().into(),
        draft_revision_id: None,
        offset: 0,
    });
    assert_eq!(original["nodes"][0]["preview"], receipt["raw"]);
    assert!(original["nodes"][0]["label"].is_null());
    assert_ne!(
        original["nodes"][0]["nodeId"],
        accepted["nodes"][0]["nodeId"]
    );
    for path in ["/projects/close", "/projects/open"] {
        let result = supervisor
            .api_request(&CoreApiRequest {
                method: "POST".into(),
                path: path.into(),
                body: Some(json!({"root":receipt["root"]}).to_string()),
                if_match: None,
                idempotency_key: None,
            })
            .unwrap();
        assert_eq!(result.status, 200);
    }
    let reopened = call(Command::Page {
        revision_id: accepted_id,
        draft_revision_id: None,
        offset: 0,
    });
    assert_eq!(reopened, accepted);
    window
        .state::<ApplicationLockManager>()
        .begin_terminal_exit();
    assert!(tauri::async_runtime::block_on(document_correction_request(
        window.clone(),
        window.state(),
        window.state(),
        CorrectionRequest {
            schema_version: "1.0".into(),
            project_id: receipt["projectId"].as_str().unwrap().into(),
            command: Command::Queue { after_job_id: None }
        }
    ))
    .is_err());
    println!(
        "{}",
        json!({"kind":"actual-correction-component-native-core","status":"PASS","originalPreserved":true,"freshCanonicalIds":true,"explicitAcceptance":true,"durableReopen":true,"readerReturn":true,"terminalExitDenied":true,"modelExecuted":false,"packagedInstallationQualified":false})
    );
}
#[test]
#[ignore = "Requires opt-in owned Windows Wry fixture"]
fn actual_renderer_correction_save_accept_reader_and_reopen() {
    assert_eq!(
        std::env::var("RO_CORRECTION_NATIVE_TEST").as_deref(),
        Ok("1")
    );
    let repo = dunce::canonicalize(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..")).unwrap();
    let fixture = dunce::canonicalize(PathBuf::from(
        std::env::var_os("RO_CORRECTION_NATIVE_FIXTURE").unwrap(),
    ))
    .unwrap();
    assert_eq!(fixture.parent(), Some(repo.join("artifacts/tmp").as_path()));
    assert!(fixture
        .file_name()
        .unwrap()
        .to_str()
        .unwrap()
        .starts_with("directory-dialog-correction-native-"));
    let python = PathBuf::from(std::env::var_os("RO_CORRECTION_NATIVE_PYTHON").unwrap());
    let raw = std::fs::read(fixture.join("correction-receipt.json")).unwrap();
    assert!(raw.len() < 8192);
    let receipt: Value = serde_json::from_slice(&raw).unwrap();
    let environment = vec![
        (
            "PYTHONPATH".into(),
            std::env::join_paths([
                repo.join("tests/service/fixtures"),
                repo.join("services/core-api/src"),
                repo.clone(),
                repo.join(".venv/Lib/site-packages"),
            ])
            .unwrap(),
        ),
        ("PYTHONDONTWRITEBYTECODE".into(), "1".into()),
        ("TEMP".into(), fixture.join("temporary").into_os_string()),
        ("TMP".into(), fixture.join("temporary").into_os_string()),
    ];
    let config = SupervisorConfig::for_integration_harness(
        python,
        fixture.clone(),
        vec![
            "-B".into(),
            "-m".into(),
            "native_integration_sidecar".into(),
            "--profile-vault-root".into(),
            fixture.join("vault").into_os_string(),
        ],
        environment,
    )
    .unwrap();
    let mut context = tauri::generate_context!();
    let mut window_config = context
        .config()
        .app
        .windows
        .iter()
        .find(|w| w.label == "main")
        .unwrap()
        .clone();
    window_config.url = WebviewUrl::App("correction-witness/index.html".into());
    for window in &mut context.config_mut().app.windows {
        window.create = false;
    }
    let result = Arc::new(Mutex::new(None));
    let destination = Arc::clone(&result);
    let app = crate::application_builder()
        .any_thread()
        .invoke_handler(tauri::generate_handler![
            document_correction_request,
            correction_witness_complete,
            crate::document_viewer::document_viewer_source,
            crate::document_viewer::document_viewer_text,
            crate::document_viewer::document_viewer_outline,
            crate::document_reader::document_reader_revisions
        ])
        .setup(move |app| {
            crate::setup_runtime(
                app,
                Ok(config),
                &fixture.join("application-data"),
                crate::DirectoryPickerManager::for_fixture(fixture.join("projects")),
            )?;
            app.manage(Completion::default());
            let window = tauri::WebviewWindowBuilder::from_config(app, &window_config)?
                .data_directory(fixture.join("webview"))
                .visible(false)
                .drag_and_drop(false)
                .disable_drag_drop_handler()
                .title("Research Observatory — SYNTHETIC correction component Native test")
                .build()?;
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    exercise(window, receipt)
                }));
                handle.state::<RuntimeSupervisor>().stop();
                *destination.lock().unwrap() = Some(outcome);
                handle.exit(0);
            });
            Ok(())
        })
        .build(context)
        .unwrap();
    assert_eq!(app.run_return(|_, _| {}), 0);
    match result.lock().unwrap().take().expect("witness ran") {
        Ok(()) => (),
        Err(panic) => std::panic::resume_unwind(panic),
    }
}
