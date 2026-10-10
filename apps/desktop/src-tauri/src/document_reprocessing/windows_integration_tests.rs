//! Production controls -> Wry/Native/current Core principal -> encrypted reparse.
//! Declared authored parser fixture; no model or packaged installation claim.
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
    diagnostic: Option<String>,
    observed_status: Option<String>,
}
#[derive(Default)]
struct Completion(Mutex<Option<Report>>);
#[tauri::command]
fn reprocessing_witness_complete(
    report: Report,
    state: State<'_, Completion>,
) -> Result<(), &'static str> {
    if report
        .observed_status
        .as_deref()
        .is_some_and(|value| value.chars().count() > 1000)
        || report.schema_version != "1.0"
        || ![
            "mount",
            "correction",
            "batch",
            "reconciliation",
            "acceptance",
            "reader",
            "return",
            "complete",
        ]
        .contains(&report.phase.as_str())
        || report.diagnostic.as_deref().is_some_and(|value| {
            ![
                "unknown-command",
                "unconfirmed-authority",
                "parse-pending",
                "control-timeout",
            ]
            .contains(&value)
        })
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
    window.eval(&format!("(async()=>{{while(!window.__REPROCESSING_NATIVE_DRIVER__)await new Promise(r=>setTimeout(r,25));await window.__REPROCESSING_NATIVE_DRIVER__({project},{selection});}})()")).unwrap();
    let deadline = Instant::now() + Duration::from_secs(180);
    loop {
        let state = window.state::<Completion>();
        let report = state.0.lock().unwrap();
        if let Some(report) = report.as_ref() {
            assert!(
                report.passed,
                "actual production reprocessing witness stopped at {} ({:?}); {:?}",
                report.phase, report.diagnostic, report.observed_status
            );
            assert_eq!(report.phase, "complete");
            break;
        }
        assert!(Instant::now() < deadline, "rendered journey settles");
        drop(report);
        std::thread::sleep(Duration::from_millis(25));
    }
    let reprocess = |command: Command| {
        tauri::async_runtime::block_on(document_reprocessing_request(
            window.clone(),
            window.state(),
            window.state(),
            ReprocessingRequest {
                schema_version: "1.0".into(),
                project_id: receipt["projectId"].as_str().unwrap().into(),
                command,
            },
        ))
        .unwrap()
        .unwrap()
    };
    let correction = |command: Value| {
        let request = serde_json::from_value(
            json!({"schemaVersion":"1.0","projectId":receipt["projectId"],"command":command}),
        )
        .unwrap();
        tauri::async_runtime::block_on(crate::document_corrections::document_correction_request(
            window.clone(),
            window.state(),
            window.state(),
            request,
        ))
        .unwrap()
        .unwrap()
    };
    let queue = reprocess(Command::Queue {
        after_batch_id: None,
    });
    let batch = &queue["items"][0];
    let item = &batch["items"][0];
    assert_eq!(item["state"], "accepted");
    let retained = reprocess(Command::ReadImpact {
        batch_revision_id: batch["batchRevisionId"].as_str().unwrap().into(),
        item_id: item["itemId"].as_str().unwrap().into(),
    });
    assert_eq!(retained["revisionId"], item["acceptedRevisionId"]);
    assert_eq!(retained["impactState"], "completed");
    assert_ne!(retained["revisionId"], retained["machineRevisionId"]);
    let final_id = retained["revisionId"].as_str().unwrap().to_string();
    let final_page = correction(
        json!({"action":"page","revisionId":final_id,"draftRevisionId":null,"offset":0}),
    );
    assert_eq!(
        final_page["nodes"][0]["label"],
        "SYNTHETIC Native retained reparse label"
    );
    assert_eq!(
        final_page["source"]["objectSha256"],
        receipt["sourceSha256"]
    );
    let original = correction(
        json!({"action":"page","revisionId":receipt["originalRevisionId"],"draftRevisionId":null,"offset":0}),
    );
    assert_eq!(original["nodes"][0]["preview"], receipt["raw"]);
    assert!(original["nodes"][0]["label"].is_null());
    assert_ne!(
        original["nodes"][0]["nodeId"],
        final_page["nodes"][0]["nodeId"]
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
    assert_eq!(
        correction(
            json!({"action":"page","revisionId":final_id,"draftRevisionId":null,"offset":0})
        ),
        final_page
    );
    assert_eq!(
        reprocess(Command::ReadImpact {
            batch_revision_id: batch["batchRevisionId"].as_str().unwrap().into(),
            item_id: item["itemId"].as_str().unwrap().into()
        }),
        retained
    );
    window
        .state::<ApplicationLockManager>()
        .begin_terminal_exit();
    assert!(
        tauri::async_runtime::block_on(document_reprocessing_request(
            window.clone(),
            window.state(),
            window.state(),
            ReprocessingRequest {
                schema_version: "1.0".into(),
                project_id: receipt["projectId"].as_str().unwrap().into(),
                command: Command::Queue {
                    after_batch_id: None
                }
            }
        ))
        .is_err()
    );
    println!(
        "{}",
        json!({"kind":"actual-reprocessing-component-native-core","status":"PASS","originalPreserved":true,"freshCanonicalIds":true,"explicitPerDocumentAcceptance":true,"humanCorrectionReconciled":true,"durableReopen":true,"readerReturn":true,"terminalExitDenied":true,"parserOutputAuthoredFixture":true,"modelExecuted":false,"packagedInstallationQualified":false})
    );
}
#[test]
#[ignore = "Requires opt-in owned Windows Wry fixture"]
fn actual_renderer_corrected_reparse_accept_reader_and_reopen() {
    assert_eq!(
        std::env::var("RO_REPROCESSING_NATIVE_TEST").as_deref(),
        Ok("1")
    );
    let repo = dunce::canonicalize(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..")).unwrap();
    let fixture = dunce::canonicalize(PathBuf::from(
        std::env::var_os("RO_REPROCESSING_NATIVE_FIXTURE").unwrap(),
    ))
    .unwrap();
    assert_eq!(fixture.parent(), Some(repo.join("artifacts/tmp").as_path()));
    assert!(
        fixture
            .file_name()
            .unwrap()
            .to_str()
            .unwrap()
            .starts_with("directory-dialog-correction-native-")
    );
    let python = PathBuf::from(std::env::var_os("RO_REPROCESSING_NATIVE_PYTHON").unwrap());
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
            "tests.documents.reprocessing_native_windows_sidecar".into(),
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
    window_config.url = WebviewUrl::App("reprocessing-witness/index.html".into());
    for window in &mut context.config_mut().app.windows {
        window.create = false;
    }
    let result = Arc::new(Mutex::new(None));
    let destination = Arc::clone(&result);
    let app = crate::application_builder()
        .any_thread()
        .invoke_handler(tauri::generate_handler![
            document_reprocessing_request,
            crate::document_corrections::document_correction_request,
            reprocessing_witness_complete,
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
                .title("Research Observatory — SYNTHETIC reprocessing Native test")
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
