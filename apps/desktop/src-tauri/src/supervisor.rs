use std::collections::VecDeque;
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{IpAddr, Ipv4Addr, SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{Arc, Mutex, mpsc};
use std::thread;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

const EXPECTED_EXECUTABLE: &str = "research-observatory-core-x86_64-pc-windows-msvc.exe";
const EXPECTED_BUILD: &str = "0.1.0";
const MAX_ATTEMPTS: u8 = 3;
const MAX_HANDSHAKE_BYTES: usize = 4096;
const START_TIMEOUT: Duration = Duration::from_secs(10);
const STOP_TIMEOUT: Duration = Duration::from_secs(5);
const HEALTH_RETRY: Duration = Duration::from_millis(50);
const MAX_DIAGNOSTICS: usize = 64;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum RuntimeState {
    Starting,
    Ready,
    Crashed,
    Stopped,
    Incompatible,
    RecoveryRequired,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeSnapshot {
    pub state: RuntimeState,
    pub attempt: u8,
    pub retry_available: bool,
    pub diagnostic_reference: Option<&'static str>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeDiagnostic {
    pub sequence: u64,
    pub code: &'static str,
    pub stream: &'static str,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct DatabaseCompatibility {
    minimum: String,
    maximum_exclusive: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct RuntimeHandshake {
    protocol_version: String,
    build_id: String,
    pid: u32,
    host: String,
    port: u16,
    nonce: String,
    capabilities: Vec<String>,
    database_compatibility: DatabaseCompatibility,
    diagnostic_code: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct ReadinessResponse {
    schema_version: String,
    service: String,
    version: String,
    state: String,
    capabilities: Vec<String>,
    ready: bool,
}

#[derive(Clone, Debug)]
pub struct SupervisorConfig {
    executable: PathBuf,
    working_directory: PathBuf,
}

impl SupervisorConfig {
    pub fn new(executable: PathBuf) -> Result<Self, &'static str> {
        let metadata = fs::symlink_metadata(&executable).map_err(|_| "RO-CORE-NOT-PACKAGED")?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err("RO-CORE-INTEGRITY-FAILED");
        }
        if executable.file_name().and_then(|value| value.to_str()) != Some(EXPECTED_EXECUTABLE) {
            return Err("RO-CORE-INTEGRITY-FAILED");
        }
        let canonical = dunce::canonicalize(&executable).map_err(|_| "RO-CORE-INTEGRITY-FAILED")?;
        if canonical != executable {
            return Err("RO-CORE-INTEGRITY-FAILED");
        }
        let working_directory = canonical
            .parent()
            .ok_or("RO-CORE-INTEGRITY-FAILED")?
            .to_path_buf();
        Ok(Self {
            executable: canonical,
            working_directory,
        })
    }

    pub fn from_resource_root(resource_root: &Path) -> Result<Self, &'static str> {
        Self::new(resource_root.join("core-sidecar").join(EXPECTED_EXECUTABLE))
    }
}

struct RunningProcess {
    child: Child,
    stdin: ChildStdin,
    containment: ProcessTreeContainment,
}

struct SupervisorInner {
    state: RuntimeState,
    attempt: u8,
    process: Option<RunningProcess>,
    diagnostics: VecDeque<RuntimeDiagnostic>,
    sequence: u64,
}

impl SupervisorInner {
    fn snapshot(&self) -> RuntimeSnapshot {
        let diagnostic_reference = (self.state != RuntimeState::Ready)
            .then(|| self.diagnostics.back().map(|item| item.code))
            .flatten();
        RuntimeSnapshot {
            state: self.state,
            attempt: self.attempt,
            retry_available: matches!(
                self.state,
                RuntimeState::Crashed | RuntimeState::Stopped | RuntimeState::Incompatible
            ) && self.attempt < MAX_ATTEMPTS,
            diagnostic_reference,
        }
    }

    fn record(&mut self, code: &'static str, stream: &'static str) {
        self.sequence += 1;
        if self.diagnostics.len() == MAX_DIAGNOSTICS {
            self.diagnostics.pop_front();
        }
        self.diagnostics.push_back(RuntimeDiagnostic {
            sequence: self.sequence,
            code,
            stream,
        });
    }

    fn refresh(&mut self) {
        let Some(process) = self.process.as_mut() else {
            return;
        };
        match process.child.try_wait() {
            Ok(Some(status)) => {
                self.process = None;
                if status.success() && self.state == RuntimeState::Stopped {
                    self.record("RO-CORE-STOPPED", "process");
                } else {
                    self.state = RuntimeState::Crashed;
                    self.record("RO-CORE-CRASHED", "process");
                }
            }
            Ok(None) => {}
            Err(_) => {
                self.process = None;
                self.state = RuntimeState::Crashed;
                self.record("RO-CORE-STATUS-FAILED", "process");
            }
        }
    }
}

#[derive(Clone)]
pub struct RuntimeSupervisor {
    config: Result<SupervisorConfig, &'static str>,
    inner: Arc<Mutex<SupervisorInner>>,
}

impl RuntimeSupervisor {
    pub fn new(config: Result<SupervisorConfig, &'static str>) -> Self {
        let configuration_failed = config.is_err();
        let initial_state = if config.is_ok() {
            RuntimeState::Stopped
        } else {
            RuntimeState::RecoveryRequired
        };
        let mut diagnostics = VecDeque::new();
        if let Err(code) = config {
            diagnostics.push_back(RuntimeDiagnostic {
                sequence: 1,
                code,
                stream: "supervisor",
            });
        }
        Self {
            config,
            inner: Arc::new(Mutex::new(SupervisorInner {
                state: initial_state,
                attempt: 0,
                process: None,
                diagnostics,
                sequence: u64::from(configuration_failed),
            })),
        }
    }

    pub fn start(&self) -> RuntimeSnapshot {
        let config = match &self.config {
            Ok(config) => config.clone(),
            Err(_) => return self.status(),
        };
        let attempt = {
            let mut inner = self
                .inner
                .lock()
                .expect("runtime supervisor mutex poisoned");
            inner.refresh();
            if matches!(inner.state, RuntimeState::Starting | RuntimeState::Ready) {
                return inner.snapshot();
            }
            if inner.attempt >= MAX_ATTEMPTS {
                inner.state = RuntimeState::RecoveryRequired;
                inner.record("RO-CORE-RESTART-LIMIT", "supervisor");
                return inner.snapshot();
            }
            inner.attempt += 1;
            inner.state = RuntimeState::Starting;
            inner.record("RO-CORE-STARTING", "supervisor");
            inner.attempt
        };

        match launch(&config, Arc::clone(&self.inner), attempt) {
            Ok(mut process) => {
                let mut inner = self
                    .inner
                    .lock()
                    .expect("runtime supervisor mutex poisoned");
                if inner.attempt != attempt || inner.state != RuntimeState::Starting {
                    let snapshot = inner.snapshot();
                    drop(inner);
                    stop_running_process(&mut process);
                    return snapshot;
                }
                inner.process = Some(process);
                inner.state = RuntimeState::Ready;
                inner.record("RO-CORE-READY", "supervisor");
                inner.snapshot()
            }
            Err((state, code)) => {
                let mut inner = self
                    .inner
                    .lock()
                    .expect("runtime supervisor mutex poisoned");
                if inner.attempt != attempt || inner.state != RuntimeState::Starting {
                    return inner.snapshot();
                }
                inner.process = None;
                inner.state = state;
                inner.record(code, "supervisor");
                inner.snapshot()
            }
        }
    }

    pub fn status(&self) -> RuntimeSnapshot {
        let mut inner = self
            .inner
            .lock()
            .expect("runtime supervisor mutex poisoned");
        inner.refresh();
        inner.snapshot()
    }

    pub fn diagnostics(&self) -> Vec<RuntimeDiagnostic> {
        let inner = self
            .inner
            .lock()
            .expect("runtime supervisor mutex poisoned");
        inner.diagnostics.iter().cloned().collect()
    }

    /// Return the supervised root PID for integration qualification only.
    /// Renderer commands deliberately do not expose this process identity.
    pub fn active_pid(&self) -> Option<u32> {
        let mut inner = self
            .inner
            .lock()
            .expect("runtime supervisor mutex poisoned");
        inner.refresh();
        inner.process.as_ref().map(|process| process.child.id())
    }

    pub fn stop(&self) -> RuntimeSnapshot {
        let process = {
            let mut inner = self
                .inner
                .lock()
                .expect("runtime supervisor mutex poisoned");
            inner.refresh();
            inner.state = RuntimeState::Stopped;
            inner.process.take()
        };
        if let Some(mut process) = process {
            stop_running_process(&mut process);
        }
        let mut inner = self
            .inner
            .lock()
            .expect("runtime supervisor mutex poisoned");
        inner.record("RO-CORE-STOPPED", "supervisor");
        inner.snapshot()
    }
}

fn launch(
    config: &SupervisorConfig,
    inner: Arc<Mutex<SupervisorInner>>,
    attempt: u8,
) -> Result<RunningProcess, (RuntimeState, &'static str)> {
    let mut command = Command::new(&config.executable);
    command
        .arg("--supervised")
        .current_dir(&config.working_directory)
        .env_clear()
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    for name in ["SystemRoot", "WINDIR", "TEMP", "TMP"] {
        if let Some(value) = std::env::var_os(name) {
            command.env(name, value);
        }
    }
    command.env("RO_CORE_PROFILE", "local");
    command.env("RO_CORE_BIND_HOST", "127.0.0.1");
    command.env("RO_CORE_BIND_PORT", "0");
    command.env("RO_CORE_LOG_LEVEL", "INFO");
    configure_hidden_process(&mut command);

    let mut child = command
        .spawn()
        .map_err(|_| (RuntimeState::Crashed, "RO-CORE-SPAWN-FAILED"))?;
    let containment = ProcessTreeContainment::attach(&child).map_err(|code| {
        let _ = child.kill();
        let _ = child.wait();
        (RuntimeState::Crashed, code)
    })?;
    let pid = child.id();
    let stdout = child
        .stdout
        .take()
        .ok_or((RuntimeState::Crashed, "RO-CORE-HANDSHAKE-MISSING"))?;
    let stderr = child
        .stderr
        .take()
        .ok_or((RuntimeState::Crashed, "RO-CORE-LOG-PIPE-FAILED"))?;
    let stdin = child
        .stdin
        .take()
        .ok_or((RuntimeState::Crashed, "RO-CORE-CONTROL-PIPE-FAILED"))?;

    let (handshake_tx, handshake_rx) = mpsc::sync_channel(1);
    let stdout_inner = Arc::clone(&inner);
    thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        let mut first = Vec::new();
        let read = reader
            .by_ref()
            .take((MAX_HANDSHAKE_BYTES + 1) as u64)
            .read_until(b'\n', &mut first);
        let _ = handshake_tx.send(read.map(|_| first));
        drain_log(reader, stdout_inner, "stdout");
    });
    let stderr_inner = Arc::clone(&inner);
    thread::spawn(move || drain_log(BufReader::new(stderr), stderr_inner, "stderr"));

    let handshake_deadline = Instant::now() + START_TIMEOUT;
    let bytes = loop {
        ensure_attempt_active(&inner, attempt)?;
        let remaining = handshake_deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err((RuntimeState::Crashed, "RO-CORE-START-TIMEOUT"));
        }
        match handshake_rx.recv_timeout(remaining.min(Duration::from_millis(50))) {
            Ok(result) => {
                break result.map_err(|_| (RuntimeState::Crashed, "RO-CORE-HANDSHAKE-MISSING"))?;
            }
            Err(mpsc::RecvTimeoutError::Timeout) => continue,
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                return Err((RuntimeState::Crashed, "RO-CORE-HANDSHAKE-MISSING"));
            }
        }
    };
    let handshake = validate_handshake(&bytes, pid)?;
    wait_until_ready(&handshake, &inner, attempt)?;
    Ok(RunningProcess {
        child,
        stdin,
        containment,
    })
}

fn validate_handshake(
    bytes: &[u8],
    expected_pid: u32,
) -> Result<RuntimeHandshake, (RuntimeState, &'static str)> {
    if bytes.is_empty() || bytes.len() > MAX_HANDSHAKE_BYTES || !bytes.ends_with(b"\n") {
        return Err((RuntimeState::Incompatible, "RO-CORE-HANDSHAKE-INVALID"));
    }
    let handshake: RuntimeHandshake = serde_json::from_slice(bytes)
        .map_err(|_| (RuntimeState::Incompatible, "RO-CORE-HANDSHAKE-INVALID"))?;
    let nonce_valid = handshake.nonce.len() == 32
        && handshake
            .nonce
            .bytes()
            .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value));
    if handshake.protocol_version != "1.0"
        || handshake.build_id != EXPECTED_BUILD
        || handshake.pid != expected_pid
        || handshake.host != "127.0.0.1"
        || !nonce_valid
        || handshake.capabilities != ["runtime.status"]
        || handshake.database_compatibility.minimum != "0.1.0"
        || handshake.database_compatibility.maximum_exclusive != "0.2.0"
        || handshake.diagnostic_code != "RO-CORE-STARTING"
    {
        return Err((RuntimeState::Incompatible, "RO-CORE-INCOMPATIBLE"));
    }
    Ok(handshake)
}

fn ensure_attempt_active(
    inner: &Arc<Mutex<SupervisorInner>>,
    attempt: u8,
) -> Result<(), (RuntimeState, &'static str)> {
    let locked = inner.lock().expect("runtime supervisor mutex poisoned");
    if locked.attempt == attempt && locked.state == RuntimeState::Starting {
        Ok(())
    } else {
        Err((RuntimeState::Stopped, "RO-CORE-STOPPED"))
    }
}

fn wait_until_ready(
    handshake: &RuntimeHandshake,
    inner: &Arc<Mutex<SupervisorInner>>,
    attempt: u8,
) -> Result<(), (RuntimeState, &'static str)> {
    let address = SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), handshake.port);
    let deadline = Instant::now() + START_TIMEOUT;
    while Instant::now() < deadline {
        ensure_attempt_active(inner, attempt)?;
        if let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(250)) {
            let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
            let request = b"GET /readyz HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
            if stream.write_all(request).is_ok() {
                let mut response = Vec::new();
                if stream.take(65_537).read_to_end(&mut response).is_ok()
                    && response.len() <= 65_536
                    && readiness_is_compatible(&response)
                {
                    return Ok(());
                }
            }
        }
        thread::sleep(HEALTH_RETRY);
    }
    Err((RuntimeState::Crashed, "RO-CORE-START-TIMEOUT"))
}

fn stop_running_process(process: &mut RunningProcess) {
    let _ = process.stdin.write_all(b"shutdown\n");
    let _ = process.stdin.flush();
    let deadline = Instant::now() + STOP_TIMEOUT;
    loop {
        match process.child.try_wait() {
            Ok(Some(_)) => break,
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(20)),
            _ => {
                process.containment.terminate();
                let _ = process.child.wait();
                break;
            }
        }
    }
}

fn readiness_is_compatible(response: &[u8]) -> bool {
    let Some(split) = response.windows(4).position(|window| window == b"\r\n\r\n") else {
        return false;
    };
    let headers = &response[..split];
    if !headers.starts_with(b"HTTP/1.1 200 ") {
        return false;
    }
    let Ok(payload) = serde_json::from_slice::<ReadinessResponse>(&response[split + 4..]) else {
        return false;
    };
    payload.schema_version == "1.0"
        && payload.service == "research-observatory-core"
        && payload.version == EXPECTED_BUILD
        && payload.state == "ready"
        && payload.capabilities == ["runtime.status"]
        && payload.ready
}

fn drain_log<R: BufRead>(mut reader: R, inner: Arc<Mutex<SupervisorInner>>, stream: &'static str) {
    let mut line = Vec::new();
    while reader
        .by_ref()
        .take(8193)
        .read_until(b'\n', &mut line)
        .ok()
        .filter(|count| *count > 0)
        .is_some()
    {
        let code = if line.len() > 8192 {
            "RO-CORE-LOG-OVERSIZE"
        } else {
            "RO-CORE-RUNTIME-LOG"
        };
        if let Ok(mut locked) = inner.lock() {
            locked.record(code, stream);
        }
        line.clear();
    }
}

#[cfg(windows)]
fn configure_hidden_process(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    command.creation_flags(0x0800_0000);
}

#[cfg(not(windows))]
fn configure_hidden_process(_command: &mut Command) {}

#[cfg(windows)]
struct ProcessTreeContainment(windows_sys::Win32::Foundation::HANDLE);

#[cfg(windows)]
unsafe impl Send for ProcessTreeContainment {}

#[cfg(windows)]
impl ProcessTreeContainment {
    fn attach(child: &Child) -> Result<Self, &'static str> {
        use std::mem::{size_of, zeroed};
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::System::JobObjects::{
            AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
            SetInformationJobObject,
        };
        unsafe {
            let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if job.is_null() {
                return Err("RO-CORE-CONTAINMENT-FAILED");
            }
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let configured = SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                (&raw const limits).cast(),
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );
            if configured == 0 {
                windows_sys::Win32::Foundation::CloseHandle(job);
                return Err("RO-CORE-CONTAINMENT-FAILED");
            }
            let assigned = AssignProcessToJobObject(job, child.as_raw_handle().cast());
            if assigned == 0 {
                windows_sys::Win32::Foundation::CloseHandle(job);
                return Err("RO-CORE-CONTAINMENT-FAILED");
            }
            Ok(Self(job))
        }
    }

    fn terminate(&self) {
        unsafe {
            windows_sys::Win32::System::JobObjects::TerminateJobObject(self.0, 1);
        }
    }
}

#[cfg(windows)]
impl Drop for ProcessTreeContainment {
    fn drop(&mut self) {
        unsafe {
            windows_sys::Win32::Foundation::CloseHandle(self.0);
        }
    }
}

#[cfg(not(windows))]
struct ProcessTreeContainment;

#[cfg(not(windows))]
impl ProcessTreeContainment {
    fn attach(_child: &Child) -> Result<Self, &'static str> {
        Ok(Self)
    }

    fn terminate(&self) {}
}

#[cfg(test)]
mod tests {
    use super::{RuntimeState, SupervisorInner, validate_handshake};
    use std::collections::VecDeque;

    fn handshake(pid: u32) -> Vec<u8> {
        format!(
            concat!(
                "{{\"protocolVersion\":\"1.0\",\"buildId\":\"0.1.0\",\"pid\":{},",
                "\"host\":\"127.0.0.1\",\"port\":49152,",
                "\"nonce\":\"0123456789abcdef0123456789abcdef\",",
                "\"capabilities\":[\"runtime.status\"],",
                "\"databaseCompatibility\":{{\"minimum\":\"0.1.0\",",
                "\"maximumExclusive\":\"0.2.0\"}},",
                "\"diagnosticCode\":\"RO-CORE-STARTING\"}}\n"
            ),
            pid
        )
        .into_bytes()
    }

    #[test]
    fn handshake_is_exact_and_process_bound() {
        assert!(validate_handshake(&handshake(42), 42).is_ok());
        assert!(validate_handshake(&handshake(42), 43).is_err());
        let mut extra = handshake(42);
        extra.splice(
            extra.len() - 2..extra.len() - 2,
            b",\"secret\":\"hunter2\"".iter().copied(),
        );
        assert!(validate_handshake(&extra, 42).is_err());
        assert!(validate_handshake(&vec![b'x'; 4097], 42).is_err());
    }

    #[test]
    fn bounded_diagnostics_discard_oldest_without_raw_content() {
        let mut inner = SupervisorInner {
            state: RuntimeState::Stopped,
            attempt: 0,
            process: None,
            diagnostics: VecDeque::new(),
            sequence: 0,
        };
        for _ in 0..80 {
            inner.record("RO-CORE-RUNTIME-LOG", "stderr");
        }
        assert_eq!(inner.diagnostics.len(), 64);
        assert_eq!(inner.diagnostics.front().expect("diagnostic").sequence, 17);
    }
}
