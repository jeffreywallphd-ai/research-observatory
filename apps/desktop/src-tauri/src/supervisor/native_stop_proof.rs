//! Private Windows Native fixture observations; queries never wait or clean up.
//! The parent gates this entire module on test + Windows + integration-harness.
use super::*;
use serde_json::{Value, json};
use std::collections::HashMap;
use std::os::windows::io::AsRawHandle;
use std::sync::OnceLock;
use windows_sys::Win32::Foundation::{
    CloseHandle, DuplicateHandle, HANDLE, WAIT_OBJECT_0, WAIT_TIMEOUT,
};
use windows_sys::Win32::System::JobObjects::{
    JOBOBJECT_BASIC_ACCOUNTING_INFORMATION, JOBOBJECT_BASIC_PROCESS_ID_LIST,
    JobObjectBasicAccountingInformation, JobObjectBasicProcessIdList, QueryInformationJobObject,
};
use windows_sys::Win32::System::Threading::{
    GetCurrentProcess, GetExitCodeProcess, GetProcessId, PROCESS_QUERY_LIMITED_INFORMATION,
    PROCESS_SYNCHRONIZE, WaitForSingleObject,
};

type Ticket = Arc<Mutex<Record>>;

fn registry() -> &'static Mutex<HashMap<usize, Ticket>> {
    static REGISTRY: OnceLock<Mutex<HashMap<usize, Ticket>>> = OnceLock::new();
    REGISTRY.get_or_init(|| Mutex::new(HashMap::new()))
}

#[derive(Clone, Copy)]
pub(super) enum Event {
    NormalEntry,
    ImmediateEntry,
    TerminateInvoked,
    DirectKillInvoked,
}

#[derive(Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub(super) struct JobSnapshot {
    accounting_query_ok: bool,
    process_list_query_ok: bool,
    active_processes: u32,
    total_processes: u32,
    total_terminated_processes: u32,
    assigned_processes: u32,
    returned_processes: u32,
    complete_process_list: bool,
    process_ids: Vec<usize>,
}

fn job_snapshot(job: HANDLE) -> JobSnapshot {
    // Fixed memory bound; an overflow/error/inconsistent list never means empty.
    const MAX_PROCESSES: usize = 4096;
    let mut accounting = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION::default();
    let accounting_ok = unsafe {
        QueryInformationJobObject(
            job,
            JobObjectBasicAccountingInformation,
            (&raw mut accounting).cast(),
            std::mem::size_of_val(&accounting) as u32,
            std::ptr::null_mut(),
        ) != 0
    };
    let mut storage = [0_usize; 2 + MAX_PROCESSES];
    let list_ok = unsafe {
        QueryInformationJobObject(
            job,
            JobObjectBasicProcessIdList,
            storage.as_mut_ptr().cast(),
            std::mem::size_of_val(&storage) as u32,
            std::ptr::null_mut(),
        ) != 0
    };
    let list = unsafe { &*storage.as_ptr().cast::<JOBOBJECT_BASIC_PROCESS_ID_LIST>() };
    let assigned = list.NumberOfAssignedProcesses;
    let returned = list.NumberOfProcessIdsInList;
    let complete = list_ok && assigned == returned && returned as usize <= MAX_PROCESSES;
    let process_ids = if complete {
        unsafe { std::slice::from_raw_parts(list.ProcessIdList.as_ptr(), returned as usize) }
            .to_vec()
    } else {
        Vec::new()
    };
    JobSnapshot {
        accounting_query_ok: accounting_ok,
        process_list_query_ok: list_ok,
        active_processes: accounting.ActiveProcesses,
        total_processes: accounting.TotalProcesses,
        total_terminated_processes: accounting.TotalTerminatedProcesses,
        assigned_processes: assigned,
        returned_processes: returned,
        complete_process_list: complete,
        process_ids,
    }
}

impl JobSnapshot {
    fn empty(&self) -> bool {
        self.accounting_query_ok
            && self.process_list_query_ok
            && self.complete_process_list
            && self.active_processes == 0
            && self.assigned_processes == 0
            && self.returned_processes == 0
            && self.process_ids.is_empty()
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(super) struct Record {
    attempt: u8,
    identity: RecoveryProcessIdentity,
    initially_alive: bool,
    normal_entries: u32,
    immediate_entries: u32,
    terminate_invocations: u32,
    direct_kill_invocations: u32,
    before_close: Option<JobSnapshot>,
    close_attempts: u32,
    close_results: u32,
    close_succeeded: bool,
}

pub(super) fn event(job: HANDLE, event: Event) {
    let ticket = registry()
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .get(&(job as usize))
        .cloned();
    if let Some(ticket) = ticket {
        let mut record = ticket.lock().unwrap_or_else(|p| p.into_inner());
        let counter = match event {
            Event::NormalEntry => &mut record.normal_entries,
            Event::ImmediateEntry => &mut record.immediate_entries,
            Event::TerminateInvoked => &mut record.terminate_invocations,
            Event::DirectKillInvoked => &mut record.direct_kill_invocations,
        };
        *counter = counter.saturating_add(1);
    }
}

// These two functions surround the ORIGINAL close, exactly once. They never
// duplicate/retain a Job handle, wait for a process, drain, or perform cleanup.
pub(super) fn before_close(job: HANDLE) -> Option<Ticket> {
    let ticket = registry()
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .get(&(job as usize))
        .cloned();
    if let Some(ticket) = &ticket {
        let first = {
            let mut record = ticket.lock().unwrap_or_else(|p| p.into_inner());
            record.close_attempts = record.close_attempts.saturating_add(1);
            record.close_attempts == 1
        };
        if first {
            let snapshot = job_snapshot(job);
            ticket
                .lock()
                .unwrap_or_else(|p| p.into_inner())
                .before_close = Some(snapshot);
        }
        // Retain the ticket until finish/Drop. Repeat hooks invalidate the
        // sequence without querying an already-closed/reused kernel handle.
    }
    ticket
}

pub(super) fn after_close(ticket: Option<Ticket>, succeeded: bool) {
    if let Some(ticket) = ticket {
        let mut record = ticket.lock().unwrap_or_else(|p| p.into_inner());
        record.close_results = record.close_results.saturating_add(1);
        record.close_succeeded = if record.close_results == 1 {
            succeeded
        } else {
            false
        };
    }
}

struct ProcessHandle(Option<HANDLE>);

impl ProcessHandle {
    fn close(&mut self) -> bool {
        self.0
            .take()
            .is_some_and(|handle| unsafe { CloseHandle(handle) != 0 })
    }
}

impl Drop for ProcessHandle {
    fn drop(&mut self) {
        let _ = self.close();
    }
}

pub(super) struct Observation {
    process: ProcessHandle,
    job_key: usize,
    ticket: Ticket,
}

impl Observation {
    pub(super) fn bind_ready(supervisor: &RuntimeSupervisor) -> Result<Self, &'static str> {
        let inner = supervisor
            .shared
            .inner
            .lock()
            .map_err(|_| "observer-inner-poisoned")?;
        if inner.state != RuntimeState::Ready || inner.launching || inner.stopping {
            return Err("observer-requires-actual-ready");
        }
        Self::bind_running(
            inner.process.as_ref().ok_or("observer-no-process")?,
            inner.attempt,
        )
    }

    fn bind_running(process: &RunningProcess, attempt: u8) -> Result<Self, &'static str> {
        let mut retained = std::ptr::null_mut();
        let duplicated = unsafe {
            DuplicateHandle(
                GetCurrentProcess(),
                process.child.as_raw_handle().cast(),
                GetCurrentProcess(),
                &raw mut retained,
                PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SYNCHRONIZE,
                0,
                0,
            ) != 0
        };
        if !duplicated || retained.is_null() {
            return Err("observer-process-retain-failed");
        }
        let process_handle = ProcessHandle(Some(retained));
        let actual_pid = unsafe { GetProcessId(retained) };
        if actual_pid == 0 || actual_pid != process.child.id() {
            return Err("observer-process-id-mismatch");
        }
        let identity = recovery_process_identity(retained, actual_pid)
            .ok_or("observer-process-identity-unknown")?;
        let alive = unsafe { WaitForSingleObject(retained, 0) } == WAIT_TIMEOUT;
        if !alive {
            return Err("observer-process-already-dead-or-unknown");
        }
        let ticket = Arc::new(Mutex::new(Record {
            attempt,
            identity,
            initially_alive: alive,
            normal_entries: 0,
            immediate_entries: 0,
            terminate_invocations: 0,
            direct_kill_invocations: 0,
            before_close: None,
            close_attempts: 0,
            close_results: 0,
            close_succeeded: false,
        }));
        let key = process.containment.0 as usize;
        let mut active = registry()
            .lock()
            .map_err(|_| "observer-registry-poisoned")?;
        if active.contains_key(&key) {
            return Err("observer-already-armed");
        }
        active.insert(key, Arc::clone(&ticket));
        Ok(Self {
            process: process_handle,
            job_key: key,
            ticket,
        })
    }

    // Persist the returned record before asserting its verdict. No wait/drain is
    // introduced; the retained process handle is independently queried with0ms.
    pub(super) fn finish(mut self) -> Value {
        let record = self.ticket.lock().unwrap_or_else(|p| p.into_inner());
        let handle = self.process.0.expect("live observer process handle");
        let wait_result = unsafe { WaitForSingleObject(handle, 0) };
        let mut exit_code = u32::MAX;
        let exit_known = unsafe { GetExitCodeProcess(handle, &raw mut exit_code) } != 0;
        let actual_pid_after = unsafe { GetProcessId(handle) };
        let identity_after = recovery_process_identity(handle, actual_pid_after);
        let identity_equal = identity_after.as_ref() == Some(&record.identity);
        let observer_handle_closed = self.process.close();
        let normal = record.initially_alive
            && record.normal_entries == 1
            && record.immediate_entries == 0
            && record.terminate_invocations == 0
            && record.direct_kill_invocations == 0
            && record.close_attempts == 1
            && record.close_results == 1
            && record.close_succeeded
            && record.before_close.as_ref().is_some_and(JobSnapshot::empty)
            && record
                .before_close
                .as_ref()
                .is_some_and(|job| job.total_terminated_processes == 0)
            && wait_result == WAIT_OBJECT_0
            && exit_known
            && exit_code == 0
            && identity_equal
            && observer_handle_closed;
        json!({
            "kind":"actual-native-inner-core-stop-observation",
            "record":*record,
            "waitResult":wait_result,"exitCodeKnown":exit_known,"exitCode":exit_code,
            "identityAfter":identity_after,"identityEqual":identity_equal,
            "observerHandleClosed":observer_handle_closed,"coreNormalContainedDrain":normal,
            "allOwnedRoleDrain":"requires-separate-actual-start-finish-observation",
            "limits":"Test-only queries add instrumentation overhead. No observer wait/kill/Job retention. This verdict alone cannot establish breakaway roles or all-owned drain."
        })
    }
}

impl Drop for Observation {
    fn drop(&mut self) {
        let mut active = registry().lock().unwrap_or_else(|p| p.into_inner());
        if active
            .get(&self.job_key)
            .is_some_and(|ticket| Arc::ptr_eq(ticket, &self.ticket))
        {
            active.remove(&self.job_key);
        }
        // ProcessHandle performs emergency handle release only; never kills.
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const CHILD: &str = "supervisor::native_stop_proof::tests::calibration_child";

    #[test]
    fn calibration_child() {
        let Ok(mode) = std::env::var("RO_NATIVE_STOP_CALIBRATION") else {
            return;
        };
        if mode == "hung" {
            thread::sleep(Duration::from_secs(60));
            return;
        }
        if mode == "contained-child" {
            // Deliberately live child inherited into the original Core Job.
            // Dropping Child does not stop it; the existing last Job close will.
            let inherited = Command::new(std::env::current_exe().unwrap())
                .args(["--exact", CHILD, "--nocapture"])
                .env("RO_NATIVE_STOP_CALIBRATION", "hung")
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap();
            drop(inherited);
        }
        let input = std::io::stdin();
        let mut line = String::new();
        input.read_line(&mut line).unwrap();
        assert_eq!(line, "shutdown\n");
        if mode == "nonzero" {
            std::process::exit(7);
        }
    }

    fn process(mode: &str) -> RunningProcess {
        let mut command = Command::new(std::env::current_exe().unwrap());
        command
            .args(["--exact", CHILD, "--nocapture"])
            .env("RO_NATIVE_STOP_CALIBRATION", mode)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        configure_hidden_process(&mut command);
        let mut child = command.spawn().unwrap();
        let stdin = child.stdin.take().unwrap();
        let containment = ProcessTreeContainment::attach_and_resume(&child).unwrap();
        RunningProcess {
            child,
            stdin: recovery_control_writer(stdin),
            containment,
            capability_token: CapabilityToken::generate().unwrap(),
            cancellation: Arc::new(AtomicBool::new(false)),
            physically_closed: Arc::new(AtomicBool::new(false)),
            port: 0,
        }
    }

    fn stopped(mode: &str, immediate: bool, late_force: bool) -> Value {
        let mut process = process(mode);
        let observation = Observation::bind_running(&process, 1).unwrap();
        if immediate {
            assert!(stop_running_process_immediately(&mut process));
        } else {
            assert!(stop_running_process(&mut process, &AtomicBool::new(false)));
        }
        if late_force {
            process.containment.terminate();
        }
        drop(process);
        observation.finish()
    }

    #[test]
    fn actual_normal_exit_and_original_preclose_job_are_required() {
        let normal = stopped("normal", false, false);
        assert_eq!(normal["coreNormalContainedDrain"], true, "{normal}");
        assert_eq!(normal["record"]["beforeClose"]["activeProcesses"], 0);
        assert_eq!(normal["record"]["beforeClose"]["completeProcessList"], true);
        assert_eq!(normal["exitCode"], 0);
        assert_eq!(normal["observerHandleClosed"], true);

        let nonzero = stopped("nonzero", false, false);
        assert_eq!(nonzero["exitCode"], 7);
        assert_eq!(nonzero["coreNormalContainedDrain"], false);

        let child_live = stopped("contained-child", false, false);
        assert_eq!(child_live["exitCode"], 0);
        assert!(
            child_live["record"]["beforeClose"]["activeProcesses"]
                .as_u64()
                .unwrap()
                > 0
        );
        assert_eq!(child_live["record"]["closeSucceeded"], true);
        assert_eq!(child_live["coreNormalContainedDrain"], false);

        let late_force = stopped("normal", false, true);
        assert_eq!(late_force["exitCode"], 0);
        assert_eq!(late_force["record"]["terminateInvocations"], 1);
        assert_eq!(late_force["coreNormalContainedDrain"], false);
    }

    #[test]
    fn actual_five_second_fallback_and_security_force_deny_normal_proof() {
        let started = Instant::now();
        let hung = stopped("hung", false, false);
        assert!(started.elapsed() >= STOP_TIMEOUT);
        assert_eq!(hung["record"]["terminateInvocations"], 1);
        assert_eq!(hung["coreNormalContainedDrain"], false);
        let security = stopped("hung", true, false);
        assert_eq!(security["record"]["immediateEntries"], 1);
        assert_eq!(security["record"]["directKillInvocations"], 1);
        assert_eq!(security["coreNormalContainedDrain"], false);
    }

    #[test]
    fn actual_wrong_object_query_dead_binding_and_missing_close_fail_closed() {
        let mut process = process("normal");
        // This is an actual kernel query against a retained process object,
        // not deliberate reuse/double-close of the original Job handle.
        let unknown = job_snapshot(process.child.as_raw_handle().cast());
        assert!(!unknown.accounting_query_ok && !unknown.empty());
        let observation = Observation::bind_running(&process, 1).unwrap();
        assert!(Observation::bind_running(&process, 1).is_err());
        assert!(stop_running_process(&mut process, &AtomicBool::new(false)));
        assert!(Observation::bind_running(&process, 1).is_err());
        let missing_close = observation.finish();
        assert_eq!(missing_close["coreNormalContainedDrain"], false);
        assert_eq!(missing_close["record"]["closeAttempts"], 0);
        drop(process);
    }

    #[test]
    fn synthetic_duplicate_hook_replay_denies_without_actual_double_close() {
        let mut process = process("normal");
        let observation = Observation::bind_running(&process, 1).unwrap();
        let closed_job_key = process.containment.0;
        assert!(stop_running_process(&mut process, &AtomicBool::new(false)));
        drop(process); // The ONE actual original CloseHandle occurs here.
        // Synthetic observer-protocol replay only. before_close recognizes its
        // tombstone and performs no kernel query; no second CloseHandle runs.
        let replay = before_close(closed_job_key);
        assert!(replay.is_some());
        after_close(replay, false);
        let receipt = observation.finish();
        assert_eq!(receipt["record"]["closeAttempts"], 2);
        assert_eq!(receipt["record"]["closeResults"], 2);
        assert_eq!(receipt["coreNormalContainedDrain"], false);
    }
}
