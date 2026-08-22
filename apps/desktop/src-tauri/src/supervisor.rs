use std::collections::VecDeque;
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{IpAddr, Ipv4Addr, SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex, Weak, mpsc};
use std::thread;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

const EXPECTED_EXECUTABLE: &str = "research-observatory-core-x86_64-pc-windows-msvc.exe";
const EXPECTED_BUILD: &str = "0.1.0";
const CORE_API_CLIENT_VERSION: &str = "1.0.0";
const MAX_ATTEMPTS: u8 = 3;
const MAX_HANDSHAKE_BYTES: usize = 4096;
const START_TIMEOUT: Duration = Duration::from_secs(10);
const STOP_TIMEOUT: Duration = Duration::from_secs(5);
const HEALTH_RETRY: Duration = Duration::from_millis(50);
const MAX_DIAGNOSTICS: usize = 64;
const CAPABILITY_TOKEN_BYTES: usize = 32;

struct CapabilityToken([u8; CAPABILITY_TOKEN_BYTES]);

impl CapabilityToken {
    fn generate() -> Result<Self, &'static str> {
        let mut bytes = [0_u8; CAPABILITY_TOKEN_BYTES];
        fill_secure_random(&mut bytes)?;
        Ok(Self(bytes))
    }

    fn append_hex(&self, target: &mut Vec<u8>) {
        append_hex(&self.0, target);
    }

    fn duplicate_for_request(&self) -> Self {
        Self(self.0)
    }
}

impl Drop for CapabilityToken {
    fn drop(&mut self) {
        zeroize_bytes(&mut self.0);
    }
}

fn zeroize_bytes(target: &mut [u8]) {
    for value in target {
        unsafe { std::ptr::write_volatile(value, 0) };
    }
}

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
    pub trace_id: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeResourceUsage {
    pub process_running: bool,
    pub working_set_bytes: Option<u64>,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CoreApiRequest {
    pub method: String,
    pub path: String,
    pub body: Option<String>,
    pub if_match: Option<String>,
    pub idempotency_key: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CoreApiResponse {
    pub status: u16,
    pub content_type: String,
    pub trace_id: String,
    pub etag: Option<String>,
    pub body: String,
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

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct VersionResponse {
    schema_version: String,
    service: String,
    version: String,
    api_version: String,
    minimum_client_api_version: String,
    maximum_client_api_version_exclusive: String,
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
    capability_token: CapabilityToken,
    cancellation: Arc<AtomicBool>,
    port: u16,
}

struct SupervisorInner {
    state: RuntimeState,
    state_diagnostic: Option<&'static str>,
    attempt: u8,
    process: Option<RunningProcess>,
    launching: bool,
    stopping: bool,
    diagnostics: VecDeque<RuntimeDiagnostic>,
    sequence: u64,
}

impl SupervisorInner {
    fn snapshot(&self) -> RuntimeSnapshot {
        RuntimeSnapshot {
            state: self.state,
            attempt: self.attempt,
            retry_available: matches!(
                self.state,
                RuntimeState::Crashed | RuntimeState::Stopped | RuntimeState::Incompatible
            ) && self.attempt < MAX_ATTEMPTS
                && !self.launching
                && !self.stopping,
            diagnostic_reference: self.state_diagnostic,
        }
    }

    fn transition(
        &mut self,
        state: RuntimeState,
        diagnostic: Option<&'static str>,
        stream: &'static str,
    ) {
        self.state = state;
        self.state_diagnostic = diagnostic;
        if let Some(code) = diagnostic {
            self.record(code, stream, None);
        }
    }

    fn record(&mut self, code: &'static str, stream: &'static str, trace_id: Option<String>) {
        self.sequence += 1;
        if self.diagnostics.len() == MAX_DIAGNOSTICS {
            self.diagnostics.pop_front();
        }
        self.diagnostics.push_back(RuntimeDiagnostic {
            sequence: self.sequence,
            code,
            stream,
            trace_id,
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
                    self.transition(RuntimeState::Stopped, Some("RO-CORE-STOPPED"), "process");
                } else {
                    self.transition(RuntimeState::Crashed, Some("RO-CORE-CRASHED"), "process");
                }
            }
            Ok(None) => {}
            Err(_) => {
                self.process = None;
                self.transition(
                    RuntimeState::Crashed,
                    Some("RO-CORE-STATUS-FAILED"),
                    "process",
                );
            }
        }
    }
}

struct SupervisorShared {
    inner: Mutex<SupervisorInner>,
    lifecycle: Condvar,
}

#[derive(Clone)]
pub struct RuntimeSupervisor {
    config: Result<SupervisorConfig, &'static str>,
    shared: Arc<SupervisorShared>,
}

impl RuntimeSupervisor {
    pub fn new(config: Result<SupervisorConfig, &'static str>) -> Self {
        let configuration_failed = config.is_err();
        let initial_diagnostic = match &config {
            Ok(_) => "RO-CORE-STOPPED",
            Err(code) => code,
        };
        let initial_state = if config.is_ok() {
            RuntimeState::Stopped
        } else {
            RuntimeState::RecoveryRequired
        };
        let mut diagnostics = VecDeque::new();
        if let Err(code) = &config {
            diagnostics.push_back(RuntimeDiagnostic {
                sequence: 1,
                code,
                stream: "supervisor",
                trace_id: None,
            });
        }
        Self {
            config,
            shared: Arc::new(SupervisorShared {
                inner: Mutex::new(SupervisorInner {
                    state: initial_state,
                    state_diagnostic: Some(initial_diagnostic),
                    attempt: 0,
                    process: None,
                    launching: false,
                    stopping: false,
                    diagnostics,
                    sequence: u64::from(configuration_failed),
                }),
                lifecycle: Condvar::new(),
            }),
        }
    }

    pub fn start(&self) -> RuntimeSnapshot {
        let config = match &self.config {
            Ok(config) => config.clone(),
            Err(_) => return self.status(),
        };
        let attempt = {
            let mut inner = self
                .shared
                .inner
                .lock()
                .expect("runtime supervisor mutex poisoned");
            inner.refresh();
            if inner.stopping
                || inner.launching
                || matches!(inner.state, RuntimeState::Starting | RuntimeState::Ready)
            {
                return inner.snapshot();
            }
            if inner.attempt >= MAX_ATTEMPTS {
                inner.transition(
                    RuntimeState::RecoveryRequired,
                    Some("RO-CORE-RESTART-LIMIT"),
                    "supervisor",
                );
                return inner.snapshot();
            }
            inner.attempt += 1;
            inner.launching = true;
            inner.transition(
                RuntimeState::Starting,
                Some("RO-CORE-STARTING"),
                "supervisor",
            );
            inner.attempt
        };

        match launch(&config, Arc::clone(&self.shared), attempt) {
            Ok(mut process) => {
                let mut inner = self
                    .shared
                    .inner
                    .lock()
                    .expect("runtime supervisor mutex poisoned");
                if inner.attempt != attempt || inner.state != RuntimeState::Starting {
                    drop(inner);
                    stop_running_process(&mut process);
                    let mut inner = self
                        .shared
                        .inner
                        .lock()
                        .expect("runtime supervisor mutex poisoned");
                    inner.launching = false;
                    self.shared.lifecycle.notify_all();
                    let snapshot = inner.snapshot();
                    return snapshot;
                }
                inner.process = Some(process);
                inner.transition(RuntimeState::Ready, None, "supervisor");
                inner.record("RO-CORE-READY", "supervisor", None);
                inner.launching = false;
                self.shared.lifecycle.notify_all();
                inner.snapshot()
            }
            Err((state, code)) => {
                let mut inner = self
                    .shared
                    .inner
                    .lock()
                    .expect("runtime supervisor mutex poisoned");
                inner.launching = false;
                self.shared.lifecycle.notify_all();
                if inner.attempt != attempt || inner.state != RuntimeState::Starting {
                    return inner.snapshot();
                }
                inner.process = None;
                inner.transition(state, Some(code), "supervisor");
                inner.snapshot()
            }
        }
    }

    pub fn status(&self) -> RuntimeSnapshot {
        let mut inner = self
            .shared
            .inner
            .lock()
            .expect("runtime supervisor mutex poisoned");
        inner.refresh();
        inner.snapshot()
    }

    pub fn diagnostics(&self) -> Vec<RuntimeDiagnostic> {
        let inner = self
            .shared
            .inner
            .lock()
            .expect("runtime supervisor mutex poisoned");
        inner.diagnostics.iter().cloned().collect()
    }

    pub fn resource_usage(&self) -> RuntimeResourceUsage {
        let mut inner = self
            .shared
            .inner
            .lock()
            .expect("runtime supervisor mutex poisoned");
        inner.refresh();
        let Some(process) = inner.process.as_ref() else {
            return RuntimeResourceUsage {
                process_running: false,
                working_set_bytes: None,
            };
        };
        RuntimeResourceUsage {
            process_running: true,
            working_set_bytes: process_working_set_bytes(process.child.id()),
        }
    }

    pub fn api_request(&self, request: &CoreApiRequest) -> Result<CoreApiResponse, &'static str> {
        validate_api_request(request)?;
        let (port, capability_token, cancellation, attempt) = {
            let mut inner = self
                .shared
                .inner
                .lock()
                .expect("runtime supervisor mutex poisoned");
            inner.refresh();
            if inner.state != RuntimeState::Ready || inner.stopping || inner.launching {
                return Err("RO-CORE-API-UNAVAILABLE");
            }
            let process = inner.process.as_ref().ok_or("RO-CORE-API-UNAVAILABLE")?;
            (
                process.port,
                process.capability_token.duplicate_for_request(),
                Arc::clone(&process.cancellation),
                inner.attempt,
            )
        };
        let response = authenticated_api_request_with_cancellation(
            port,
            &capability_token,
            request,
            Some(cancellation.as_ref()),
        );
        let mut inner = self
            .shared
            .inner
            .lock()
            .expect("runtime supervisor mutex poisoned");
        inner.refresh();
        if cancellation.load(Ordering::Acquire)
            || inner.attempt != attempt
            || inner.state != RuntimeState::Ready
            || inner.stopping
            || inner.launching
            || inner.process.as_ref().map(|process| process.port) != Some(port)
        {
            return Err("RO-CORE-API-CANCELLED");
        }
        if let Ok(response) = &response {
            inner.record(
                "RO-CORE-API-REQUEST-COMPLETE",
                "api",
                Some(response.trace_id.clone()),
            );
        }
        response
    }

    /// Return the supervised root PID for integration qualification only.
    /// Renderer commands deliberately do not expose this process identity.
    pub fn active_pid(&self) -> Option<u32> {
        let mut inner = self
            .shared
            .inner
            .lock()
            .expect("runtime supervisor mutex poisoned");
        inner.refresh();
        inner.process.as_ref().map(|process| process.child.id())
    }

    pub fn stop(&self) -> RuntimeSnapshot {
        self.stop_with_policy(false)
    }

    pub fn stop_for_application_lock(&self) -> RuntimeSnapshot {
        self.stop_with_policy(true)
    }

    fn stop_with_policy(&self, immediate: bool) -> RuntimeSnapshot {
        if self.config.is_err() {
            return self.status();
        }
        let mut inner = self
            .shared
            .inner
            .lock()
            .expect("runtime supervisor mutex poisoned");
        inner.refresh();
        if inner.stopping {
            while inner.stopping {
                inner = self
                    .shared
                    .lifecycle
                    .wait(inner)
                    .expect("runtime supervisor mutex poisoned");
            }
            return inner.snapshot();
        }
        inner.stopping = true;
        inner.transition(RuntimeState::Stopped, Some("RO-CORE-STOPPED"), "supervisor");
        while inner.launching {
            inner = self
                .shared
                .lifecycle
                .wait(inner)
                .expect("runtime supervisor mutex poisoned");
        }
        if let Some(process) = inner.process.as_ref() {
            process.cancellation.store(true, Ordering::Release);
        }
        let process = inner.process.take();
        drop(inner);
        if let Some(mut process) = process {
            if immediate {
                stop_running_process_immediately(&mut process);
            } else {
                stop_running_process(&mut process);
            }
        }
        let mut inner = self
            .shared
            .inner
            .lock()
            .expect("runtime supervisor mutex poisoned");
        inner.stopping = false;
        self.shared.lifecycle.notify_all();
        inner.snapshot()
    }
}

fn launch(
    config: &SupervisorConfig,
    shared: Arc<SupervisorShared>,
    attempt: u8,
) -> Result<RunningProcess, (RuntimeState, &'static str)> {
    let capability_token =
        CapabilityToken::generate().map_err(|code| (RuntimeState::Crashed, code))?;
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
    let mut stdin = child
        .stdin
        .take()
        .ok_or((RuntimeState::Crashed, "RO-CORE-CONTROL-PIPE-FAILED"))?;
    let mut authentication = Vec::with_capacity(70);
    authentication.extend_from_slice(b"auth ");
    capability_token.append_hex(&mut authentication);
    authentication.push(b'\n');
    let authentication_written = stdin
        .write_all(&authentication)
        .and_then(|_| stdin.flush())
        .is_ok();
    zeroize_bytes(&mut authentication);
    if !authentication_written {
        let _ = child.kill();
        let _ = child.wait();
        return Err((RuntimeState::Crashed, "RO-CORE-AUTH-PIPE-FAILED"));
    }
    let containment = ProcessTreeContainment::attach_and_resume(&child).map_err(|code| {
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
    let (handshake_tx, handshake_rx) = mpsc::sync_channel(1);
    let stdout_inner = Arc::downgrade(&shared);
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
    let stderr_inner = Arc::downgrade(&shared);
    thread::spawn(move || drain_log(BufReader::new(stderr), stderr_inner, "stderr"));

    let startup = (|| {
        let handshake_deadline = Instant::now() + START_TIMEOUT;
        let bytes = loop {
            ensure_attempt_active(&shared, attempt)?;
            let remaining = handshake_deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                return Err((RuntimeState::Crashed, "RO-CORE-START-TIMEOUT"));
            }
            match handshake_rx.recv_timeout(remaining.min(Duration::from_millis(50))) {
                Ok(result) => {
                    break result
                        .map_err(|_| (RuntimeState::Crashed, "RO-CORE-HANDSHAKE-MISSING"))?;
                }
                Err(mpsc::RecvTimeoutError::Timeout) => continue,
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    return Err((RuntimeState::Crashed, "RO-CORE-HANDSHAKE-MISSING"));
                }
            }
        };
        let handshake = validate_handshake(&bytes, pid)?;
        wait_until_ready(&handshake, &capability_token, &mut child, &shared, attempt)?;
        verify_core_api_contract(handshake.port, &capability_token)?;
        ensure_attempt_active(&shared, attempt)?;
        Ok(handshake.port)
    })();
    let port = match startup {
        Ok(port) => port,
        Err(error) => {
            containment.terminate();
            let _ = child.wait();
            return Err(error);
        }
    };
    Ok(RunningProcess {
        child,
        stdin,
        containment,
        capability_token,
        cancellation: Arc::new(AtomicBool::new(false)),
        port,
    })
}

fn append_hex(bytes: &[u8], target: &mut Vec<u8>) {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    for value in bytes {
        target.push(HEX[usize::from(value >> 4)]);
        target.push(HEX[usize::from(value & 0x0f)]);
    }
}

fn canonical_operation_id(value: &str) -> bool {
    let Some(rest) = value.strip_prefix("op-") else {
        return false;
    };
    (1..=63).contains(&rest.len())
        && rest
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
        && !rest.starts_with('-')
        && !rest.ends_with('-')
}

fn canonical_unsigned(value: &str, minimum: u64, maximum: u64) -> bool {
    !value.is_empty()
        && value.bytes().all(|byte| byte.is_ascii_digit())
        && (value == "0" || !value.starts_with('0'))
        && value
            .parse::<u64>()
            .is_ok_and(|number| (minimum..=maximum).contains(&number))
}

fn bounded_project_text(value: &str, minimum: usize, maximum: usize) -> bool {
    (minimum..=maximum).contains(&value.len())
        && !value.chars().any(|character| character.is_control())
}

fn canonical_project_root(value: &str) -> bool {
    if !bounded_project_text(value, 1, 4096) {
        return false;
    }
    let normalized = value.replace('\\', "/");
    let absolute = normalized.starts_with('/')
        || (normalized.len() >= 3
            && normalized.as_bytes()[0].is_ascii_alphabetic()
            && normalized.as_bytes()[1] == b':'
            && normalized.as_bytes()[2] == b'/');
    absolute && normalized.split('/').all(|part| part != "..")
}

fn exact_json_strings(
    body: &str,
    expected: &[&str],
) -> Option<serde_json::Map<String, serde_json::Value>> {
    if body.is_empty() || body.len() > 16_384 {
        return None;
    }
    let value = serde_json::from_str::<serde_json::Value>(body).ok()?;
    let object = value.as_object()?;
    if object.len() != expected.len()
        || !expected
            .iter()
            .all(|key| object.get(*key).is_some_and(serde_json::Value::is_string))
    {
        return None;
    }
    Some(object.clone())
}

fn validate_project_api_request(path: &str, body: &str) -> bool {
    if path == "/projects" {
        let Some(value) = exact_json_strings(
            body,
            &[
                "parentDirectory",
                "directoryName",
                "displayName",
                "templateId",
            ],
        ) else {
            return false;
        };
        let parent = value["parentDirectory"].as_str().unwrap_or_default();
        let directory = value["directoryName"].as_str().unwrap_or_default();
        let display = value["displayName"].as_str().unwrap_or_default();
        let template = value["templateId"].as_str().unwrap_or_default();
        return canonical_project_root(parent)
            && (1..=64).contains(&directory.len())
            && directory
                .bytes()
                .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
            && directory
                .bytes()
                .next()
                .is_some_and(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit())
            && directory
                .bytes()
                .last()
                .is_some_and(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit())
            && bounded_project_text(display, 1, 120)
            && (1..=120).contains(&template.len())
            && template.bytes().all(|byte| {
                byte.is_ascii_lowercase() || byte.is_ascii_digit() || b".-".contains(&byte)
            })
            && template
                .bytes()
                .next()
                .is_some_and(|byte| byte.is_ascii_lowercase());
    }
    if matches!(
        path,
        "/projects/open" | "/projects/close" | "/projects/archive" | "/projects/restore"
    ) {
        return exact_json_strings(body, &["root"])
            .and_then(|value| value["root"].as_str().map(canonical_project_root))
            .unwrap_or(false);
    }
    if path == "/projects/delete" {
        let Some(value) = exact_json_strings(body, &["root", "confirmation"]) else {
            return false;
        };
        let confirmation = value["confirmation"].as_str().unwrap_or_default();
        return canonical_project_root(value["root"].as_str().unwrap_or_default())
            && confirmation
                .strip_prefix("delete:")
                .is_some_and(|identity| {
                    identity.len() == 36
                        && identity
                            .bytes()
                            .all(|byte| byte.is_ascii_hexdigit() || byte == b'-')
                });
    }
    if matches!(
        path,
        "/projects/privacy" | "/projects/privacy/cache/preview"
    ) {
        return exact_json_strings(body, &["root"])
            .and_then(|value| value["root"].as_str().map(canonical_project_root))
            .unwrap_or(false);
    }
    if path == "/projects/privacy/cache/clear" {
        let Some(value) = exact_json_strings(body, &["root", "previewToken", "confirmation"])
        else {
            return false;
        };
        let token = value["previewToken"].as_str().unwrap_or_default();
        return canonical_project_root(value["root"].as_str().unwrap_or_default())
            && token.len() == 32
            && token
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            && value["confirmation"].as_str() == Some(format!("clear-cache:{token}").as_str());
    }
    if path == "/projects/privacy/update" {
        let Ok(value) = serde_json::from_str::<serde_json::Value>(body) else {
            return false;
        };
        let Some(object) = value.as_object() else {
            return false;
        };
        let expected = [
            "root",
            "expectedRevision",
            "networkPolicy",
            "remoteModelApproval",
            "telemetryMode",
            "logRetentionDays",
            "documentRetention",
            "cacheRetentionDays",
            "egressConsentToken",
        ];
        if body.is_empty()
            || body.len() > 16_384
            || object.len() != expected.len()
            || !expected.iter().all(|key| object.contains_key(*key))
        {
            return false;
        }
        let Some(root) = object["root"].as_str() else {
            return false;
        };
        let Some(revision) = object["expectedRevision"].as_u64() else {
            return false;
        };
        let Some(log_days) = object["logRetentionDays"].as_u64() else {
            return false;
        };
        let Some(cache_days) = object["cacheRetentionDays"].as_u64() else {
            return false;
        };
        let Some(network) = object["networkPolicy"].as_str() else {
            return false;
        };
        let consent = object["egressConsentToken"].as_str();
        return canonical_project_root(root)
            && revision <= 9_007_199_254_740_991
            && (1..=90).contains(&log_days)
            && (1..=90).contains(&cache_days)
            && matches!(network, "offline" | "metadata-only" | "approved-providers")
            && object["remoteModelApproval"].as_str() == Some("preview-every-task")
            && matches!(
                object["telemetryMode"].as_str(),
                Some("off" | "local-diagnostics-only")
            )
            && matches!(
                object["documentRetention"].as_str(),
                Some("project-lifetime" | "review-after-90-days" | "review-after-365-days")
            )
            && ((network == "offline" && object["egressConsentToken"].is_null())
                || (network != "offline" && consent == Some("acknowledge-egress-preview-v1")));
    }
    false
}

fn validate_api_request(request: &CoreApiRequest) -> Result<(), &'static str> {
    if request.path.len() > 2048 || !request.path.is_ascii() {
        return Err("RO-CORE-API-REQUEST-INVALID");
    }
    if request
        .path
        .bytes()
        .any(|byte| !(byte.is_ascii_alphanumeric() || b"/-?&=.".contains(&byte)))
    {
        return Err("RO-CORE-API-REQUEST-INVALID");
    }
    if request.method == "GET" && matches!(request.path.as_str(), "/runtime/version" | "/healthz") {
        return if request.body.is_none()
            && request.if_match.is_none()
            && request.idempotency_key.is_none()
        {
            Ok(())
        } else {
            Err("RO-CORE-API-REQUEST-INVALID")
        };
    }
    if request.method == "GET" {
        if request.body.is_some() || request.if_match.is_some() || request.idempotency_key.is_some()
        {
            return Err("RO-CORE-API-REQUEST-INVALID");
        }
        if let Some(query) = request.path.strip_prefix("/runtime/operations?limit=") {
            if let Some((limit, after)) = query.split_once("&after=") {
                if canonical_unsigned(limit, 1, 100) && canonical_operation_id(after) {
                    return Ok(());
                }
            } else if canonical_unsigned(query, 1, 100) {
                return Ok(());
            }
        }
        if let Some(rest) = request.path.strip_prefix("/runtime/operations/") {
            if let Some((operation_id, sequence)) = rest.split_once("/events?afterSequence=") {
                if canonical_operation_id(operation_id)
                    && canonical_unsigned(sequence, 0, 9_007_199_254_740_991)
                {
                    return Ok(());
                }
            } else if canonical_operation_id(rest) {
                return Ok(());
            }
        }
    }
    if request.method == "POST"
        && request.if_match.is_none()
        && request.idempotency_key.is_none()
        && request
            .body
            .as_deref()
            .is_some_and(|body| validate_project_api_request(&request.path, body))
    {
        return Ok(());
    }
    if request.method == "POST"
        && request
            .path
            .strip_prefix("/runtime/operations/")
            .and_then(|value| value.strip_suffix("/cancel"))
            .is_some_and(canonical_operation_id)
        && request
            .if_match
            .as_deref()
            .is_some_and(canonical_operation_etag)
        && request.idempotency_key.as_deref().is_some_and(|value| {
            value.len() == 32
                && value
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        })
        && request.body.is_none()
    {
        return Ok(());
    }
    Err("RO-CORE-API-REQUEST-INVALID")
}

fn canonical_operation_etag(value: &str) -> bool {
    let Some(inner) = value
        .strip_prefix('"')
        .and_then(|item| item.strip_suffix('"'))
    else {
        return false;
    };
    let Some((operation_id, sequence)) = inner.rsplit_once('-') else {
        return false;
    };
    canonical_operation_id(operation_id) && canonical_unsigned(sequence, 0, u64::MAX)
}

fn authenticated_api_request(
    port: u16,
    capability_token: &CapabilityToken,
    api_request: &CoreApiRequest,
) -> Result<CoreApiResponse, &'static str> {
    authenticated_api_request_with_cancellation(port, capability_token, api_request, None)
}

fn authenticated_api_request_with_cancellation(
    port: u16,
    capability_token: &CapabilityToken,
    api_request: &CoreApiRequest,
    cancellation: Option<&AtomicBool>,
) -> Result<CoreApiResponse, &'static str> {
    if cancellation.is_some_and(|flag| flag.load(Ordering::Acquire)) {
        return Err("RO-CORE-API-CANCELLED");
    }
    let mut trace_bytes = [0_u8; 16];
    fill_secure_random(&mut trace_bytes).map_err(|_| "RO-CORE-TRACE-RANDOM-FAILED")?;
    let mut trace = Vec::with_capacity(32);
    append_hex(&trace_bytes, &mut trace);
    zeroize_bytes(&mut trace_bytes);
    let trace_id = String::from_utf8(trace.clone()).map_err(|_| "RO-CORE-TRACE-RANDOM-FAILED")?;

    let address = SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), port);
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_secs(1))
        .map_err(|_| "RO-CORE-API-UNAVAILABLE")?;
    stream
        .set_read_timeout(Some(Duration::from_millis(50)))
        .map_err(|_| "RO-CORE-API-UNAVAILABLE")?;
    stream
        .set_write_timeout(Some(Duration::from_secs(1)))
        .map_err(|_| "RO-CORE-API-UNAVAILABLE")?;
    let mut wire = Vec::with_capacity(512);
    wire.extend_from_slice(api_request.method.as_bytes());
    wire.push(b' ');
    wire.extend_from_slice(api_request.path.as_bytes());
    wire.extend_from_slice(b" HTTP/1.1\r\nHost: 127.0.0.1:");
    wire.extend_from_slice(port.to_string().as_bytes());
    wire.extend_from_slice(b"\r\nAuthorization: Bearer ");
    capability_token.append_hex(&mut wire);
    wire.extend_from_slice(b"\r\nX-Trace-Id: ");
    wire.extend_from_slice(&trace);
    if let Some(if_match) = &api_request.if_match {
        wire.extend_from_slice(b"\r\nIf-Match: ");
        wire.extend_from_slice(if_match.as_bytes());
    }
    if let Some(idempotency_key) = &api_request.idempotency_key {
        wire.extend_from_slice(b"\r\nIdempotency-Key: ");
        wire.extend_from_slice(idempotency_key.as_bytes());
    }
    wire.extend_from_slice(b"\r\nAccept: application/json, text/event-stream");
    if api_request.body.is_some() {
        wire.extend_from_slice(b"\r\nContent-Type: application/json");
    }
    wire.extend_from_slice(b"\r\nContent-Length: ");
    wire.extend_from_slice(
        api_request
            .body
            .as_ref()
            .map_or(0, String::len)
            .to_string()
            .as_bytes(),
    );
    wire.extend_from_slice(b"\r\nConnection: close\r\n\r\n");
    if let Some(body) = &api_request.body {
        wire.extend_from_slice(body.as_bytes());
    }
    let written = stream.write_all(&wire).and_then(|_| stream.flush()).is_ok();
    zeroize_bytes(&mut wire);
    zeroize_bytes(&mut trace);
    if !written {
        return Err("RO-CORE-API-UNAVAILABLE");
    }
    if cancellation.is_some_and(|flag| flag.load(Ordering::Acquire)) {
        return Err("RO-CORE-API-CANCELLED");
    }
    let mut response = Vec::new();
    let deadline = Instant::now() + Duration::from_secs(2);
    let mut chunk = [0_u8; 8192];
    loop {
        if cancellation.is_some_and(|flag| flag.load(Ordering::Acquire)) {
            return Err("RO-CORE-API-CANCELLED");
        }
        match stream.read(&mut chunk) {
            Ok(0) => break,
            Ok(count) => {
                if response.len().saturating_add(count) > 1_048_576 {
                    return Err("RO-CORE-API-RESPONSE-INVALID");
                }
                response.extend_from_slice(&chunk[..count]);
            }
            Err(error)
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                ) && Instant::now() < deadline => {}
            Err(_) => return Err("RO-CORE-API-RESPONSE-INVALID"),
        }
        if Instant::now() >= deadline {
            return Err("RO-CORE-API-RESPONSE-INVALID");
        }
    }
    parse_api_response(&response, &trace_id)
}

fn parse_api_response(
    response: &[u8],
    expected_trace: &str,
) -> Result<CoreApiResponse, &'static str> {
    let split = response
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or("RO-CORE-API-RESPONSE-INVALID")?;
    let header_text =
        std::str::from_utf8(&response[..split]).map_err(|_| "RO-CORE-API-RESPONSE-INVALID")?;
    let mut lines = header_text.split("\r\n");
    let status_line = lines.next().ok_or("RO-CORE-API-RESPONSE-INVALID")?;
    let mut status_parts = status_line.splitn(3, ' ');
    if status_parts.next() != Some("HTTP/1.1") {
        return Err("RO-CORE-API-RESPONSE-INVALID");
    }
    let status = status_parts
        .next()
        .filter(|value| value.len() == 3 && value.bytes().all(|byte| byte.is_ascii_digit()))
        .and_then(|value| value.parse::<u16>().ok())
        .filter(|value| (100..=599).contains(value))
        .ok_or("RO-CORE-API-RESPONSE-INVALID")?;
    if status_parts.next().is_none() {
        return Err("RO-CORE-API-RESPONSE-INVALID");
    }
    let mut content_type: Option<String> = None;
    let mut trace_id: Option<String> = None;
    let mut etag: Option<String> = None;
    let mut transfer_encoding: Option<&str> = None;
    let mut content_length: Option<usize> = None;
    for line in lines {
        let (name, value) = line.split_once(':').ok_or("RO-CORE-API-RESPONSE-INVALID")?;
        let value = value.trim();
        if name.eq_ignore_ascii_case("content-type") {
            if content_type.is_some() {
                return Err("RO-CORE-API-RESPONSE-INVALID");
            }
            content_type = Some(value.split(';').next().unwrap_or("").to_ascii_lowercase());
        } else if name.eq_ignore_ascii_case("x-trace-id") {
            if trace_id.is_some() {
                return Err("RO-CORE-API-RESPONSE-INVALID");
            }
            trace_id = Some(value.to_owned());
        } else if name.eq_ignore_ascii_case("etag") {
            if etag.is_some() || value.len() > 160 || !value.is_ascii() {
                return Err("RO-CORE-API-RESPONSE-INVALID");
            }
            etag = Some(value.to_owned());
        } else if name.eq_ignore_ascii_case("transfer-encoding") {
            if transfer_encoding.is_some() || !value.eq_ignore_ascii_case("chunked") {
                return Err("RO-CORE-API-RESPONSE-INVALID");
            }
            transfer_encoding = Some(value);
        } else if name.eq_ignore_ascii_case("content-length") {
            if content_length.is_some()
                || !canonical_unsigned(value, 0, 1_048_576)
                || value.parse::<usize>().is_err()
            {
                return Err("RO-CORE-API-RESPONSE-INVALID");
            }
            content_length = value.parse::<usize>().ok();
        }
    }
    if trace_id.as_deref() != Some(expected_trace) {
        return Err("RO-CORE-API-RESPONSE-INVALID");
    }
    let raw_body = &response[split + 4..];
    if transfer_encoding.is_some() && content_length.is_some() {
        return Err("RO-CORE-API-RESPONSE-INVALID");
    }
    let body_bytes = if transfer_encoding.is_some() {
        decode_chunked(raw_body)?
    } else {
        if content_length != Some(raw_body.len()) {
            return Err("RO-CORE-API-RESPONSE-INVALID");
        }
        raw_body.to_vec()
    };
    let body = String::from_utf8(body_bytes).map_err(|_| "RO-CORE-API-RESPONSE-INVALID")?;
    Ok(CoreApiResponse {
        status,
        content_type: content_type.ok_or("RO-CORE-API-RESPONSE-INVALID")?,
        trace_id: trace_id.ok_or("RO-CORE-API-RESPONSE-INVALID")?,
        etag,
        body,
    })
}

fn decode_chunked(body: &[u8]) -> Result<Vec<u8>, &'static str> {
    let mut offset = 0;
    let mut decoded = Vec::new();
    loop {
        let line_end = body[offset..]
            .windows(2)
            .position(|window| window == b"\r\n")
            .map(|position| offset + position)
            .ok_or("RO-CORE-API-RESPONSE-INVALID")?;
        let size_text = std::str::from_utf8(&body[offset..line_end])
            .map_err(|_| "RO-CORE-API-RESPONSE-INVALID")?;
        if size_text.is_empty()
            || size_text.len() > 8
            || !size_text.bytes().all(|byte| byte.is_ascii_hexdigit())
        {
            return Err("RO-CORE-API-RESPONSE-INVALID");
        }
        let size =
            usize::from_str_radix(size_text, 16).map_err(|_| "RO-CORE-API-RESPONSE-INVALID")?;
        offset = line_end + 2;
        if size == 0 {
            if body.get(offset..offset + 2) != Some(b"\r\n") {
                return Err("RO-CORE-API-RESPONSE-INVALID");
            }
            return Ok(decoded);
        }
        let end = offset
            .checked_add(size)
            .filter(|end| *end <= body.len())
            .ok_or("RO-CORE-API-RESPONSE-INVALID")?;
        if decoded.len() + size > 1_048_576 || body.get(end..end + 2) != Some(b"\r\n") {
            return Err("RO-CORE-API-RESPONSE-INVALID");
        }
        decoded.extend_from_slice(&body[offset..end]);
        offset = end + 2;
    }
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
        || handshake.port == 0
        || !nonce_valid
        || handshake.capabilities
            != [
                "operations.cancel",
                "operations.events",
                "operations.read",
                "privacy.cache-cleanup",
                "privacy.policy",
                "projects.lifecycle",
                "runtime.contract",
                "runtime.status",
            ]
        || handshake.database_compatibility.minimum != "0.1.0"
        || handshake.database_compatibility.maximum_exclusive != "0.2.0"
        || handshake.diagnostic_code != "RO-CORE-STARTING"
    {
        return Err((RuntimeState::Incompatible, "RO-CORE-INCOMPATIBLE"));
    }
    Ok(handshake)
}

fn ensure_attempt_active(
    shared: &Arc<SupervisorShared>,
    attempt: u8,
) -> Result<(), (RuntimeState, &'static str)> {
    let locked = shared
        .inner
        .lock()
        .expect("runtime supervisor mutex poisoned");
    if locked.attempt == attempt && locked.state == RuntimeState::Starting {
        Ok(())
    } else {
        Err((RuntimeState::Stopped, "RO-CORE-STOPPED"))
    }
}

fn wait_until_ready(
    handshake: &RuntimeHandshake,
    capability_token: &CapabilityToken,
    child: &mut Child,
    shared: &Arc<SupervisorShared>,
    attempt: u8,
) -> Result<(), (RuntimeState, &'static str)> {
    let address = SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), handshake.port);
    let deadline = Instant::now() + START_TIMEOUT;
    while Instant::now() < deadline {
        ensure_attempt_active(shared, attempt)?;
        match child.try_wait() {
            Ok(Some(_)) => return Err((RuntimeState::Crashed, "RO-CORE-EARLY-EXIT")),
            Ok(None) => {}
            Err(_) => return Err((RuntimeState::Crashed, "RO-CORE-STATUS-FAILED")),
        }
        if let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(250)) {
            let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
            let mut request = format!(
                "GET /readyz HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer ",
                handshake.port,
            )
            .into_bytes();
            capability_token.append_hex(&mut request);
            request.extend_from_slice(b"\r\nConnection: close\r\n\r\n");
            let written = stream.write_all(&request).is_ok();
            request.fill(0);
            if written {
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

fn semantic_version(value: &str) -> Option<[u64; 3]> {
    let mut parts = value.split('.');
    let parse = |part: &str| {
        if part.is_empty()
            || (part.len() > 1 && part.starts_with('0'))
            || !part.bytes().all(|byte| byte.is_ascii_digit())
        {
            return None;
        }
        part.parse::<u64>().ok()
    };
    let version = [
        parse(parts.next()?)?,
        parse(parts.next()?)?,
        parse(parts.next()?)?,
    ];
    parts.next().is_none().then_some(version)
}

fn version_response_is_compatible(response: &CoreApiResponse) -> bool {
    if response.status != 200
        || response.content_type != "application/json"
        || response.etag.is_some()
    {
        return false;
    }
    let Ok(version) = serde_json::from_str::<VersionResponse>(&response.body) else {
        return false;
    };
    let Some(client) = semantic_version(CORE_API_CLIENT_VERSION) else {
        return false;
    };
    let Some(api) = semantic_version(&version.api_version) else {
        return false;
    };
    let Some(minimum) = semantic_version(&version.minimum_client_api_version) else {
        return false;
    };
    let Some(maximum) = semantic_version(&version.maximum_client_api_version_exclusive) else {
        return false;
    };
    version.schema_version == "1.0"
        && version.service == "research-observatory-core"
        && version.version == EXPECTED_BUILD
        && api[0] == client[0]
        && client >= minimum
        && client < maximum
}

fn verify_core_api_contract(
    port: u16,
    capability_token: &CapabilityToken,
) -> Result<(), (RuntimeState, &'static str)> {
    let request = CoreApiRequest {
        method: "GET".to_owned(),
        path: "/runtime/version".to_owned(),
        body: None,
        if_match: None,
        idempotency_key: None,
    };
    let response = authenticated_api_request(port, capability_token, &request)
        .map_err(|_| (RuntimeState::Incompatible, "RO-CORE-INCOMPATIBLE"))?;
    if version_response_is_compatible(&response) {
        Ok(())
    } else {
        Err((RuntimeState::Incompatible, "RO-CORE-INCOMPATIBLE"))
    }
}

#[cfg(windows)]
fn fill_secure_random(target: &mut [u8]) -> Result<(), &'static str> {
    use windows_sys::Win32::Security::Cryptography::{
        BCRYPT_USE_SYSTEM_PREFERRED_RNG, BCryptGenRandom,
    };
    let status = unsafe {
        BCryptGenRandom(
            std::ptr::null_mut(),
            target.as_mut_ptr(),
            target.len() as u32,
            BCRYPT_USE_SYSTEM_PREFERRED_RNG,
        )
    };
    if status < 0 {
        return Err("RO-CORE-AUTH-RANDOM-FAILED");
    }
    Ok(())
}

#[cfg(not(windows))]
fn fill_secure_random(target: &mut [u8]) -> Result<(), &'static str> {
    std::fs::File::open("/dev/urandom")
        .and_then(|mut source| source.read_exact(target))
        .map_err(|_| "RO-CORE-AUTH-RANDOM-FAILED")
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

fn stop_running_process_immediately(process: &mut RunningProcess) {
    process.cancellation.store(true, Ordering::Release);
    process.containment.terminate();
    let _ = process.child.kill();
    let _ = process.child.wait();
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
        && payload.capabilities
            == [
                "operations.cancel",
                "operations.events",
                "operations.read",
                "privacy.cache-cleanup",
                "privacy.policy",
                "projects.lifecycle",
                "runtime.contract",
                "runtime.status",
            ]
        && payload.ready
}

fn drain_log<R: BufRead>(mut reader: R, shared: Weak<SupervisorShared>, stream: &'static str) {
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
        let Some(shared) = shared.upgrade() else {
            return;
        };
        if let Ok(mut locked) = shared.inner.lock() {
            locked.record(code, stream, None);
        }
        line.clear();
    }
}

#[cfg(windows)]
fn configure_hidden_process(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    use windows_sys::Win32::System::Threading::{CREATE_NO_WINDOW, CREATE_SUSPENDED};
    command.creation_flags(CREATE_NO_WINDOW | CREATE_SUSPENDED);
}

#[cfg(windows)]
fn process_working_set_bytes(pid: u32) -> Option<u64> {
    use windows_sys::Win32::Foundation::CloseHandle;
    use windows_sys::Win32::System::ProcessStatus::{
        K32GetProcessMemoryInfo, PROCESS_MEMORY_COUNTERS,
    };
    use windows_sys::Win32::System::Threading::{OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION};

    unsafe {
        let process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if process.is_null() {
            return None;
        }
        let mut counters = PROCESS_MEMORY_COUNTERS {
            cb: std::mem::size_of::<PROCESS_MEMORY_COUNTERS>() as u32,
            ..Default::default()
        };
        let result = K32GetProcessMemoryInfo(
            process,
            &mut counters,
            std::mem::size_of::<PROCESS_MEMORY_COUNTERS>() as u32,
        );
        CloseHandle(process);
        (result != 0).then_some(counters.WorkingSetSize as u64)
    }
}

#[cfg(not(windows))]
fn process_working_set_bytes(_pid: u32) -> Option<u64> {
    None
}

#[cfg(not(windows))]
fn configure_hidden_process(_command: &mut Command) {}

#[cfg(windows)]
struct ProcessTreeContainment(windows_sys::Win32::Foundation::HANDLE);

#[cfg(windows)]
unsafe impl Send for ProcessTreeContainment {}

#[cfg(windows)]
impl ProcessTreeContainment {
    fn attach_and_resume(child: &Child) -> Result<Self, &'static str> {
        use std::mem::{size_of, zeroed};
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
        use windows_sys::Win32::System::Diagnostics::ToolHelp::{
            CreateToolhelp32Snapshot, TH32CS_SNAPTHREAD, THREADENTRY32, Thread32First, Thread32Next,
        };
        use windows_sys::Win32::System::JobObjects::{
            AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
            SetInformationJobObject,
        };
        use windows_sys::Win32::System::Threading::{
            OpenThread, ResumeThread, THREAD_SUSPEND_RESUME,
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
                CloseHandle(job);
                return Err("RO-CORE-CONTAINMENT-FAILED");
            }
            let assigned = AssignProcessToJobObject(job, child.as_raw_handle().cast());
            if assigned == 0 {
                CloseHandle(job);
                return Err("RO-CORE-CONTAINMENT-FAILED");
            }
            let snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
            if snapshot == INVALID_HANDLE_VALUE {
                CloseHandle(job);
                return Err("RO-CORE-CONTAINMENT-FAILED");
            }
            let mut entry: THREADENTRY32 = zeroed();
            entry.dwSize = size_of::<THREADENTRY32>() as u32;
            let mut found = false;
            let mut has_entry = Thread32First(snapshot, &raw mut entry) != 0;
            while has_entry {
                if entry.th32OwnerProcessID == child.id() {
                    let thread = OpenThread(THREAD_SUSPEND_RESUME, 0, entry.th32ThreadID);
                    if thread.is_null() || ResumeThread(thread) == u32::MAX {
                        if !thread.is_null() {
                            CloseHandle(thread);
                        }
                        CloseHandle(snapshot);
                        CloseHandle(job);
                        return Err("RO-CORE-CONTAINMENT-FAILED");
                    }
                    CloseHandle(thread);
                    found = true;
                }
                has_entry = Thread32Next(snapshot, &raw mut entry) != 0;
            }
            CloseHandle(snapshot);
            if !found {
                CloseHandle(job);
                return Err("RO-CORE-CONTAINMENT-FAILED");
            }
            Ok(Self(job))
        }
    }

    fn terminate(&self) {
        use std::mem::size_of;
        use windows_sys::Win32::Foundation::CloseHandle;
        use windows_sys::Win32::System::JobObjects::{
            JOBOBJECT_BASIC_PROCESS_ID_LIST, JobObjectBasicProcessIdList, QueryInformationJobObject,
        };
        use windows_sys::Win32::System::Threading::{
            OpenProcess, PROCESS_SYNCHRONIZE, WaitForSingleObject,
        };
        unsafe {
            const MAX_JOB_PROCESSES: usize = 256;
            let mut process_ids = vec![0_usize; 2 + MAX_JOB_PROCESSES];
            let queried = QueryInformationJobObject(
                self.0,
                JobObjectBasicProcessIdList,
                process_ids.as_mut_ptr().cast(),
                (process_ids.len() * size_of::<usize>()) as u32,
                std::ptr::null_mut(),
            );
            let mut process_handles = Vec::new();
            if queried != 0 {
                let list = &*process_ids
                    .as_ptr()
                    .cast::<JOBOBJECT_BASIC_PROCESS_ID_LIST>();
                let count = usize::try_from(list.NumberOfProcessIdsInList)
                    .unwrap_or(0)
                    .min(MAX_JOB_PROCESSES);
                for &pid in std::slice::from_raw_parts(list.ProcessIdList.as_ptr(), count) {
                    let handle = OpenProcess(PROCESS_SYNCHRONIZE, 0, pid as u32);
                    if !handle.is_null() {
                        process_handles.push(handle);
                    }
                }
            }
            windows_sys::Win32::System::JobObjects::TerminateJobObject(self.0, 1);
            let deadline = Instant::now() + STOP_TIMEOUT;
            for handle in process_handles {
                let remaining = deadline.saturating_duration_since(Instant::now());
                let timeout = u32::try_from(remaining.as_millis()).unwrap_or(u32::MAX);
                WaitForSingleObject(handle, timeout);
                CloseHandle(handle);
            }
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
    fn attach_and_resume(_child: &Child) -> Result<Self, &'static str> {
        Ok(Self)
    }

    fn terminate(&self) {}
}

#[cfg(test)]
mod tests {
    use super::{
        CapabilityToken, CoreApiRequest, RuntimeState, RuntimeSupervisor, SupervisorInner,
        authenticated_api_request_with_cancellation, parse_api_response, semantic_version,
        validate_api_request, validate_handshake, version_response_is_compatible,
    };
    use std::collections::VecDeque;
    use std::io::Read;
    use std::net::TcpListener;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::{Arc, mpsc};

    fn handshake(pid: u32) -> Vec<u8> {
        format!(
            concat!(
                "{{\"protocolVersion\":\"1.0\",\"buildId\":\"0.1.0\",\"pid\":{},",
                "\"host\":\"127.0.0.1\",\"port\":49152,",
                "\"nonce\":\"0123456789abcdef0123456789abcdef\",",
                "\"capabilities\":[\"operations.cancel\",\"operations.events\",\"operations.read\",\"privacy.cache-cleanup\",\"privacy.policy\",\"projects.lifecycle\",\"runtime.contract\",\"runtime.status\"],",
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
        let port_zero = String::from_utf8(handshake(42))
            .expect("UTF-8 handshake")
            .replace("\"port\":49152", "\"port\":0")
            .into_bytes();
        assert!(validate_handshake(&port_zero, 42).is_err());
        let mut extra = handshake(42);
        extra.splice(
            extra.len() - 2..extra.len() - 2,
            b",\"secret\":\"hunter2\"".iter().copied(),
        );
        assert!(validate_handshake(&extra, 42).is_err());
        assert!(validate_handshake(&vec![b'x'; 4097], 42).is_err());
    }

    #[test]
    fn capability_tokens_are_256_bit_and_rotate() {
        let first = CapabilityToken::generate().expect("system CSPRNG");
        let second = CapabilityToken::generate().expect("system CSPRNG");
        assert_eq!(first.0.len(), 32);
        assert_ne!(first.0, second.0);
        let mut encoded = Vec::new();
        first.append_hex(&mut encoded);
        assert_eq!(encoded.len(), 64);
        assert!(
            encoded
                .iter()
                .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(value))
        );
    }

    #[test]
    fn native_api_transport_allows_only_generated_local_routes() {
        for (method, path) in [
            ("GET", "/runtime/version"),
            ("GET", "/healthz"),
            ("GET", "/runtime/operations?limit=50"),
            ("GET", "/runtime/operations?limit=2&after=op-first"),
            ("GET", "/runtime/operations/op-first"),
            ("GET", "/runtime/operations/op-first/events?afterSequence=0"),
            ("POST", "/runtime/operations/op-first/cancel"),
        ] {
            assert!(
                validate_api_request(&CoreApiRequest {
                    method: method.to_owned(),
                    path: path.to_owned(),
                    body: None,
                    if_match: (method == "POST").then(|| "\"op-first-1\"".to_owned()),
                    idempotency_key: (method == "POST").then(|| "a".repeat(32)),
                })
                .is_ok(),
                "{method} {path}",
            );
        }
        for (path, body) in [
            (
                "/projects",
                r#"{"parentDirectory":"C:/Research","directoryName":"study-one","displayName":"Study One","templateId":"theory-synthesis"}"#,
            ),
            ("/projects/open", r#"{"root":"C:/Research/study-one"}"#),
            ("/projects/close", r#"{"root":"C:/Research/study-one"}"#),
            ("/projects/archive", r#"{"root":"C:/Research/study-one"}"#),
            ("/projects/restore", r#"{"root":"C:/Research/study-one"}"#),
            (
                "/projects/delete",
                r#"{"root":"C:/Research/study-one","confirmation":"delete:11111111-1111-4111-8111-111111111111"}"#,
            ),
            ("/projects/privacy", r#"{"root":"C:/Research/study-one"}"#),
            (
                "/projects/privacy/update",
                r#"{"root":"C:/Research/study-one","expectedRevision":0,"networkPolicy":"approved-providers","remoteModelApproval":"preview-every-task","telemetryMode":"off","logRetentionDays":14,"documentRetention":"project-lifetime","cacheRetentionDays":30,"egressConsentToken":"acknowledge-egress-preview-v1"}"#,
            ),
            (
                "/projects/privacy/cache/preview",
                r#"{"root":"C:/Research/study-one"}"#,
            ),
            (
                "/projects/privacy/cache/clear",
                r#"{"root":"C:/Research/study-one","previewToken":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","confirmation":"clear-cache:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}"#,
            ),
        ] {
            assert!(
                validate_api_request(&CoreApiRequest {
                    method: "POST".to_owned(),
                    path: path.to_owned(),
                    body: Some(body.to_owned()),
                    if_match: None,
                    idempotency_key: None,
                })
                .is_ok(),
                "POST {path}",
            );
        }
        for (path, body) in [
            ("/projects/open", r#"{"root":"../escape"}"#),
            (
                "/projects/open",
                r#"{"root":"C:/Study","extra":"untrusted"}"#,
            ),
            (
                "/projects/delete",
                r#"{"root":"C:/Study","confirmation":"delete:wrong"}"#,
            ),
            ("/projects", r#"{"parentDirectory":"C:/Research"}"#),
            (
                "/projects/privacy/update",
                r#"{"root":"C:/Study","expectedRevision":0,"networkPolicy":"approved-providers","remoteModelApproval":"preview-every-task","telemetryMode":"off","logRetentionDays":14,"documentRetention":"project-lifetime","cacheRetentionDays":30,"egressConsentToken":null}"#,
            ),
            (
                "/projects/privacy/update",
                r#"{"root":"C:/Study","expectedRevision":0,"networkPolicy":"offline","remoteModelApproval":"preview-every-task","telemetryMode":"off","logRetentionDays":0,"documentRetention":"project-lifetime","cacheRetentionDays":30,"egressConsentToken":null}"#,
            ),
            (
                "/projects/privacy/cache/clear",
                r#"{"root":"C:/Study","previewToken":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","confirmation":"clear-cache:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}"#,
            ),
            ("/openapi.json", r#"{}"#),
        ] {
            assert!(
                validate_api_request(&CoreApiRequest {
                    method: "POST".to_owned(),
                    path: path.to_owned(),
                    body: Some(body.to_owned()),
                    if_match: None,
                    idempotency_key: None,
                })
                .is_err(),
                "POST {path}",
            );
        }
        for (method, path) in [
            ("GET", "https://evil.invalid/runtime/version"),
            ("GET", "/runtime/version\r\nHost: evil.invalid"),
            ("GET", "/openapi.json"),
            ("GET", "/runtime/operations?limit=0"),
            ("GET", "/runtime/operations?limit=50&after="),
            (
                "GET",
                "/runtime/operations/op-first/events?afterSequence=01",
            ),
            ("DELETE", "/runtime/operations/op-first"),
            ("POST", "/runtime/operations/op-first/cancel"),
        ] {
            assert!(
                validate_api_request(&CoreApiRequest {
                    method: method.to_owned(),
                    path: path.to_owned(),
                    body: None,
                    if_match: None,
                    idempotency_key: None,
                })
                .is_err(),
                "{method} {path}",
            );
        }
    }

    #[test]
    fn native_api_transport_parses_only_correlated_bounded_responses() {
        let trace = "0123456789abcdef0123456789abcdef";
        let response = format!(
            "HTTP/1.1 200 OK\r\ncontent-type: application/json; charset=utf-8\r\nx-trace-id: {trace}\r\ncontent-length: 2\r\n\r\n{{}}"
        );
        let parsed = parse_api_response(response.as_bytes(), trace).expect("valid response");
        assert_eq!(parsed.status, 200);
        assert_eq!(parsed.content_type, "application/json");
        assert_eq!(parsed.body, "{}");
        assert!(
            parse_api_response(response.as_bytes(), "ffffffffffffffffffffffffffffffff").is_err()
        );
        assert!(
            parse_api_response(response.replacen("200 OK", "200evil", 1).as_bytes(), trace)
                .is_err()
        );
        assert!(
            parse_api_response(
                response
                    .replacen("content-length: 2", "content-length: 3", 1)
                    .as_bytes(),
                trace
            )
            .is_err()
        );

        let chunked = format!(
            "HTTP/1.1 200 OK\r\ncontent-type: text/event-stream\r\nx-trace-id: {trace}\r\ntransfer-encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n"
        );
        assert_eq!(
            parse_api_response(chunked.as_bytes(), trace)
                .expect("valid chunked response")
                .body,
            "hello"
        );
    }

    #[test]
    fn native_api_transport_cancels_an_inflight_request_without_waiting_for_response() {
        let listener = TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, 0)).expect("listener");
        let port = listener.local_addr().expect("listener address").port();
        let (received_tx, received_rx) = mpsc::sync_channel(1);
        let (release_tx, release_rx) = mpsc::sync_channel(1);
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accepted request");
            let mut first = [0_u8; 1];
            stream.read_exact(&mut first).expect("request byte");
            received_tx.send(()).expect("request observed");
            release_rx.recv().expect("release server");
        });
        let cancellation = Arc::new(AtomicBool::new(false));
        let request_cancellation = Arc::clone(&cancellation);
        let client = std::thread::spawn(move || {
            authenticated_api_request_with_cancellation(
                port,
                &CapabilityToken::generate().expect("capability token"),
                &CoreApiRequest {
                    method: "GET".to_owned(),
                    path: "/runtime/version".to_owned(),
                    body: None,
                    if_match: None,
                    idempotency_key: None,
                },
                Some(request_cancellation.as_ref()),
            )
        });
        received_rx.recv().expect("request reached server");
        cancellation.store(true, Ordering::Release);
        assert_eq!(
            client.join().expect("client result"),
            Err("RO-CORE-API-CANCELLED")
        );
        release_tx.send(()).expect("release server");
        server.join().expect("server stopped");
    }

    #[test]
    fn native_startup_enforces_the_generated_api_compatibility_range() {
        assert_eq!(semantic_version("1.0.0"), Some([1, 0, 0]));
        assert_eq!(semantic_version("01.0.0"), None);
        assert_eq!(semantic_version("1.0"), None);
        let compatible = super::CoreApiResponse {
            status: 200,
            content_type: "application/json".to_owned(),
            trace_id: "0123456789abcdef0123456789abcdef".to_owned(),
            etag: None,
            body: concat!(
                "{\"schemaVersion\":\"1.0\",",
                "\"service\":\"research-observatory-core\",",
                "\"version\":\"0.1.0\",\"apiVersion\":\"1.0.0\",",
                "\"minimumClientApiVersion\":\"1.0.0\",",
                "\"maximumClientApiVersionExclusive\":\"2.0.0\"}"
            )
            .to_owned(),
        };
        assert!(version_response_is_compatible(&compatible));
        assert!(!version_response_is_compatible(&super::CoreApiResponse {
            body: compatible
                .body
                .replace("\"apiVersion\":\"1.0.0\"", "\"apiVersion\":\"2.0.0\""),
            ..compatible
        }));
    }

    #[test]
    fn bounded_diagnostics_discard_oldest_without_raw_content() {
        let mut inner = SupervisorInner {
            state: RuntimeState::Stopped,
            state_diagnostic: Some("RO-CORE-STOPPED"),
            attempt: 0,
            process: None,
            launching: false,
            stopping: false,
            diagnostics: VecDeque::new(),
            sequence: 0,
        };
        for _ in 0..80 {
            inner.record("RO-CORE-RUNTIME-LOG", "stderr", None);
        }
        assert_eq!(inner.diagnostics.len(), 64);
        assert_eq!(inner.diagnostics.front().expect("diagnostic").sequence, 17);
        let trace_id = "0123456789abcdef0123456789abcdef".to_owned();
        inner.record(
            "RO-CORE-API-REQUEST-COMPLETE",
            "api",
            Some(trace_id.clone()),
        );
        assert_eq!(
            inner
                .diagnostics
                .back()
                .expect("trace-linked diagnostic")
                .trace_id,
            Some(trace_id)
        );
    }

    #[test]
    fn late_log_records_do_not_replace_the_state_diagnostic() {
        let mut inner = SupervisorInner {
            state: RuntimeState::Crashed,
            state_diagnostic: Some("RO-CORE-CRASHED"),
            attempt: 1,
            process: None,
            launching: false,
            stopping: false,
            diagnostics: VecDeque::new(),
            sequence: 0,
        };
        inner.record("RO-CORE-RUNTIME-LOG", "stderr", None);
        inner.record("RO-CORE-LOG-OVERSIZE", "stdout", None);
        assert_eq!(
            inner.snapshot().diagnostic_reference,
            Some("RO-CORE-CRASHED")
        );
    }

    #[test]
    fn stop_cannot_launder_a_configuration_failure() {
        let supervisor = RuntimeSupervisor::new(Err("RO-CORE-INTEGRITY-FAILED"));
        let snapshot = supervisor.stop();
        assert_eq!(snapshot.state, RuntimeState::RecoveryRequired);
        assert_eq!(
            snapshot.diagnostic_reference,
            Some("RO-CORE-INTEGRITY-FAILED")
        );
        assert!(!snapshot.retry_available);
    }
}
