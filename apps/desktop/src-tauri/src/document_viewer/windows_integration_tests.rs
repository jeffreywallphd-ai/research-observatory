//! Opt-in actual Wry/Native/Core reads, rights and maximum-source cancellation.
//! Direct production handler calls do not prove renderer abort dispatch; the
//! actual shipping-renderer observation and source-held Core regression are
//! separate evidence. Writer contention is not an authentication-phase marker.

use super::*;
use crate::supervisor::{CoreApiRequest, RuntimeState, SupervisorConfig};
use sha2::{Digest, Sha256};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::mpsc;
use std::time::{Duration, Instant};
use tauri::{ipc::IpcResponse, Manager};

struct Writer {
    process: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
}

impl Writer {
    fn start(python: &Path, repo: &Path, fixture: &Path) -> Self {
        let mut process = Command::new(python)
            .arg("-B")
            .arg(repo.join("tests/documents/viewer_native_windows_fixture.py"))
            .arg("writer")
            .arg("--fixture")
            .arg(fixture)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .expect("actual SQLCipher writer starts");
        let input = process.stdin.take().unwrap();
        let output = BufReader::new(process.stdout.take().unwrap());
        let mut writer = Self {
            process,
            input,
            output,
        };
        assert_eq!(writer.read()["kind"], "writer-ready");
        writer
    }

    fn read(&mut self) -> Value {
        let mut line = String::new();
        assert!(self.output.read_line(&mut line).unwrap() <= 1024);
        serde_json::from_str(&line).expect("bounded writer protocol")
    }

    fn request(&mut self, action: &str) -> Value {
        writeln!(self.input, "{}", json!({"action": action})).unwrap();
        self.input.flush().unwrap();
        self.read()
    }
}

impl Drop for Writer {
    fn drop(&mut self) {
        let _ = writeln!(self.input, "{}", json!({"action":"close"}));
        let _ = self.input.flush();
        let deadline = Instant::now() + Duration::from_secs(2);
        loop {
            if self.process.try_wait().ok().flatten().is_some() {
                break;
            }
            if Instant::now() >= deadline {
                let _ = self.process.kill();
                let _ = self.process.wait();
                break;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
    }
}

fn range(
    window: &tauri::WebviewWindow,
    request: ViewerRangeRequest,
) -> Result<tauri::ipc::Response, ViewerRangeFailure> {
    tauri::async_runtime::block_on(document_viewer_range(
        window.clone(),
        window.state(),
        window.state(),
        window.state(),
        request,
    ))
}

fn exercise(
    window: tauri::WebviewWindow,
    repo: PathBuf,
    fixture: PathBuf,
    python: PathBuf,
    receipt: Value,
) {
    let supervisor = window.state::<RuntimeSupervisor>();
    let deadline = Instant::now() + Duration::from_secs(60);
    while supervisor.status().state != RuntimeState::Ready {
        assert!(
            Instant::now() < deadline,
            "supervised actual Core becomes ready"
        );
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
        .expect("real selected-project authority");
    assert_eq!(opened.status, 200);
    let request: ViewerRangeRequest = serde_json::from_value(json!({
        "schemaVersion":"1.0", "projectId":receipt["projectId"], "selector":receipt["selector"],
        "requestId":"00000000-0000-7000-8000-000000000021", "start":MAX_SOURCE-MAX_RANGE, "end":MAX_SOURCE,
    })).unwrap();
    assert_eq!(receipt["sourceBytes"], MAX_SOURCE);
    let source = tauri::async_runtime::block_on(document_viewer_source(
        window.clone(),
        window.state(),
        window.state(),
        ViewerSourceRequest {
            schema_version: request.schema_version.clone(),
            project_id: request.project_id.clone(),
            selector: request.selector.clone(),
        },
    ))
    .ok()
    .flatten()
    .expect("actual max encrypted source metadata");
    assert_eq!(source["source"]["objectSha256"], receipt["sourceSha256"]);
    let mut writer = Writer::start(&python, &repo, &fixture);
    assert_eq!(writer.request("observe")["outcome"], "available");
    let key = (request.project_id.clone(), request.request_id.clone());
    let (send, receive) = mpsc::channel();
    let running_window = window.clone();
    let running_request = request.clone();
    let running = std::thread::spawn(move || {
        send.send(range(&running_window, running_request)).unwrap();
    });
    let manager = window.state::<DocumentViewerManager>();
    let pending_deadline = Instant::now() + Duration::from_secs(3);
    loop {
        let issued = manager
            .pending
            .lock()
            .unwrap()
            .active
            .get(&key)
            .is_some_and(|pending| pending.session.lock().unwrap().is_some());
        assert!(
            matches!(receive.try_recv(), Err(mpsc::TryRecvError::Empty)),
            "original range is unsettled before cancellation"
        );
        if issued && writer.request("observe")["outcome"] == "busy" {
            break;
        }
        assert!(
            Instant::now() < pending_deadline,
            "issued original owns contended real SQLCipher work"
        );
        std::thread::sleep(Duration::from_millis(2));
    }
    let began = Instant::now();
    assert!(tauri::async_runtime::block_on(document_viewer_cancel(
        window.clone(),
        window.state(),
        ViewerCancelRequest {
            schema_version: "1.0".into(),
            project_id: key.0.clone(),
            request_id: key.1.clone(),
        },
    ))
    .is_ok());
    let result = receive
        .recv_timeout(Duration::from_secs(1))
        .expect("exact original range settles");
    let failure = match result {
        Err(failure) => failure,
        Ok(_) => panic!("cancelled request exposed successful bytes"),
    };
    assert_eq!(failure.schema_version, "1.0");
    assert_eq!((&failure.project_id, &failure.request_id), (&key.0, &key.1));
    assert!(
        failure.drained,
        "original range carries physical Core drain acknowledgement"
    );
    let committed = writer.request("commit");
    assert_eq!(committed["outcome"], "committed");
    assert_eq!(committed["preserved"], true);
    assert!(
        began.elapsed() <= Duration::from_secs(1),
        "terminal drain AND verified writer commit <=1s"
    );
    let cancel_and_writer_ms = began.elapsed().as_secs_f64() * 1000.0;
    assert!(
        manager.no_active_owner(&key),
        "terminal acknowledgement clears native admission"
    );
    running.join().unwrap();
    let mut retry = request.clone();
    retry.request_id = "00000000-0000-7000-8000-000000000022".into();
    let bytes = match range(&window, retry) {
        Ok(response) => response.body().unwrap(),
        Err(_) => panic!("fresh exact-source retry denied"),
    };
    let bytes = match bytes {
        tauri::ipc::InvokeResponseBody::Raw(bytes) => bytes,
        _ => panic!("range was not raw byte IPC"),
    };
    assert_eq!(bytes.len(), MAX_RANGE as usize);
    assert_eq!(
        format!("{:x}", Sha256::digest(bytes)),
        receipt["tailSha256"].as_str().unwrap()
    );
    // Explicit-none has no manual application lock. Exercise its actual terminal
    // close fence rather than forcing a state or claiming a lock witness.
    window
        .state::<ApplicationLockManager>()
        .begin_terminal_exit();
    let mut closed = request;
    closed.request_id = "00000000-0000-7000-8000-000000000023".into();
    assert!(
        range(&window, closed).is_err(),
        "terminal close denies fresh protected delivery"
    );
    println!(
        "{}",
        json!({"kind":"native-viewer-max-cancel", "status":"PASS",
        "sourceBytes":MAX_SOURCE,"rangeBytes":MAX_RANGE,"correlatedDrainedDenial":true,
        "writerPreserved":true,"cancelAndWriterMs":cancel_and_writer_ms,
        "freshTailExact":true,"terminalCloseDenied":true,"rendererAbortDispatchProven":false,
        "writerContentionProvesAuthenticationPhase":false,"modelExecuted":false})
    );
}

#[test]
#[ignore = "opt-in real Windows principal, owned Wry event loop and seeded encrypted maximum fixture"]
fn real_native_maximum_cancel_releases_writer_and_preserves_exact_tail() {
    run_native_test("RO_RUN_VIEWER_NATIVE_MAX", exercise);
}

#[test]
#[ignore = "opt-in real Windows principal, owned Wry event loop and synthetic accepted encrypted fixture"]
fn real_native_accepted_text_outline_rights_resource_and_close_fences() {
    run_native_test("RO_RUN_VIEWER_NATIVE_ACCEPTED", exercise_accepted);
}

fn exercise_accepted(
    window: tauri::WebviewWindow,
    _repo: PathBuf,
    _fixture: PathBuf,
    _python: PathBuf,
    receipt: Value,
) {
    let supervisor = window.state::<RuntimeSupervisor>();
    let deadline = Instant::now() + Duration::from_secs(60);
    while supervisor.status().state != RuntimeState::Ready {
        assert!(
            Instant::now() < deadline,
            "actual supervised Core becomes ready"
        );
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
        .expect("real selected-project authority");
    assert_eq!(opened.status, 200);
    let text = |fixture: &Value| -> ViewerTextRequest {
        serde_json::from_value(
            json!({"schemaVersion":"1.0", "projectId":receipt["projectId"],
            "selector":fixture["selector"], "nodeId":fixture["nodeId"], "offset":0}),
        )
        .unwrap()
    };
    let read_text = |request| {
        tauri::async_runtime::block_on(document_viewer_text(
            window.clone(),
            window.state(),
            window.state(),
            request,
        ))
    };
    let read_outline = |request: &ViewerTextRequest| {
        tauri::async_runtime::block_on(document_viewer_outline(
            window.clone(),
            window.state(),
            window.state(),
            ViewerOutlineRequest {
                schema_version: request.schema_version.clone(),
                project_id: request.project_id.clone(),
                selector: request.selector.clone(),
                after_node_id: None,
            },
        ))
    };
    let normal = text(&receipt["acceptedFixtures"]["normal"]);
    let value = read_text(normal.clone())
        .unwrap()
        .expect("real accepted text crosses Native/Core");
    assert!(text_matches(&value, &normal));
    assert_eq!(value["text"], "SYNTHETIC accepted Native text.");
    assert_eq!(
        value["metadata"]["source"]["objectSha256"],
        receipt["sourceSha256"]
    );
    assert!(!value
        .to_string()
        .contains(receipt["root"].as_str().unwrap()));
    let outline = read_outline(&normal)
        .unwrap()
        .expect("real accepted outline crosses Native/Core");
    assert_eq!(outline["scholarlyVerification"], "unverified");
    assert_eq!(
        outline["revisionId"].as_str(),
        normal.selector.normalized_revision_id.as_deref()
    );
    assert_eq!(outline["source"], value["metadata"]["source"]);
    assert_eq!(outline["nodes"].as_array().unwrap().len(), 1);
    assert_eq!(outline["nodes"][0]["nodeId"], normal.node_id);
    assert!(!outline
        .to_string()
        .contains(receipt["root"].as_str().unwrap()));

    let mut substituted = normal.clone();
    substituted.selector.document_revision_id = "018f0000-0000-7000-8000-ffffffffffff".into();
    assert!(matches!(read_text(substituted.clone()), Ok(None)));
    assert!(matches!(read_outline(&substituted), Ok(None)));
    let denied = text(&receipt["acceptedFixtures"]["denied"]);
    assert_ne!(normal.selector.attachment_id, denied.selector.attachment_id);
    assert!(matches!(read_text(denied.clone()), Ok(None)));
    assert!(matches!(read_outline(&denied), Ok(None)));
    let original = tauri::async_runtime::block_on(document_viewer_source(
        window.clone(),
        window.state(),
        window.state(),
        denied.source(),
    ))
    .unwrap()
    .expect("derive-denied copy remains inspectable");
    assert_eq!(
        original["source"]["attachmentId"],
        denied.selector.attachment_id
    );
    let original_range = range(
        &window,
        ViewerRangeRequest {
            schema_version: "1.0".into(),
            project_id: denied.project_id.clone(),
            selector: denied.selector.clone(),
            request_id: "018f0000-0000-7000-8000-000000000024".into(),
            start: 0,
            end: receipt["sourceBytes"].as_u64().unwrap(),
        },
    );
    let bytes = match original_range {
        Ok(response) => response.body().unwrap(),
        Err(_) => panic!("derive-denied copy original range failed"),
    };
    match bytes {
        tauri::ipc::InvokeResponseBody::Raw(bytes) => assert_eq!(
            format!("{:x}", Sha256::digest(bytes)),
            receipt["sourceSha256"].as_str().unwrap()
        ),
        _ => panic!("original range was not protected raw IPC"),
    }
    let large = text(&receipt["acceptedFixtures"]["large"]);
    assert_eq!(
        read_text(large.clone()),
        Err("viewer-resource-limit".into())
    );
    assert_eq!(read_outline(&large), Err("viewer-resource-limit".into()));
    assert_eq!(
        read_text(normal.clone()).unwrap().unwrap()["text"],
        value["text"]
    );

    window
        .state::<ApplicationLockManager>()
        .begin_terminal_exit();
    assert_eq!(
        read_text(normal.clone()),
        Err("viewer-source-unavailable".into())
    );
    assert_eq!(
        read_outline(&normal),
        Err("viewer-source-unavailable".into())
    );
    println!(
        "{}",
        json!({"kind":"native-viewer-accepted", "status":"PASS",
        "exactTextAndOutline":true, "substitutedSourceDenied":true, "copyDeriveDenied":true,
        "deniedCopyOriginalExact":true, "resourceLimitMapped":true, "freshRetryExact":true,
        "terminalCloseDenied":true, "inFlightCloseProven":false, "manualLockProven":false,
        "rendererInvokeDispatchProven":false, "parserOutput":"explicitly-synthetic", "modelExecuted":false})
    );
}

fn run_native_test(
    flag: &str,
    exercise: fn(tauri::WebviewWindow, PathBuf, PathBuf, PathBuf, Value),
) {
    assert_eq!(std::env::var(flag).as_deref(), Ok("1"));
    let repo = dunce::canonicalize(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..")).unwrap();
    let fixture =
        PathBuf::from(std::env::var_os("RO_VIEWER_NATIVE_FIXTURE").expect("fixture required"));
    assert_eq!(dunce::canonicalize(&fixture).unwrap(), fixture);
    assert_eq!(fixture.parent(), Some(repo.join("artifacts/tmp").as_path()));
    assert!(fixture
        .file_name()
        .unwrap()
        .to_str()
        .unwrap()
        .starts_with("directory-dialog-viewer-native-"));
    let python =
        PathBuf::from(std::env::var_os("RO_VIEWER_NATIVE_PYTHON").expect("Python required"));
    let payload = std::fs::read(fixture.join("viewer-receipt.json")).unwrap();
    assert!(payload.len() < 8192);
    let receipt: Value = serde_json::from_slice(&payload).unwrap();
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
        python.clone(),
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
    let window_config = context
        .config()
        .app
        .windows
        .iter()
        .find(|w| w.label == "main")
        .unwrap()
        .clone();
    for window in &mut context.config_mut().app.windows {
        window.create = false;
    }
    let result = Arc::new(Mutex::new(None));
    let destination = Arc::clone(&result);
    let app = crate::application_builder()
        .any_thread()
        .setup(move |app| {
            crate::setup_runtime(
                app,
                Ok(config),
                &fixture.join("application-data"),
                crate::DirectoryPickerManager::for_fixture(fixture.join("projects")),
            )?;
            let window = tauri::WebviewWindowBuilder::from_config(app, &window_config)?
                .data_directory(fixture.join("webview"))
                .visible(false)
                .drag_and_drop(false)
                .disable_drag_drop_handler()
                .title("Research Observatory — SYNTHETIC Reader Native handler test")
                .build()?;
            let app_handle = app.handle().clone();
            std::thread::spawn(move || {
                let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    exercise(window, repo, fixture, python, receipt)
                }));
                app_handle.state::<RuntimeSupervisor>().stop();
                *destination.lock().unwrap() = Some(outcome);
                app_handle.exit(0);
            });
            Ok(())
        })
        .build(context)
        .expect("real owned Wry app builds");
    assert_eq!(app.run_return(|_, _| {}), 0);
    match result
        .lock()
        .unwrap()
        .take()
        .expect("native test actually executed")
    {
        Ok(()) => (),
        Err(panic) => std::panic::resume_unwind(panic),
    }
}
