use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::{Duration, Instant};

use research_observatory_desktop_lib::supervisor::{
    CoreApiRequest, RuntimeSnapshot, RuntimeState, RuntimeSupervisor, SupervisorConfig,
};
use research_observatory_desktop_lib::support_bundle::SupportBundleManager;
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
    contract_request_performance: ContractRequestPerformance,
    problem_trace_preserved: bool,
    unsafe_api_path_denied: bool,
    incompatible_api_rejected: bool,
    support_bundle_trace_linked: bool,
    support_bundle_redacted: bool,
    support_bundle_exact_export: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ContractRequestPerformance {
    hardware: MeasurementHardware,
    fixture: &'static str,
    state: &'static str,
    repetitions_per_request: usize,
    distribution: &'static str,
    absolute_budget_ms: f64,
    regression_threshold_percent: f64,
    version_request: RequestDistribution,
    health_request: RequestDistribution,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct MeasurementHardware {
    operating_system: String,
    architecture: &'static str,
    processor: String,
    logical_cpu_count: usize,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct RequestDistribution {
    method: &'static str,
    path: &'static str,
    samples_ms: Vec<f64>,
    minimum_ms: f64,
    p50_ms: f64,
    p95_ms: f64,
    maximum_ms: f64,
    passes: bool,
    future_regression_limit_ms: f64,
}

const REQUEST_REPETITIONS: usize = 20;
const REQUEST_BUDGET_MS: f64 = 100.0;
const REGRESSION_THRESHOLD_PERCENT: f64 = 20.0;

static FIXTURE_SEQUENCE: AtomicU64 = AtomicU64::new(1);

fn rounded_milliseconds(value: f64) -> f64 {
    (value * 1_000.0).round() / 1_000.0
}

fn request_distribution(
    method: &'static str,
    path: &'static str,
    samples: Vec<f64>,
) -> RequestDistribution {
    assert_eq!(samples.len(), REQUEST_REPETITIONS);
    assert!(
        samples
            .iter()
            .all(|sample| sample.is_finite() && *sample >= 0.0)
    );
    let mut ordered = samples.clone();
    ordered.sort_by(f64::total_cmp);
    let nearest_rank = |probability: f64| {
        let rank = ((ordered.len() as f64 * probability).ceil() as usize).clamp(1, ordered.len());
        ordered[rank - 1]
    };
    let minimum = ordered[0];
    let p50 = nearest_rank(0.50);
    let p95 = nearest_rank(0.95);
    let maximum = ordered[ordered.len() - 1];
    RequestDistribution {
        method,
        path,
        samples_ms: samples.into_iter().map(rounded_milliseconds).collect(),
        minimum_ms: rounded_milliseconds(minimum),
        p50_ms: rounded_milliseconds(p50),
        p95_ms: rounded_milliseconds(p95),
        maximum_ms: rounded_milliseconds(maximum),
        passes: p95 <= REQUEST_BUDGET_MS,
        future_regression_limit_ms: rounded_milliseconds(
            (p95 * (1.0 + REGRESSION_THRESHOLD_PERCENT / 100.0)).min(REQUEST_BUDGET_MS),
        ),
    }
}

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

    let mut version_samples = Vec::with_capacity(REQUEST_REPETITIONS);
    let mut measured_version_trace = String::new();
    for _ in 0..REQUEST_REPETITIONS {
        let started = Instant::now();
        let response = tauri::async_runtime::block_on(dispatch_core_api_request(
            graceful.clone(),
            CoreApiRequest {
                method: "GET".to_owned(),
                path: "/runtime/version".to_owned(),
                body: None,
                if_match: None,
                idempotency_key: None,
            },
        ))
        .expect("measured version request");
        let elapsed = started.elapsed().as_secs_f64() * 1_000.0;
        let body: serde_json::Value =
            serde_json::from_str(&response.body).expect("measured version response JSON");
        assert!(
            response.status == 200
                && response.content_type == "application/json"
                && body["schemaVersion"] == "1.0"
                && body["service"] == "research-observatory-core"
                && body["version"] == "0.1.0"
                && body["apiVersion"] == "1.0.0"
                && body["minimumClientApiVersion"] == "1.0.0"
                && body["maximumClientApiVersionExclusive"] == "2.0.0",
            "measured version response violated the generated contract"
        );
        measured_version_trace = response.trace_id;
        version_samples.push(elapsed);
    }

    let mut health_samples = Vec::with_capacity(REQUEST_REPETITIONS);
    for _ in 0..REQUEST_REPETITIONS {
        let started = Instant::now();
        let response = tauri::async_runtime::block_on(dispatch_core_api_request(
            graceful.clone(),
            CoreApiRequest {
                method: "GET".to_owned(),
                path: "/healthz".to_owned(),
                body: None,
                if_match: None,
                idempotency_key: None,
            },
        ))
        .expect("measured health request");
        let elapsed = started.elapsed().as_secs_f64() * 1_000.0;
        let body: serde_json::Value =
            serde_json::from_str(&response.body).expect("measured health response JSON");
        assert!(
            response.status == 200
                && response.content_type == "application/json"
                && body["schemaVersion"] == "1.0"
                && body["service"] == "research-observatory-core"
                && body["version"] == "0.1.0"
                && body["state"] == "ready"
                && body["alive"] == true
                && body["capabilities"]
                    == serde_json::json!([
                        "operations.cancel",
                        "operations.events",
                        "operations.read",
                        "privacy.cache-cleanup",
                        "privacy.policy",
                        "projects.lifecycle",
                        "runtime.contract",
                        "runtime.status"
                    ]),
            "measured health response violated the generated contract"
        );
        health_samples.push(elapsed);
    }

    let contract_request_performance = ContractRequestPerformance {
        hardware: MeasurementHardware {
            operating_system: format!(
                "{} ({})",
                std::env::consts::OS,
                std::env::var("OS").unwrap_or_else(|_| "unreported".to_owned())
            ),
            architecture: std::env::consts::ARCH,
            processor: std::env::var("PROCESSOR_IDENTIFIER")
                .unwrap_or_else(|_| "unreported".to_owned()),
            logical_cpu_count: std::thread::available_parallelism()
                .map(usize::from)
                .unwrap_or(1),
        },
        fixture: "canonical authenticated PyInstaller onedir Core 0.1.0 package",
        state: "warm after strict Ready; one unmeasured version request precedes measured requests",
        repetitions_per_request: REQUEST_REPETITIONS,
        distribution: "nearest-rank p50 and p95; no measured sample discarded",
        absolute_budget_ms: REQUEST_BUDGET_MS,
        regression_threshold_percent: REGRESSION_THRESHOLD_PERCENT,
        version_request: request_distribution("GET", "/runtime/version", version_samples),
        health_request: request_distribution("GET", "/healthz", health_samples),
    };
    assert!(
        contract_request_performance.version_request.passes
            && contract_request_performance.health_request.passes,
        "post-readiness Core request performance exceeded the approved 100 ms p95 budget"
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

    let support_root = std::env::temp_dir().join(format!(
        "ro-support-supervision-{}-{}",
        std::process::id(),
        FIXTURE_SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    let support_manager = SupportBundleManager::default();
    let support_preview = support_manager
        .preview(&support_root, &graceful)
        .expect("support bundle preview");
    let support_document =
        serde_json::to_value(support_preview.bundle()).expect("serialize support bundle document");
    let support_bundle_trace_linked = support_document["recentDiagnostics"]
        .as_array()
        .expect("support diagnostics array")
        .iter()
        .any(|item| item["traceId"] == measured_version_trace);
    assert!(
        support_bundle_trace_linked,
        "support bundle did not retain the desktop action trace ID"
    );
    let support_document_text = serde_json::to_string(&support_document)
        .expect("serialize support bundle for redaction check");
    let support_bundle_redacted = !support_document_text.contains("Bearer")
        && !support_document_text.contains("authorization")
        && !support_document_text.contains("processId")
        && !support_document_text.contains("absolutePath")
        && !support_document_text.contains(
            support_root
                .to_str()
                .expect("support root path must be Unicode"),
        )
        && support_document["exclusions"]
            .as_array()
            .is_some_and(|items| items.len() == 9);
    assert!(
        support_bundle_redacted,
        "support bundle leaked excluded data"
    );

    let mut reviewed_bytes = serde_json::to_vec_pretty(support_preview.bundle())
        .expect("serialize exact reviewed support bundle");
    reviewed_bytes.push(b'\n');
    assert_eq!(reviewed_bytes.len(), support_preview.byte_length());
    assert_eq!(
        support_preview.document_json().as_bytes(),
        reviewed_bytes.as_slice(),
        "preview JSON did not equal the exact export bytes"
    );
    let support_export = support_manager
        .export(&support_root, support_preview.preview_id())
        .expect("export exact reviewed support bundle");
    let installed_bytes = fs::read(support_export.path()).expect("read exported support bundle");
    let support_bundle_exact_export = installed_bytes == reviewed_bytes
        && support_export.byte_length() == support_preview.byte_length()
        && support_export.sha256() == support_preview.sha256();
    assert!(
        support_bundle_exact_export,
        "support export differed from the reviewed bytes"
    );
    remove_fixture(support_root);

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
        "RO-CORE-INCOMPATIBLE",
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
            contract_request_performance,
            problem_trace_preserved,
            unsafe_api_path_denied,
            incompatible_api_rejected: true,
            support_bundle_trace_linked,
            support_bundle_redacted,
            support_bundle_exact_export,
        })
        .expect("serialize supervision report")
    );
}
