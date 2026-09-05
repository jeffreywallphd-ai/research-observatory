//! Disposable test composition: actual async native dispatch and supervised Core.

#[cfg(feature = "integration-harness")]
mod probe {
    use std::ffi::OsString;
    use std::io::{self, BufRead, Write};
    use std::path::PathBuf;

    use research_observatory_desktop_lib::{
        dispatch_core_api_request, dispatch_runtime_start, dispatch_runtime_stop,
        supervisor::{CoreApiRequest, RuntimeSupervisor, SupervisorConfig},
    };
    use serde_json::{Value, json};

    fn emit(value: &Value) -> Result<(), &'static str> {
        let mut output = io::stdout().lock();
        serde_json::to_writer(&mut output, value).map_err(|_| "probe-encode-failed")?;
        output
            .write_all(b"\n")
            .and_then(|_| output.flush())
            .map_err(|_| "probe-output-failed")
    }

    pub fn run() -> Result<(), &'static str> {
        let arguments: Vec<OsString> = std::env::args_os().skip(1).collect();
        if arguments
            .first()
            .is_some_and(|value| value == "--default-parent")
        {
            if arguments.len() != 1 {
                return Err("probe-arguments-invalid");
            }
            return emit(
                &json!({"kind":"actual-default-parent", "debugAssertions":cfg!(debug_assertions),
                "outcome":research_observatory_desktop_lib::directory_picker::default_project_parent(),
                "readOnly":true, "fixtureSubstitution":false}),
            );
        }
        if arguments
            .first()
            .is_some_and(|value| value == "--tauri-directory")
        {
            if arguments.len() != 3 {
                return Err("probe-arguments-invalid");
            }
            #[cfg(windows)]
            {
                use research_observatory_desktop_lib::directory_integration_harness::{Mode, run};
                let mode = arguments[1]
                    .to_str()
                    .and_then(Mode::parse)
                    .ok_or("probe-mode-invalid")?;
                return run(mode, &arguments[2]);
            }
            #[cfg(not(windows))]
            return Err("probe-windows-required");
        }
        if arguments
            .first()
            .is_some_and(|value| value == "--folder-dialog")
        {
            #[cfg(windows)]
            return super::folder_dialog::run(&arguments[1..]);
            #[cfg(not(windows))]
            return Err("probe-windows-required");
        }
        if arguments
            .first()
            .is_some_and(|value| value == "--check-packaged-path")
            && arguments.len() == 2
        {
            let result = SupervisorConfig::new(PathBuf::from(&arguments[1]));
            return emit(&json!({"accepted": result.is_ok(), "code": result.err()}));
        }
        if arguments.len() != 4 {
            return Err("probe-arguments-invalid");
        }
        let config = SupervisorConfig::for_integration_harness(
            PathBuf::from(&arguments[0]),
            PathBuf::from(&arguments[1]),
            vec![
                OsString::from("-m"),
                OsString::from("native_integration_sidecar"),
                OsString::from("--profile-vault-root"),
                arguments[3].clone(),
            ],
            vec![(OsString::from("PYTHONPATH"), arguments[2].clone())],
        )?;
        let supervisor = RuntimeSupervisor::new(Ok(config));
        let mut launches = Vec::new();
        let result = (|| {
            emit(&json!({"kind": "initialized", "snapshot": supervisor.status()}))?;
            for line in io::stdin().lock().lines() {
                let line = line.map_err(|_| "probe-input-failed")?;
                let value: Value = serde_json::from_str(&line).map_err(|_| "probe-json-invalid")?;
                match value.get("control").and_then(Value::as_str) {
                    Some("start") => {
                        let owned = supervisor.clone();
                        launches.push(std::thread::spawn(move || {
                            tauri::async_runtime::block_on(dispatch_runtime_start(owned))
                        }));
                        emit(&json!({"kind": "snapshot", "snapshot": supervisor.status()}))?;
                    }
                    Some("status") => {
                        emit(&json!({"kind": "snapshot", "snapshot": supervisor.status()}))?
                    }
                    Some("stop") => {
                        let snapshot = tauri::async_runtime::block_on(dispatch_runtime_stop(
                            supervisor.clone(),
                        ))?;
                        emit(&json!({"kind": "snapshot", "snapshot": snapshot}))?;
                    }
                    Some(_) => return Err("probe-control-invalid"),
                    None => {
                        let request: CoreApiRequest =
                            serde_json::from_value(value).map_err(|_| "probe-envelope-invalid")?;
                        match tauri::async_runtime::block_on(dispatch_core_api_request(
                            supervisor.clone(),
                            request,
                        )) {
                            Ok(response) => {
                                emit(&json!({"kind": "response", "response": response}))?
                            }
                            Err(code) => emit(&json!({"kind": "error", "code": code}))?,
                        }
                    }
                }
            }
            Ok(())
        })();
        let stopped = tauri::async_runtime::block_on(dispatch_runtime_stop(supervisor));
        for launch in launches {
            launch.join().map_err(|_| "probe-launch-thread-failed")??;
        }
        stopped?;
        result
    }
}

/// A real Windows dialog with synthetic generation authority. This deliberately
/// does not claim Tauri IPC, application-lock policy, Core, or profile proof.
#[cfg(all(feature = "integration-harness", windows))]
mod folder_dialog {
    use std::cell::RefCell;
    use std::ffi::OsString;
    use std::io::{self, Write};
    use std::os::windows::ffi::OsStrExt;
    use std::os::windows::fs::MetadataExt;
    use std::path::{Path, PathBuf};
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::sync::{Arc, Mutex};
    use std::time::{Duration, Instant};

    use research_observatory_desktop_lib::directory_picker::{
        CloseDisposition, DirectoryOutcome, DirectoryPickerManager, DirectoryPurpose,
        DirectoryRequest,
    };
    use serde::Serialize;
    use serde_json::{Value, json};
    use windows::core::w;
    use windows_sys::Win32::Foundation::{HWND, LPARAM, LRESULT, WPARAM};
    use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
    use windows_sys::Win32::System::Threading::GetCurrentProcessId;
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        CW_USEDEFAULT, CreateWindowExW, DefWindowProcW, DestroyWindow, DispatchMessageW,
        EnumWindows, GW_OWNER, GetClassNameW, GetMessageW, GetWindow, GetWindowThreadProcessId,
        IsWindowVisible, KillTimer, MSG, PostMessageW, PostQuitMessage, RegisterClassW, SetTimer,
        TranslateMessage, WM_APP, WM_CLOSE, WM_DESTROY, WM_TIMER, WNDCLASSW, WS_OVERLAPPEDWINDOW,
        WS_VISIBLE,
    };

    const OBSERVATION_TIMER: usize = 1;
    const RESULT_READY: u32 = WM_APP + 71;
    const CLEANUP_READY: u32 = WM_APP + 72;
    const CONTROL_DELAY: Duration = Duration::from_secs(10);

    #[derive(Clone, Copy, Eq, PartialEq)]
    enum Mode {
        Selection,
        GenerationCancel,
        MainClose,
    }

    impl Mode {
        fn parse(value: &str) -> Option<Self> {
            match value {
                "selection" => Some(Self::Selection),
                "generation-cancel" => Some(Self::GenerationCancel),
                "main-close" => Some(Self::MainClose),
                _ => None,
            }
        }

        fn name(self) -> &'static str {
            match self {
                Self::Selection => "selection",
                Self::GenerationCancel => "generation-cancel",
                Self::MainClose => "main-close",
            }
        }
    }

    #[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
    struct Counts {
        files: usize,
        directories: usize,
    }

    fn emit(value: &Value) -> Result<(), &'static str> {
        let mut output = io::stdout().lock();
        serde_json::to_writer(&mut output, value).map_err(|_| "probe-output-failed")?;
        output
            .write_all(b"\n")
            .and_then(|_| output.flush())
            .map_err(|_| "probe-output-failed")
    }

    fn non_reparse_directory(path: &Path) -> Result<(), &'static str> {
        let metadata = std::fs::symlink_metadata(path).map_err(|_| "probe-fixture-unavailable")?;
        if !metadata.is_dir()
            || metadata.file_type().is_symlink()
            || metadata.file_attributes() & 0x400 != 0
        {
            return Err("probe-fixture-invalid");
        }
        Ok(())
    }

    fn fixture_path(value: &OsString) -> Result<PathBuf, &'static str> {
        let repo = dunce::canonicalize(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.."))
            .map_err(|_| "probe-repository-unavailable")?;
        let parent = repo.join("artifacts/tmp");
        let path = PathBuf::from(value);
        // Do not resolve or inspect a caller path outside this exact fixture
        // boundary. The caller explicitly supplies a prepared synthetic child.
        let name = path
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or("probe-fixture-invalid")?;
        if path.parent() != Some(parent.as_path())
            || !name
                .strip_prefix("directory-dialog-")
                .is_some_and(|suffix| {
                    !suffix.is_empty()
                        && suffix
                            .bytes()
                            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
                })
        {
            return Err("probe-fixture-invalid");
        }
        for directory in [&repo, &repo.join("artifacts"), &parent, &path] {
            non_reparse_directory(directory)?;
        }
        if dunce::canonicalize(&path).map_err(|_| "probe-fixture-unavailable")? != path {
            return Err("probe-fixture-invalid");
        }
        Ok(path)
    }

    fn counts(root: &Path) -> Result<Counts, &'static str> {
        let mut result = Counts {
            files: 0,
            directories: 0,
        };
        let mut pending = vec![root.to_path_buf()];
        while let Some(directory) = pending.pop() {
            non_reparse_directory(&directory)?;
            result.directories += 1;
            for entry in std::fs::read_dir(&directory).map_err(|_| "probe-fixture-unavailable")? {
                let entry = entry.map_err(|_| "probe-fixture-unavailable")?;
                let metadata = std::fs::symlink_metadata(entry.path())
                    .map_err(|_| "probe-fixture-unavailable")?;
                if metadata.file_type().is_symlink() || metadata.file_attributes() & 0x400 != 0 {
                    return Err("probe-fixture-invalid");
                }
                if metadata.is_dir() {
                    pending.push(entry.path());
                } else if metadata.is_file() {
                    result.files += 1;
                } else {
                    return Err("probe-fixture-invalid");
                }
                if result.files + result.directories + pending.len() > 1024 {
                    return Err("probe-fixture-too-large");
                }
            }
        }
        Ok(result)
    }

    fn selected_is_fixture(path: &str, fixture: &Path) -> bool {
        let path = Path::new(path);
        // Test-scope denial precedes filesystem access and never echoes another
        // selection. The production picker already validates its canonical path.
        if !path.starts_with(fixture) {
            return false;
        }
        let Ok(relative) = path.strip_prefix(fixture) else {
            return false;
        };
        if relative
            .components()
            .any(|part| !matches!(part, std::path::Component::Normal(_)))
        {
            return false;
        }
        let mut current = fixture.to_path_buf();
        if non_reparse_directory(&current).is_err() {
            return false;
        }
        for component in relative.components() {
            current.push(component);
            if non_reparse_directory(&current).is_err() {
                return false;
            }
        }
        dunce::canonicalize(path).is_ok_and(|canonical| canonical == path)
    }

    #[derive(Default)]
    struct OwnedDialogs {
        owner: isize,
        count: usize,
        first: Option<isize>,
    }

    unsafe extern "system" fn observe_window(window: HWND, data: LPARAM) -> i32 {
        let observation = unsafe { &mut *(data as *mut OwnedDialogs) };
        let mut process = 0;
        if unsafe { GetWindowThreadProcessId(window, &mut process) } == 0
            || process != unsafe { GetCurrentProcessId() }
            || unsafe { GetWindow(window, GW_OWNER) } as isize != observation.owner
            || unsafe { IsWindowVisible(window) } == 0
        {
            return 1;
        }
        let mut class = [0u16; 32];
        let length = unsafe { GetClassNameW(window, class.as_mut_ptr(), class.len() as i32) };
        if length > 0 && String::from_utf16_lossy(&class[..length as usize]) == "#32770" {
            observation.count += 1;
            observation.first.get_or_insert(window as isize);
        }
        1
    }

    fn owned_dialogs(owner: isize) -> OwnedDialogs {
        let mut observation = OwnedDialogs {
            owner,
            ..Default::default()
        };
        unsafe {
            EnumWindows(
                Some(observe_window),
                &mut observation as *mut OwnedDialogs as isize,
            )
        };
        observation
    }

    struct Witness {
        owner: isize,
        mode: Mode,
        manager: DirectoryPickerManager,
        generation: Arc<AtomicU64>,
        result: Arc<Mutex<Option<DirectoryOutcome>>>,
        fixture: PathBuf,
        before: Counts,
        started: Instant,
        triggered: bool,
        closing: bool,
        cleanup_ready: bool,
        result_received: bool,
        first_dialog: Option<isize>,
        max_dialogs: usize,
    }

    impl Witness {
        fn observe(&mut self) {
            let observed = owned_dialogs(self.owner);
            self.max_dialogs = self.max_dialogs.max(observed.count);
            if self.first_dialog.is_none() {
                self.first_dialog = observed.first;
            }
        }

        fn request_close(&mut self) {
            if self.closing {
                return;
            }
            self.closing = true;
            self.generation.fetch_add(1, Ordering::SeqCst);
            let disposition = self.manager.begin_close();
            self.cleanup_ready = matches!(disposition, CloseDisposition::CloseNow);
            if !self.cleanup_ready {
                let manager = self.manager.clone();
                let owner = self.owner;
                std::thread::spawn(move || {
                    manager.wait_for_cleanup();
                    unsafe { PostMessageW(owner as HWND, CLEANUP_READY, 0, 0) };
                });
            }
            self.finish_close();
        }

        fn finish_close(&self) {
            if self.closing && self.cleanup_ready && self.result_received {
                unsafe { DestroyWindow(self.owner as HWND) };
            }
        }

        fn receive_result(&mut self) {
            let result = self.result.lock().ok().and_then(|mut result| result.take());
            let Some(mut result) = result else {
                return;
            };
            self.observe();
            let outside_fixture = matches!(&result, DirectoryOutcome::Selected { path } if !selected_is_fixture(path, &self.fixture));
            if outside_fixture {
                result = DirectoryOutcome::Failed;
            }
            self.result_received = true;
            let after = counts(&self.fixture);
            let _ = emit(&json!({
                "kind":"folder-dialog-result", "mode":self.mode.name(),
                "scope":"actual-native-dialog-with-synthetic-generation-not-tauri-ipc-or-sign-in",
                "result":result, "selectionOutsideFixtureRejected":outside_fixture,
                "ownerHwnd":self.owner, "observedOwnedDialogHwnd":self.first_dialog,
                "maximumVisibleOwnedDialogs":self.max_dialogs,
                "visibleOwnedDialogsAfterResult":owned_dialogs(self.owner).count,
                "elapsedMilliseconds":self.started.elapsed().as_millis(),
                "before":self.before, "after":after.as_ref().ok(),
                "fixtureCountsUnchanged":after.is_ok_and(|after| after == self.before),
            }));
            self.finish_close();
        }
    }

    thread_local! { static WITNESS: RefCell<Option<Witness>> = const { RefCell::new(None) }; }

    unsafe extern "system" fn window_proc(
        window: HWND,
        message: u32,
        wparam: WPARAM,
        lparam: LPARAM,
    ) -> LRESULT {
        if message == WM_DESTROY {
            // Destruction can reenter while the state is borrowed by finish_close.
            unsafe {
                KillTimer(window, OBSERVATION_TIMER);
                PostQuitMessage(0);
            }
            return 0;
        }
        let handled = WITNESS.with(|slot| {
            let Ok(mut slot) = slot.try_borrow_mut() else { return false; };
            let Some(witness) = slot.as_mut() else { return false; };
            match message {
                WM_TIMER if wparam == OBSERVATION_TIMER => {
                    witness.observe();
                    if !witness.triggered && !witness.result_received && witness.started.elapsed() >= CONTROL_DELAY {
                        witness.triggered = true;
                        match witness.mode {
                            Mode::Selection => {}
                            Mode::GenerationCancel => {
                                witness.generation.fetch_add(1, Ordering::SeqCst);
                                witness.manager.cancel_pending();
                                let _ = emit(&json!({"kind":"synthetic-generation-invalidated", "mode":witness.mode.name()}));
                            }
                            Mode::MainClose => {
                                let _ = emit(&json!({"kind":"synthetic-main-close-requested", "mode":witness.mode.name()}));
                                witness.request_close();
                            }
                        }
                    }
                }
                RESULT_READY => witness.receive_result(),
                CLEANUP_READY => { witness.cleanup_ready = true; witness.finish_close(); }
                WM_CLOSE => witness.request_close(),
                _ => return false,
            }
            true
        });
        if handled {
            0
        } else {
            unsafe { DefWindowProcW(window, message, wparam, lparam) }
        }
    }

    pub fn run(arguments: &[OsString]) -> Result<(), &'static str> {
        if arguments.len() != 2 {
            return Err("probe-arguments-invalid");
        }
        let mode = arguments[0]
            .to_str()
            .and_then(Mode::parse)
            .ok_or("probe-mode-invalid")?;
        let fixture = fixture_path(&arguments[1])?;
        let before = counts(&fixture)?;
        let instance = unsafe { GetModuleHandleW(std::ptr::null()) };
        let class = unsafe {
            RegisterClassW(&WNDCLASSW {
                lpfnWndProc: Some(window_proc),
                hInstance: instance,
                lpszClassName: w!("ResearchObservatory.SyntheticDirectoryDialogOwner").as_ptr(),
                ..Default::default()
            })
        };
        if instance.is_null() || class == 0 {
            return Err("probe-window-unavailable");
        }
        let title = OsString::from(format!(
            "RO T03 SYNTHETIC folder dialog - {} (not sign-in)",
            mode.name()
        ))
        .encode_wide()
        .chain(Some(0))
        .collect::<Vec<_>>();
        let owner = unsafe {
            CreateWindowExW(
                0,
                w!("ResearchObservatory.SyntheticDirectoryDialogOwner").as_ptr(),
                title.as_ptr(),
                WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                CW_USEDEFAULT,
                CW_USEDEFAULT,
                720,
                360,
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                instance,
                std::ptr::null(),
            )
        };
        if owner.is_null() {
            return Err("probe-window-unavailable");
        }
        let owner = owner as isize;
        let manager = DirectoryPickerManager::default();
        let generation = Arc::new(AtomicU64::new(1));
        let result = Arc::new(Mutex::new(None));
        WITNESS.with(|slot| {
            *slot.borrow_mut() = Some(Witness {
                owner,
                mode,
                manager: manager.clone(),
                generation: Arc::clone(&generation),
                result: Arc::clone(&result),
                fixture: fixture.clone(),
                before,
                started: Instant::now(),
                triggered: false,
                closing: false,
                cleanup_ready: false,
                result_received: false,
                first_dialog: None,
                max_dialogs: 0,
            })
        });
        if unsafe { SetTimer(owner as HWND, OBSERVATION_TIMER, 100, None) } == 0 {
            unsafe { DestroyWindow(owner as HWND) };
            return Err("probe-timer-unavailable");
        }
        emit(
            &json!({"kind":"folder-dialog-start", "mode":mode.name(), "ownerHwnd":owner,
            "scope":"actual-native-dialog-with-synthetic-generation-not-tauri-ipc-or-sign-in",
            "timerMilliseconds":if mode == Mode::Selection { None } else { Some(CONTROL_DELAY.as_millis()) },
            "before":before, "fixture":fixture, "createsDirectories":false,
            "instruction":"Use only this synthetic dialog; after a selection or Escape, close its synthetic owner window."}),
        )?;
        let worker_manager = manager.clone();
        let worker = std::thread::spawn(move || {
            let request = DirectoryRequest {
                purpose: DirectoryPurpose::CreateParent,
                previous_location: fixture.to_str().map(str::to_owned),
            };
            let outcome = worker_manager.choose(owner, request, move || {
                generation.load(Ordering::SeqCst) == 1
            });
            if let Ok(mut result) = result.lock() {
                *result = Some(outcome);
            }
            unsafe { PostMessageW(owner as HWND, RESULT_READY, 0, 0) };
        });
        let mut message = MSG::default();
        loop {
            let status = unsafe { GetMessageW(&mut message, std::ptr::null_mut(), 0, 0) };
            if status <= 0 {
                break;
            }
            unsafe {
                TranslateMessage(&message);
                DispatchMessageW(&message);
            }
        }
        manager.cancel_pending();
        worker.join().map_err(|_| "probe-worker-failed")?;
        manager.wait_for_cleanup();
        let cleanup = WITNESS
            .with(|slot| slot.borrow_mut().take())
            .ok_or("probe-state-unavailable")?;
        emit(
            &json!({"kind":"folder-dialog-cleanup", "mode":mode.name(), "ownerHwnd":owner,
            "resultObserved":cleanup.result_received, "nativeAdmissionClosed":!manager.is_open(),
            "observedOwnedDialogHwnd":cleanup.first_dialog,
            "maximumVisibleOwnedDialogs":cleanup.max_dialogs,
            "visibleOwnedDialogsRemaining":owned_dialogs(owner).count,
            "fixtureCountsUnchanged":counts(&cleanup.fixture).is_ok_and(|after| after == cleanup.before),
            "scope":"actual-native-dialog-with-synthetic-generation-not-tauri-ipc-or-sign-in"}),
        )
    }
}

#[cfg(feature = "integration-harness")]
fn main() {
    if let Err(code) = probe::run() {
        eprintln!("{code}");
        std::process::exit(1);
    }
}

#[cfg(not(feature = "integration-harness"))]
fn main() {
    eprintln!("The disposable probe requires the integration-harness feature.");
    std::process::exit(1);
}
