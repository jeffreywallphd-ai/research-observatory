use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::{Duration, Instant};

use research_observatory_desktop_lib::supervisor::{
    CoreApiRequest, RuntimeSnapshot, RuntimeState, RuntimeSupervisor, SupervisorConfig,
};
use research_observatory_desktop_lib::{
    dispatch_core_api_request, dispatch_runtime_start, dispatch_runtime_stop,
};
use serde::Serialize;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct Report {
    ok: bool,
    duplicate_start_pid_stable: bool,
    cancelled_start_left_no_process: bool,
    graceful_stop: RuntimeSnapshot,
    crash_detected: bool,
    restart_pid_changed: bool,
    restart_limit: RuntimeSnapshot,
    async_command_cancelled: bool,
    port_zero_rejected: bool,
    malformed_handshake_rejected: bool,
    early_exit_classified: bool,
    readiness_timeout_classified: bool,
    graceful_tree_cleanup: bool,
    forced_tree_cleanup: bool,
    job_close_tree_cleanup: bool,
    stop_retry_serialized: bool,
    delayed_readiness_cleanup: bool,
    generated_contract_request: bool,
    problem_trace_preserved: bool,
    unsafe_api_path_denied: bool,
    incompatible_api_rejected: bool,
}

static FIXTURE_SEQUENCE: AtomicU64 = AtomicU64::new(1);

fn require_state(snapshot: &RuntimeSnapshot, expected: RuntimeState, label: &str) {
    assert_eq!(snapshot.state, expected, "{label}: {snapshot:?}");
}

#[cfg(windows)]
fn terminate(pid: u32) {
    use windows_sys::Win32::Foundation::{CloseHandle, WAIT_OBJECT_0};
    use windows_sys::Win32::System::Threading::{
        OpenProcess, PROCESS_SYNCHRONIZE, PROCESS_TERMINATE, TerminateProcess, WaitForSingleObject,
    };

    unsafe {
        let process = OpenProcess(PROCESS_TERMINATE | PROCESS_SYNCHRONIZE, 0, pid);
        assert!(!process.is_null(), "failed to open supervised process");
        assert_ne!(
            TerminateProcess(process, 97),
            0,
            "failed to terminate supervised process"
        );
        assert_eq!(
            WaitForSingleObject(process, 5_000),
            WAIT_OBJECT_0,
            "supervised process did not terminate",
        );
        CloseHandle(process);
    }
}

#[cfg(not(windows))]
fn terminate(_pid: u32) {
    panic!("CAP-01.S03 supervision qualification is release-authoritative on Windows x64");
}

fn wait_for_crash(supervisor: &RuntimeSupervisor) -> RuntimeSnapshot {
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        let snapshot = supervisor.status();
        if snapshot.state == RuntimeState::Crashed {
            return snapshot;
        }
        assert!(
            Instant::now() < deadline,
            "supervisor did not observe the process crash"
        );
        thread::sleep(Duration::from_millis(20));
    }
}

fn fixture_config(source: &Path, mode: &str) -> (PathBuf, SupervisorConfig) {
    let sequence = FIXTURE_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let root = std::env::temp_dir().join(format!(
        "research-observatory-supervisor-{}-{sequence}",
        std::process::id()
    ));
    fs::create_dir(&root).expect("create unique supervisor fixture directory");
    fs::write(root.join("fixture-mode.txt"), mode).expect("write fixture mode");
    let executable = root.join("research-observatory-core-x86_64-pc-windows-msvc.exe");
    fs::copy(source, &executable).expect("copy supervisor fixture executable");
    let canonical = dunce::canonicalize(executable).expect("canonical fixture executable");
    let config = SupervisorConfig::new(canonical).expect("valid supervisor fixture package");
    (root, config)
}

fn wait_for_child_pid(root: &Path) -> u32 {
    wait_for_pid(root.join("fixture-child.pid"), "fixture descendant")
}

fn wait_for_root_pid(root: &Path) -> u32 {
    wait_for_pid(root.join("fixture-root.pid"), "fixture root")
}

fn wait_for_pid(path: PathBuf, label: &str) -> u32 {
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        if let Ok(value) = fs::read_to_string(&path) {
            return value.trim().parse().expect("fixture PID");
        }
        assert!(Instant::now() < deadline, "{label} did not start");
        thread::sleep(Duration::from_millis(10));
    }
}

fn wait_for_marker(root: &Path, name: &str) {
    let path = root.join(name);
    let deadline = Instant::now() + Duration::from_secs(3);
    while !path.is_file() {
        assert!(
            Instant::now() < deadline,
            "fixture marker {name} was not written"
        );
        thread::sleep(Duration::from_millis(10));
    }
}

#[cfg(windows)]
fn process_is_alive(pid: u32) -> bool {
    use windows_sys::Win32::Foundation::{CloseHandle, WAIT_TIMEOUT};
    use windows_sys::Win32::System::Threading::{
        OpenProcess, PROCESS_SYNCHRONIZE, WaitForSingleObject,
    };
    unsafe {
        let process = OpenProcess(PROCESS_SYNCHRONIZE, 0, pid);
        if process.is_null() {
            return false;
        }
        let alive = WaitForSingleObject(process, 0) == WAIT_TIMEOUT;
        CloseHandle(process);
        alive
    }
}

#[cfg(not(windows))]
fn process_is_alive(_pid: u32) -> bool {
    false
}

fn require_process_tree_stopped(root_pid: u32, child_pid: u32, label: &str) {
    let deadline = Instant::now() + Duration::from_secs(5);
    while process_is_alive(root_pid) || process_is_alive(child_pid) {
        assert!(
            Instant::now() < deadline,
            "{label}: supervised process tree remained alive"
        );
        thread::sleep(Duration::from_millis(20));
    }
}

fn require_failure(
    config: SupervisorConfig,
    state: RuntimeState,
    diagnostic: &'static str,
    label: &str,
) {
    let supervisor = RuntimeSupervisor::new(Ok(config));
    let snapshot = supervisor.start();
    require_state(&snapshot, state, label);
    assert_eq!(snapshot.diagnostic_reference, Some(diagnostic), "{label}");
    assert_eq!(supervisor.active_pid(), None, "{label}: process survived");
}

fn remove_fixture(root: PathBuf) {
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        match fs::remove_dir_all(&root) {
            Ok(()) => return,
            Err(_) if Instant::now() < deadline => thread::sleep(Duration::from_millis(20)),
            Err(error) => panic!("remove fixture {}: {error}", root.display()),
        }
    }
}

fn main() {
    let executable = std::env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .expect("usage: supervision_check <canonical-sidecar-executable> <fixture-executable>");
    let fixture_executable = std::env::args_os()
        .nth(2)
        .map(PathBuf::from)
        .expect("usage: supervision_check <canonical-sidecar-executable> <fixture-executable>");
    let config = SupervisorConfig::new(executable).expect("sidecar fixture must be canonical");

    let graceful = RuntimeSupervisor::new(Ok(config.clone()));
    require_state(&graceful.start(), RuntimeState::Ready, "initial start");
    let first_pid = graceful.active_pid().expect("ready process PID");
    require_state(&graceful.start(), RuntimeState::Ready, "duplicate start");
    let duplicate_start_pid_stable = graceful.active_pid() == Some(first_pid);
    assert!(
        duplicate_start_pid_stable,
        "duplicate start created another process"
    );
    let version_response = tauri::async_runtime::block_on(dispatch_core_api_request(
        graceful.clone(),
        CoreApiRequest {
            method: "GET".to_owned(),
            path: "/runtime/version".to_owned(),
            body: None,
            if_match: None,
            idempotency_key: None,
        },
    ))
    .expect("authenticated generated-contract request");
    let version: serde_json::Value =
        serde_json::from_str(&version_response.body).expect("version response JSON");
    let generated_contract_request = version_response.status == 200
        && version_response.content_type == "application/json"
        && version_response.trace_id.len() == 32
        && version["service"] == "research-observatory-core"
        && version["apiVersion"] == "1.0.0"
        && version["minimumClientApiVersion"] == "1.0.0"
        && version["maximumClientApiVersionExclusive"] == "2.0.0"
        && !version_response.body.contains("Bearer")
        && !version_response.body.contains("token");
    assert!(
        generated_contract_request,
        "version contract request failed"
    );

    let missing_response = graceful
        .api_request(&CoreApiRequest {
            method: "GET".to_owned(),
            path: "/runtime/operations/op-missing".to_owned(),
            body: None,
            if_match: None,
            idempotency_key: None,
        })
        .expect("authenticated missing-operation request");
    let missing: serde_json::Value =
        serde_json::from_str(&missing_response.body).expect("problem response JSON");
    let problem_trace_preserved = missing_response.status == 404
        && missing_response.content_type == "application/problem+json"
        && missing["code"] == "RO-CORE-OPERATION-NOT-FOUND"
        && missing["traceId"] == missing_response.trace_id
        && missing.get("exception").is_none()
        && missing.get("path").is_none();
    assert!(problem_trace_preserved, "problem trace contract failed");

    let unsafe_api_path_denied = graceful
        .api_request(&CoreApiRequest {
            method: "GET".to_owned(),
            path: "https://evil.invalid/runtime/version".to_owned(),
            body: None,
            if_match: None,
            idempotency_key: None,
        })
        .is_err();
    assert!(
        unsafe_api_path_denied,
        "unsafe native API path was accepted"
    );
    let graceful_stop = graceful.stop();
    require_state(&graceful_stop, RuntimeState::Stopped, "graceful stop");
    assert_eq!(
        graceful.active_pid(),
        None,
        "graceful stop retained a process"
    );

    let cancellation = RuntimeSupervisor::new(Ok(config.clone()));
    let starting = cancellation.clone();
    let startup = thread::spawn(move || starting.start());
    let cancellation_deadline = Instant::now() + Duration::from_secs(2);
    while cancellation.status().state != RuntimeState::Starting {
        assert!(
            Instant::now() < cancellation_deadline,
            "startup did not enter its cancellable phase"
        );
        thread::sleep(Duration::from_millis(1));
    }
    let cancelled = cancellation.stop();
    require_state(&cancelled, RuntimeState::Stopped, "cancel startup");
    require_state(
        &startup.join().expect("startup thread"),
        RuntimeState::Stopped,
        "cancelled start result",
    );
    let cancelled_start_left_no_process = cancellation.active_pid().is_none();
    assert!(
        cancelled_start_left_no_process,
        "cancelled startup retained a process"
    );

    let crashing = RuntimeSupervisor::new(Ok(config));
    require_state(&crashing.start(), RuntimeState::Ready, "crash attempt one");
    let crashed_pid = crashing.active_pid().expect("first crash PID");
    terminate(crashed_pid);
    let first_crash = wait_for_crash(&crashing);
    assert_eq!(first_crash.diagnostic_reference, Some("RO-CORE-CRASHED"));

    require_state(&crashing.start(), RuntimeState::Ready, "crash attempt two");
    let second_pid = crashing.active_pid().expect("second crash PID");
    let restart_pid_changed = second_pid != crashed_pid;
    assert!(restart_pid_changed, "restart reused the terminated PID");
    terminate(second_pid);
    wait_for_crash(&crashing);

    require_state(
        &crashing.start(),
        RuntimeState::Ready,
        "crash attempt three",
    );
    terminate(crashing.active_pid().expect("third crash PID"));
    wait_for_crash(&crashing);
    let restart_limit = crashing.start();
    require_state(
        &restart_limit,
        RuntimeState::RecoveryRequired,
        "restart limit",
    );
    assert!(!restart_limit.retry_available);
    assert_eq!(
        restart_limit.diagnostic_reference,
        Some("RO-CORE-RESTART-LIMIT")
    );
    assert_eq!(crashing.active_pid(), None);

    let (port_zero_root, port_zero_config) = fixture_config(&fixture_executable, "port-zero");
    require_failure(
        port_zero_config,
        RuntimeState::Incompatible,
        "RO-CORE-INCOMPATIBLE",
        "port-zero handshake",
    );
    remove_fixture(port_zero_root);

    let (malformed_root, malformed_config) =
        fixture_config(&fixture_executable, "malformed-handshake");
    require_failure(
        malformed_config,
        RuntimeState::Incompatible,
        "RO-CORE-HANDSHAKE-INVALID",
        "malformed handshake",
    );
    remove_fixture(malformed_root);

    let (early_root, early_config) = fixture_config(&fixture_executable, "early-exit");
    require_failure(
        early_config,
        RuntimeState::Crashed,
        "RO-CORE-EARLY-EXIT",
        "early exit",
    );
    remove_fixture(early_root);

    let (timeout_root, timeout_config) = fixture_config(&fixture_executable, "never-ready");
    require_failure(
        timeout_config,
        RuntimeState::Crashed,
        "RO-CORE-START-TIMEOUT",
        "readiness timeout",
    );
    remove_fixture(timeout_root);

    let (api_incompatible_root, api_incompatible_config) =
        fixture_config(&fixture_executable, "api-incompatible");
    require_failure(
        api_incompatible_config,
        RuntimeState::Incompatible,
        "RO-CORE-API-INCOMPATIBLE",
        "incompatible generated API contract",
    );
    remove_fixture(api_incompatible_root);

    let (command_root, command_config) = fixture_config(&fixture_executable, "never-ready");
    let command_supervisor = RuntimeSupervisor::new(Ok(command_config));
    let command_start = command_supervisor.clone();
    let start_dispatch = thread::spawn(move || {
        tauri::async_runtime::block_on(dispatch_runtime_start(command_start))
            .expect("async start dispatch")
    });
    let command_deadline = Instant::now() + Duration::from_secs(2);
    while command_supervisor.status().state != RuntimeState::Starting {
        assert!(
            Instant::now() < command_deadline,
            "async command did not start"
        );
        thread::sleep(Duration::from_millis(1));
    }
    let cancel_started = Instant::now();
    let command_stop =
        tauri::async_runtime::block_on(dispatch_runtime_stop(command_supervisor.clone()))
            .expect("async stop dispatch");
    require_state(&command_stop, RuntimeState::Stopped, "async command stop");
    require_state(
        &start_dispatch.join().expect("start dispatch thread"),
        RuntimeState::Stopped,
        "cancelled async command",
    );
    let async_command_cancelled = cancel_started.elapsed() < Duration::from_secs(2)
        && command_supervisor.active_pid().is_none();
    assert!(
        async_command_cancelled,
        "async command cancellation blocked"
    );
    remove_fixture(command_root);

    let (delayed_root, delayed_config) = fixture_config(&fixture_executable, "child-delayed-ready");
    let delayed = RuntimeSupervisor::new(Ok(delayed_config));
    let delayed_start = delayed.clone();
    let delayed_thread = thread::spawn(move || delayed_start.start());
    let delayed_root_pid = wait_for_root_pid(&delayed_root);
    let delayed_child_pid = wait_for_child_pid(&delayed_root);
    wait_for_marker(&delayed_root, "fixture-ready-requested.flag");
    let delayed_stop = delayed.stop();
    require_state(
        &delayed_stop,
        RuntimeState::Stopped,
        "delayed readiness cancellation",
    );
    assert!(delayed_stop.retry_available);
    assert!(
        !process_is_alive(delayed_root_pid) && !process_is_alive(delayed_child_pid),
        "delayed readiness stop returned while its process tree was alive"
    );
    require_state(
        &delayed_thread.join().expect("delayed start thread"),
        RuntimeState::Stopped,
        "delayed readiness start result",
    );
    require_process_tree_stopped(
        delayed_root_pid,
        delayed_child_pid,
        "delayed readiness cancellation",
    );
    remove_fixture(delayed_root);

    let (graceful_tree_root, graceful_tree_config) =
        fixture_config(&fixture_executable, "child-ready");
    let graceful_tree = RuntimeSupervisor::new(Ok(graceful_tree_config));
    require_state(
        &graceful_tree.start(),
        RuntimeState::Ready,
        "graceful tree start",
    );
    let graceful_root_pid = graceful_tree.active_pid().expect("graceful tree root PID");
    let graceful_child_pid = wait_for_child_pid(&graceful_tree_root);
    graceful_tree.stop();
    require_process_tree_stopped(graceful_root_pid, graceful_child_pid, "graceful stop");
    remove_fixture(graceful_tree_root);

    let (forced_tree_root, forced_tree_config) = fixture_config(&fixture_executable, "child-hung");
    let forced_tree = RuntimeSupervisor::new(Ok(forced_tree_config));
    require_state(
        &forced_tree.start(),
        RuntimeState::Ready,
        "forced tree start",
    );
    let forced_root_pid = forced_tree.active_pid().expect("forced tree root PID");
    let forced_child_pid = wait_for_child_pid(&forced_tree_root);
    let stopping = forced_tree.clone();
    let stop_thread = thread::spawn(move || stopping.stop());
    let stopping_deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let snapshot = forced_tree.status();
        if snapshot.state == RuntimeState::Stopped && !snapshot.retry_available {
            break;
        }
        assert!(
            Instant::now() < stopping_deadline,
            "stop did not enter serialized state"
        );
        thread::sleep(Duration::from_millis(1));
    }
    let retry_during_stop = forced_tree.start();
    require_state(
        &retry_during_stop,
        RuntimeState::Stopped,
        "retry during stop",
    );
    assert!(!retry_during_stop.retry_available);
    stop_thread.join().expect("forced stop thread");
    require_process_tree_stopped(forced_root_pid, forced_child_pid, "forced stop");
    remove_fixture(forced_tree_root);

    let (drop_tree_root, drop_tree_config) = fixture_config(&fixture_executable, "child-ready");
    let drop_tree = RuntimeSupervisor::new(Ok(drop_tree_config));
    require_state(
        &drop_tree.start(),
        RuntimeState::Ready,
        "job close tree start",
    );
    let drop_root_pid = drop_tree.active_pid().expect("job close root PID");
    let drop_child_pid = wait_for_child_pid(&drop_tree_root);
    drop(drop_tree);
    require_process_tree_stopped(drop_root_pid, drop_child_pid, "job handle close");
    remove_fixture(drop_tree_root);

    println!(
        "{}",
        serde_json::to_string(&Report {
            ok: true,
            duplicate_start_pid_stable,
            cancelled_start_left_no_process,
            graceful_stop,
            crash_detected: true,
            restart_pid_changed,
            restart_limit,
            async_command_cancelled,
            port_zero_rejected: true,
            malformed_handshake_rejected: true,
            early_exit_classified: true,
            readiness_timeout_classified: true,
            graceful_tree_cleanup: true,
            forced_tree_cleanup: true,
            job_close_tree_cleanup: true,
            stop_retry_serialized: true,
            delayed_readiness_cleanup: true,
            generated_contract_request,
            problem_trace_preserved,
            unsafe_api_path_denied,
            incompatible_api_rejected: true,
        })
        .expect("serialize supervision report")
    );
}
