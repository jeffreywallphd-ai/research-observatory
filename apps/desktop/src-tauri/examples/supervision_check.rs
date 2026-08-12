use std::path::PathBuf;
use std::thread;
use std::time::{Duration, Instant};

use research_observatory_desktop_lib::supervisor::{
    RuntimeSnapshot, RuntimeState, RuntimeSupervisor, SupervisorConfig,
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

fn main() {
    let executable = std::env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .expect("usage: supervision_check <canonical-sidecar-executable>");
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
        })
        .expect("serialize supervision report")
    );
}
