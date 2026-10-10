//! Task-specific actual Native/Core/encrypted-source/held-output proof.
//! Direct handler calls are not renderer dispatch or native-dialog proof.
use super::*;
use crate::supervisor::{CoreApiRequest, RuntimeState, SupervisorConfig};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};
use tauri::Manager;

// This product test operates only the one modal dialog owned by its synthetic
// Wry window. It never reads or operates another application's windows.
fn select_owned_output_folder(owner: isize) -> std::thread::JoinHandle<()> {
    std::thread::spawn(move || {
        use windows_sys::Win32::UI::WindowsAndMessaging::*;
        struct Search {
            owner: isize,
            found: isize,
        }
        unsafe extern "system" fn find(
            window: windows_sys::Win32::Foundation::HWND,
            parameter: isize,
        ) -> i32 {
            let state = unsafe { &mut *(parameter as *mut Search) };
            let mut process = 0;
            unsafe {
                GetWindowThreadProcessId(window, &mut process);
            }
            if process != std::process::id()
                || unsafe { GetWindow(window, GW_OWNER) } as isize != state.owner
            {
                return 1;
            }
            let mut title = [0u16; 256];
            let length = unsafe { GetWindowTextW(window, title.as_mut_ptr(), 256) };
            if String::from_utf16_lossy(&title[..length.max(0) as usize])
                == "Choose where to save the Reader output"
                && unsafe { IsWindowVisible(window) } != 0
            {
                assert_eq!(state.found, 0, "owned task dialog must be unique");
                state.found = window as isize;
            }
            1
        }
        let started = Instant::now();
        let mut search = Search { owner, found: 0 };
        while search.found == 0 {
            assert!(
                started.elapsed() < Duration::from_secs(10),
                "actual owned output dialog must appear"
            );
            unsafe {
                EnumWindows(Some(find), &mut search as *mut _ as isize);
            }
            std::thread::sleep(Duration::from_millis(25));
        }
        // The fixture starts at its confined projects folder. IDOK selects that
        // exact visible folder through the normal real Shell dialog path.
        assert_ne!(
            unsafe { PostMessageW(search.found as _, WM_COMMAND, 1, 0) },
            0
        );
    })
}

fn exercise(window: tauri::WebviewWindow, fixture: PathBuf, receipt: Value) {
    let supervisor = window.state::<RuntimeSupervisor>();
    let started = Instant::now();
    while supervisor.status().state != RuntimeState::Ready {
        assert!(started.elapsed() < Duration::from_secs(60));
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
    let source = receipt["acceptedFixtures"]["normal"]["selector"].clone();
    let anchor = receipt["acceptedFixtures"]["anchors"][0].clone();
    let mut request:ReaderActionRequest=serde_json::from_value(json!({"schemaVersion":"1.0","projectId":receipt["projectId"],
        "selector":source,"operationId":frame_id().unwrap(),"stage":"policy","action":"export-quotation","anchorId":anchor,
        "expectedPolicyRevisionId":null,"commandId":null,"confirmed":false})).unwrap();
    let call = |request: ReaderActionRequest| {
        tauri::async_runtime::block_on(document_viewer_action(
            window.clone(),
            window.state(),
            window.state(),
            window.state(),
            window.state(),
            request,
        ))
        .unwrap()
    };
    let initial = call(request.clone());
    assert_eq!(initial.status, "policy");
    assert!(initial.drained);
    let decision = initial.decision.unwrap();
    assert_eq!(decision["state"], "review-required");
    assert_eq!(decision["canReview"], true);
    let denied = call(ReaderActionRequest {
        operation_id: frame_id().unwrap(),
        stage: ActionStage::DeniedAttempt,
        ..request.clone()
    });
    assert_eq!(
        denied.decision.unwrap()["reasonCode"],
        "viewer-direct-transfer-disabled"
    );
    request.expected_policy_revision_id = decision["policyRevisionId"].as_str().map(str::to_owned);
    let command = frame_id().unwrap();
    let review_request = ReaderActionRequest {
        operation_id: frame_id().unwrap(),
        stage: ActionStage::RightsReview,
        anchor_id: None,
        command_id: Some(command),
        confirmed: true,
        ..request.clone()
    };
    let recorded = call(review_request.clone());
    assert_eq!(recorded.status, "recorded");
    assert!(recorded.drained);
    assert!(
        !fixture.join("output").exists(),
        "permission review cannot deliver output"
    );
    let review = recorded.review.unwrap();
    let replay = call(ReaderActionRequest {
        operation_id: frame_id().unwrap(),
        ..review_request
    });
    assert_eq!(
        replay.review.unwrap(),
        review,
        "semantic retry returns the exact reviewed receipt"
    );
    request.expected_policy_revision_id = review["policyRevisionId"].as_str().map(str::to_owned);
    request.operation_id = frame_id().unwrap();
    let ready = call(request.clone());
    assert_eq!(ready.decision.unwrap()["state"], "ready");
    let gate = window.state::<ApplicationLockManager>();
    let ticket = gate.begin_protected_action().unwrap();
    let connection = Arc::new(
        supervisor
            .native_document_connection(&request.project_id)
            .unwrap(),
    );
    request.stage = ActionStage::Execute;
    request.confirmed = true;
    request.operation_id = frame_id().unwrap();
    let owners = window.state::<ViewerActionManager>();
    let lease = owners
        .begin(
            &request,
            crate::directory_window_handle(&window).unwrap(),
            connection,
        )
        .unwrap();
    let active = &lease.active;
    let current = || {
        !active.cancelled.load(Ordering::Acquire)
            && active.connection.is_current()
            && gate.finish_protected_action(ticket).is_ok()
    };
    let data = payload(active, &request, None, &current).unwrap();
    let value: Value = serde_json::from_str(&data.content_utf8).unwrap();
    assert_eq!(value["text"], "SYNTHETIC");
    assert_eq!(value["anchorId"], anchor);
    assert_eq!(
        value["source"]["documentRevisionId"],
        source["documentRevisionId"]
    );
    assert_eq!(
        value["normalizedRevisionId"],
        source["normalizedRevisionId"]
    );
    assert!(value.get("context").is_none() && value.get("prefix").is_none());
    let destination = fixture.join("output");
    std::fs::create_dir(&destination).unwrap();
    let mut output = LocalDeliverable::create(&destination, &request.operation_id, "json").unwrap();
    output
        .append(data.content_utf8.as_bytes(), &current)
        .unwrap();
    output
        .verify(
            &data.content_sha256,
            data.content_utf8.len() as u64,
            &current,
        )
        .unwrap();
    fresh(active, &request, &data, &current).unwrap();
    gate.commit_protected_action(ticket, || {
        active
            .connection
            .publish_current(|| output.publish(&|| true))
    })
    .unwrap();
    drop(output);
    let delivered: Value = serde_json::from_slice(
        &std::fs::read(destination.join(format!("reader-{}.json", request.operation_id))).unwrap(),
    )
    .unwrap();
    assert_eq!(delivered, value);
    drop(lease);

    let execution = ReaderActionRequest {
        operation_id: frame_id().unwrap(),
        ..request.clone()
    };
    let output_path = fixture
        .join("projects")
        .join(format!("reader-{}.json", execution.operation_id));
    let chooser = select_owned_output_folder(crate::directory_window_handle(&window).unwrap());
    let outcome = call(execution);
    chooser.join().unwrap();
    assert_eq!(outcome.status, "completed");
    assert!(outcome.drained);
    let dialog_output: Value =
        serde_json::from_slice(&std::fs::read(output_path).unwrap()).unwrap();
    assert_eq!(
        dialog_output, value,
        "actual Native destination/action wiring must deliver the exact payload"
    );
    let unsupported = call(ReaderActionRequest {
        operation_id: frame_id().unwrap(),
        stage: ActionStage::Policy,
        action: ReaderAction::PrintQuotation,
        confirmed: false,
        ..request.clone()
    });
    assert_eq!(
        unsupported.decision.unwrap()["state"],
        "review-required",
        "export permission does not authorize print"
    );
    window
        .state::<ApplicationLockManager>()
        .begin_terminal_exit();
    assert!(
        tauri::async_runtime::block_on(document_viewer_action(
            window.clone(),
            window.state(),
            window.state(),
            window.state(),
            window.state(),
            ReaderActionRequest {
                operation_id: frame_id().unwrap(),
                stage: ActionStage::Policy,
                confirmed: false,
                ..request
            }
        ))
        .is_err()
    );
    println!(
        "{}",
        json!({"kind":"native-reader-rights-output","status":"PASS","encryptedSourceAndActualCore":true,
        "distinctNonExecutingReviewAndReplay":true,"directTransferDenied":true,"fixedActionScope":true,
        "exactQuotationSourceAndAnchorIdentifiers":true,"heldCreateNewLocalOutput":true,"terminalDeliveryDenied":true,
            "rendererDispatchProven":false,"nativeDialogProven":true,"modelExecuted":false})
    );
}

#[test]
#[ignore = "opt-in actual owned Wry/Core principal and authored encrypted source"]
fn actual_native_rights_review_payload_and_local_output_preserve_source_identity() {
    assert_eq!(
        std::env::var("RO_RUN_VIEWER_ACTION_NATIVE").as_deref(),
        Ok("1")
    );
    let repo = dunce::canonicalize(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..")).unwrap();
    let fixture = PathBuf::from(std::env::var_os("RO_VIEWER_NATIVE_FIXTURE").unwrap());
    assert_eq!(dunce::canonicalize(&fixture).unwrap(), fixture);
    assert_eq!(fixture.parent(), Some(repo.join("artifacts/tmp").as_path()));
    assert!(
        fixture
            .file_name()
            .unwrap()
            .to_str()
            .unwrap()
            .starts_with("directory-dialog-viewer-native-")
    );
    let python = PathBuf::from(std::env::var_os("RO_VIEWER_NATIVE_PYTHON").unwrap());
    let bytes = std::fs::read(fixture.join("viewer-receipt.json")).unwrap();
    assert!(bytes.len() < 8192);
    let receipt: Value = serde_json::from_slice(&bytes).unwrap();
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
                DirectoryPickerManager::for_fixture(fixture.join("projects")),
            )?;
            let window = tauri::WebviewWindowBuilder::from_config(app, &window_config)?
                .data_directory(fixture.join("webview"))
                .visible(false)
                .drag_and_drop(false)
                .disable_drag_drop_handler()
                .title("Research Observatory — SYNTHETIC rights action test")
                .build()?;
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    exercise(window, fixture, receipt)
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
    match result
        .lock()
        .unwrap()
        .take()
        .expect("actual Native test must execute")
    {
        Ok(()) => (),
        Err(panic) => std::panic::resume_unwind(panic),
    }
}
