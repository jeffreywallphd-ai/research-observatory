use std::collections::VecDeque;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

use crate::application_lock_verification::{
    NativeVerificationProvider, VerificationOutcome, WindowsPasswordVerificationProvider,
};
use crate::supervisor::{RuntimeState, RuntimeSupervisor};

const MAX_PROFILE_BYTES: u64 = 16 * 1024;
const MAX_AUDIT_EVENTS: usize = 64;
const PROFILE_FILE: &str = "application-lock-profile.v1.json";
const REAUTHENTICATION: &str = "windows-current-user-credentials-same-sid";
const THREAT_DISCLOSURE: &str =
    "Application-session protection only; this is not Windows-account isolation.";

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ApplicationLockState {
    Locked,
    Unlocked,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ApplicationLockReason {
    Manual,
    Inactivity,
    ApplicationRestart,
    ConfigurationInvalid,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum LockConfigurationState {
    Default,
    Valid,
    Invalid,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ApplicationLockSnapshot {
    pub schema_version: &'static str,
    pub state: ApplicationLockState,
    pub profile_name: Option<String>,
    pub inactivity_timeout_minutes: u8,
    pub configuration_state: LockConfigurationState,
    pub reason: Option<ApplicationLockReason>,
    pub reauthentication: &'static str,
    pub threat_disclosure: &'static str,
    pub retry_after_seconds: u64,
    pub audit_sequence: u64,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ApplicationLockAuditEvent {
    pub sequence: u64,
    pub operation: &'static str,
    pub outcome: &'static str,
    pub reason_code: &'static str,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ApplicationUnlockAttempt {
    pub schema_version: &'static str,
    pub outcome: VerificationOutcome,
    pub reason_code: &'static str,
    pub snapshot: ApplicationLockSnapshot,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct ApplicationLockProfile {
    schema_version: String,
    document_type: String,
    profile_name: Option<String>,
    inactivity_timeout_minutes: u8,
    restart_policy: String,
    lock_authority: String,
    reauthentication: String,
    protected_action_policy: String,
    durable_operation_policy: String,
    threat_boundary: String,
}

impl ApplicationLockProfile {
    fn new(profile_name: Option<String>, inactivity_timeout_minutes: u8) -> Self {
        Self {
            schema_version: "1.0".to_owned(),
            document_type: "research-observatory-application-lock-profile".to_owned(),
            profile_name,
            inactivity_timeout_minutes,
            restart_policy: "lock-when-inactivity-enabled".to_owned(),
            lock_authority: "desktop-native-supervisor".to_owned(),
            reauthentication: REAUTHENTICATION.to_owned(),
            protected_action_policy: "invalidate-generation-stop-core-discard-renderer-state"
                .to_owned(),
            durable_operation_policy: "w1-stop-all-future-continuation-requires-explicit-allowlist"
                .to_owned(),
            threat_boundary: "application-session-protection-not-windows-account-isolation"
                .to_owned(),
        }
    }

    fn validate(&self) -> Result<(), &'static str> {
        if self.schema_version != "1.0"
            || self.document_type != "research-observatory-application-lock-profile"
            || self.restart_policy != "lock-when-inactivity-enabled"
            || self.lock_authority != "desktop-native-supervisor"
            || self.reauthentication != REAUTHENTICATION
            || self.protected_action_policy
                != "invalidate-generation-stop-core-discard-renderer-state"
            || self.durable_operation_policy
                != "w1-stop-all-future-continuation-requires-explicit-allowlist"
            || self.threat_boundary
                != "application-session-protection-not-windows-account-isolation"
            || !matches!(self.inactivity_timeout_minutes, 0 | 5 | 15 | 30 | 60)
        {
            return Err("RO-LOCK-CONFIGURATION-INVALID");
        }
        validate_profile_name(self.profile_name.as_deref())
    }
}

struct ApplicationLockInner {
    state: ApplicationLockState,
    reason: Option<ApplicationLockReason>,
    configuration_state: LockConfigurationState,
    profile: ApplicationLockProfile,
    generation: u64,
    last_activity: Instant,
    failed_attempts: u8,
    retry_at: Option<Instant>,
    reauthentication_in_progress: bool,
    audit_sequence: u64,
    audit: VecDeque<ApplicationLockAuditEvent>,
}

impl ApplicationLockInner {
    fn snapshot(&self) -> ApplicationLockSnapshot {
        ApplicationLockSnapshot {
            schema_version: "1.0",
            state: self.state,
            profile_name: (self.state == ApplicationLockState::Unlocked)
                .then(|| self.profile.profile_name.clone())
                .flatten(),
            inactivity_timeout_minutes: self.profile.inactivity_timeout_minutes,
            configuration_state: self.configuration_state,
            reason: self.reason,
            reauthentication: REAUTHENTICATION,
            threat_disclosure: THREAT_DISCLOSURE,
            retry_after_seconds: self
                .retry_at
                .and_then(|deadline| deadline.checked_duration_since(Instant::now()))
                .map(|remaining| remaining.as_secs().saturating_add(1))
                .unwrap_or(0),
            audit_sequence: self.audit_sequence,
        }
    }

    fn record(
        &mut self,
        operation: &'static str,
        outcome: &'static str,
        reason_code: &'static str,
    ) {
        self.audit_sequence = self.audit_sequence.saturating_add(1);
        if self.audit.len() == MAX_AUDIT_EVENTS {
            self.audit.pop_front();
        }
        self.audit.push_back(ApplicationLockAuditEvent {
            sequence: self.audit_sequence,
            operation,
            outcome,
            reason_code,
        });
    }

    fn lock(&mut self, reason: ApplicationLockReason) -> bool {
        if self.state == ApplicationLockState::Locked {
            if self.reauthentication_in_progress {
                self.generation = self.generation.saturating_add(1);
            }
            return false;
        }
        self.generation = self.generation.saturating_add(1);
        self.state = ApplicationLockState::Locked;
        self.reason = Some(reason);
        self.record("application-lock", "locked", reason_code(reason));
        true
    }
}

#[derive(Clone)]
pub struct ApplicationLockManager {
    profile_path: PathBuf,
    shared: Arc<Mutex<ApplicationLockInner>>,
}

impl ApplicationLockManager {
    pub fn new(application_data: &Path) -> Self {
        let profile_path = application_data.join("security").join(PROFILE_FILE);
        let (profile, configuration_state, state, reason) = match read_profile(&profile_path) {
            Ok(Some(profile)) if profile.inactivity_timeout_minutes > 0 => (
                profile,
                LockConfigurationState::Valid,
                ApplicationLockState::Locked,
                Some(ApplicationLockReason::ApplicationRestart),
            ),
            Ok(Some(profile)) => (
                profile,
                LockConfigurationState::Valid,
                ApplicationLockState::Unlocked,
                None,
            ),
            Ok(None) => (
                ApplicationLockProfile::new(None, 0),
                LockConfigurationState::Default,
                ApplicationLockState::Unlocked,
                None,
            ),
            Err(_) => (
                ApplicationLockProfile::new(None, 0),
                LockConfigurationState::Invalid,
                ApplicationLockState::Locked,
                Some(ApplicationLockReason::ConfigurationInvalid),
            ),
        };
        let mut inner = ApplicationLockInner {
            state,
            reason,
            configuration_state,
            profile,
            generation: u64::from(state == ApplicationLockState::Locked),
            last_activity: Instant::now(),
            failed_attempts: 0,
            retry_at: None,
            reauthentication_in_progress: false,
            audit_sequence: 0,
            audit: VecDeque::new(),
        };
        if let Some(reason) = reason {
            inner.record("application-start", "locked", reason_code(reason));
        }
        Self {
            profile_path,
            shared: Arc::new(Mutex::new(inner)),
        }
    }

    pub fn status(&self) -> ApplicationLockSnapshot {
        self.shared.lock().expect("lock mutex poisoned").snapshot()
    }

    pub fn audit(&self) -> Vec<ApplicationLockAuditEvent> {
        self.shared
            .lock()
            .expect("lock mutex poisoned")
            .audit
            .iter()
            .cloned()
            .collect()
    }

    pub fn is_unlocked(&self) -> bool {
        self.shared.lock().expect("lock mutex poisoned").state == ApplicationLockState::Unlocked
    }

    pub fn begin_protected_action(&self) -> Result<u64, &'static str> {
        let inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.state != ApplicationLockState::Unlocked {
            return Err("RO-APPLICATION-LOCKED");
        }
        Ok(inner.generation)
    }

    pub fn finish_protected_action(&self, generation: u64) -> Result<(), &'static str> {
        let inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.state != ApplicationLockState::Unlocked || inner.generation != generation {
            return Err("RO-APPLICATION-LOCKED");
        }
        Ok(())
    }

    pub fn commit_protected_action<T>(
        &self,
        generation: u64,
        commit: impl FnOnce() -> Result<T, &'static str>,
    ) -> Result<T, &'static str> {
        let inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.state != ApplicationLockState::Unlocked || inner.generation != generation {
            return Err("RO-APPLICATION-LOCKED");
        }
        commit()
    }

    pub fn lock(&self, reason: ApplicationLockReason) -> (ApplicationLockSnapshot, bool) {
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        let changed = inner.lock(reason);
        (inner.snapshot(), changed)
    }

    pub fn record_activity(&self) {
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.state == ApplicationLockState::Unlocked {
            inner.last_activity = Instant::now();
        }
    }

    pub fn record_notification_failure(&self) {
        self.shared.lock().expect("lock mutex poisoned").record(
            "application-lock-notification",
            "failed",
            "RO-LOCK-NOTIFICATION-FAILED",
        );
    }

    pub fn lock_if_idle(&self) -> Option<ApplicationLockSnapshot> {
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        let timeout = inner.profile.inactivity_timeout_minutes;
        if inner.state == ApplicationLockState::Unlocked
            && timeout > 0
            && inner.last_activity.elapsed() >= Duration::from_secs(u64::from(timeout) * 60)
            && inner.lock(ApplicationLockReason::Inactivity)
        {
            Some(inner.snapshot())
        } else {
            None
        }
    }

    pub fn configure(
        &self,
        profile_name: Option<String>,
        inactivity_timeout_minutes: u8,
    ) -> Result<ApplicationLockSnapshot, &'static str> {
        self.configure_with_hook(profile_name, inactivity_timeout_minutes, || {})
    }

    fn configure_with_hook(
        &self,
        profile_name: Option<String>,
        inactivity_timeout_minutes: u8,
        before_publish: impl FnOnce(),
    ) -> Result<ApplicationLockSnapshot, &'static str> {
        let profile_name = profile_name
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty());
        let profile = ApplicationLockProfile::new(profile_name, inactivity_timeout_minutes);
        profile.validate()?;
        let generation = self.begin_protected_action()?;
        let staged = stage_profile(&self.profile_path, &profile)?;
        before_publish();
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.state != ApplicationLockState::Unlocked || inner.generation != generation {
            return Err("RO-APPLICATION-LOCKED");
        }
        staged.publish(&self.profile_path)?;
        inner.profile = profile;
        inner.configuration_state = LockConfigurationState::Valid;
        inner.last_activity = Instant::now();
        inner.record(
            "application-lock-configure",
            "succeeded",
            "RO-LOCK-CONFIGURED",
        );
        Ok(inner.snapshot())
    }

    pub fn reauthenticate(
        &self,
        supervisor: &RuntimeSupervisor,
    ) -> Result<ApplicationUnlockAttempt, &'static str> {
        self.reauthenticate_with(
            &WindowsPasswordVerificationProvider,
            || supervisor.start().state,
            || {
                supervisor.stop_for_application_lock();
            },
        )
    }

    fn reauthenticate_with(
        &self,
        provider: &impl NativeVerificationProvider,
        start_core: impl FnOnce() -> RuntimeState,
        stop_core: impl FnOnce(),
    ) -> Result<ApplicationUnlockAttempt, &'static str> {
        let reservation = match self.reserve_reauthentication() {
            Ok(reservation) => reservation,
            Err(ReauthenticationReservationError::Attempt(attempt)) => return Ok(*attempt),
            Err(ReauthenticationReservationError::InvalidState(reason_code)) => {
                return Err(reason_code);
            }
        };
        let verification = provider.verify();
        if !self.reauthentication_is_current(&reservation) {
            return Ok(self.stale_reauthentication_attempt());
        }
        let result = match verification {
            VerificationOutcome::Cancelled => {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.reauthentication_in_progress = false;
                inner.record("application-unlock", "cancelled", "RO-LOCK-AUTH-CANCELLED");
                unlock_attempt(
                    &inner,
                    VerificationOutcome::Cancelled,
                    "RO-LOCK-AUTH-CANCELLED",
                )
            }
            VerificationOutcome::Denied => {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.reauthentication_in_progress = false;
                inner.failed_attempts = inner.failed_attempts.saturating_add(1);
                let exponent = inner.failed_attempts.saturating_sub(1).min(5);
                inner.retry_at = Some(Instant::now() + Duration::from_secs(1_u64 << exponent));
                inner.record("application-unlock", "denied", "RO-LOCK-AUTH-DENIED");
                unlock_attempt(&inner, VerificationOutcome::Denied, "RO-LOCK-AUTH-DENIED")
            }
            VerificationOutcome::Unavailable => {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.reauthentication_in_progress = false;
                inner.record(
                    "application-unlock",
                    "unavailable",
                    "RO-LOCK-AUTH-UNAVAILABLE",
                );
                unlock_attempt(
                    &inner,
                    VerificationOutcome::Unavailable,
                    "RO-LOCK-AUTH-UNAVAILABLE",
                )
            }
            VerificationOutcome::Busy => {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.reauthentication_in_progress = false;
                inner.record("application-unlock", "busy", "RO-LOCK-AUTH-BUSY");
                unlock_attempt(&inner, VerificationOutcome::Busy, "RO-LOCK-AUTH-BUSY")
            }
            VerificationOutcome::Failed => {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.reauthentication_in_progress = false;
                inner.record("application-unlock", "failed", "RO-LOCK-AUTH-FAILED");
                unlock_attempt(&inner, VerificationOutcome::Failed, "RO-LOCK-AUTH-FAILED")
            }
            VerificationOutcome::Succeeded => {
                if start_core() != RuntimeState::Ready {
                    let mut inner = self.shared.lock().expect("lock mutex poisoned");
                    inner.reauthentication_in_progress = false;
                    inner.record("application-unlock", "failed", "RO-LOCK-CORE-UNAVAILABLE");
                    let attempt = unlock_attempt(
                        &inner,
                        VerificationOutcome::Failed,
                        "RO-LOCK-CORE-UNAVAILABLE",
                    );
                    drop(inner);
                    stop_core();
                    return Ok(attempt);
                }
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                if inner.state != ApplicationLockState::Locked
                    || inner.generation != reservation.generation
                {
                    inner.reauthentication_in_progress = false;
                    inner.record("application-unlock", "failed", "RO-LOCK-AUTH-STALE");
                    let attempt =
                        unlock_attempt(&inner, VerificationOutcome::Failed, "RO-LOCK-AUTH-STALE");
                    drop(inner);
                    stop_core();
                    return Ok(attempt);
                }
                inner.reauthentication_in_progress = false;
                inner.state = ApplicationLockState::Unlocked;
                inner.reason = None;
                inner.failed_attempts = 0;
                inner.retry_at = None;
                inner.last_activity = Instant::now();
                inner.record("application-unlock", "succeeded", "RO-LOCK-UNLOCKED");
                unlock_attempt(&inner, VerificationOutcome::Succeeded, "RO-LOCK-UNLOCKED")
            }
        };
        drop(reservation);
        Ok(result)
    }

    fn reauthentication_is_current(&self, reservation: &ReauthenticationReservation) -> bool {
        let inner = self.shared.lock().expect("lock mutex poisoned");
        inner.state == ApplicationLockState::Locked
            && inner.reauthentication_in_progress
            && inner.generation == reservation.generation
    }

    fn stale_reauthentication_attempt(&self) -> ApplicationUnlockAttempt {
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        inner.reauthentication_in_progress = false;
        inner.record("application-unlock", "failed", "RO-LOCK-AUTH-STALE");
        unlock_attempt(&inner, VerificationOutcome::Failed, "RO-LOCK-AUTH-STALE")
    }

    fn reserve_reauthentication(
        &self,
    ) -> Result<ReauthenticationReservation, ReauthenticationReservationError> {
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.state != ApplicationLockState::Locked {
            inner.record("application-unlock", "failed", "RO-LOCK-AUTH-NOT-LOCKED");
            return Err(ReauthenticationReservationError::InvalidState(
                "RO-LOCK-AUTH-NOT-LOCKED",
            ));
        }
        if inner.reauthentication_in_progress
            || inner
                .retry_at
                .is_some_and(|deadline| deadline > Instant::now())
        {
            inner.record("application-unlock", "denied", "RO-LOCK-RATE-LIMITED");
            return Err(ReauthenticationReservationError::Attempt(Box::new(
                unlock_attempt(&inner, VerificationOutcome::Busy, "RO-LOCK-RATE-LIMITED"),
            )));
        }
        inner.reauthentication_in_progress = true;
        Ok(ReauthenticationReservation {
            shared: Arc::clone(&self.shared),
            generation: inner.generation,
        })
    }

    #[cfg(test)]
    fn complete_test_reauthentication(
        &self,
        result: VerificationOutcome,
        core_ready: bool,
    ) -> Result<ApplicationUnlockAttempt, &'static str> {
        self.reauthenticate_with(
            &|| result,
            || {
                if core_ready {
                    RuntimeState::Ready
                } else {
                    RuntimeState::RecoveryRequired
                }
            },
            || {},
        )
    }
}

fn unlock_attempt(
    inner: &ApplicationLockInner,
    outcome: VerificationOutcome,
    reason_code: &'static str,
) -> ApplicationUnlockAttempt {
    ApplicationUnlockAttempt {
        schema_version: "1.0",
        outcome,
        reason_code,
        snapshot: inner.snapshot(),
    }
}

struct ReauthenticationReservation {
    shared: Arc<Mutex<ApplicationLockInner>>,
    generation: u64,
}

enum ReauthenticationReservationError {
    Attempt(Box<ApplicationUnlockAttempt>),
    InvalidState(&'static str),
}

impl Drop for ReauthenticationReservation {
    fn drop(&mut self) {
        if let Ok(mut inner) = self.shared.lock() {
            inner.reauthentication_in_progress = false;
        }
    }
}

fn validate_profile_name(value: Option<&str>) -> Result<(), &'static str> {
    if value.is_some_and(|name| {
        name.is_empty() || name.chars().count() > 80 || name.chars().any(char::is_control)
    }) {
        return Err("RO-LOCK-CONFIGURATION-INVALID");
    }
    Ok(())
}

fn reason_code(reason: ApplicationLockReason) -> &'static str {
    match reason {
        ApplicationLockReason::Manual => "RO-LOCK-MANUAL",
        ApplicationLockReason::Inactivity => "RO-LOCK-INACTIVITY",
        ApplicationLockReason::ApplicationRestart => "RO-LOCK-APPLICATION-RESTART",
        ApplicationLockReason::ConfigurationInvalid => "RO-LOCK-CONFIGURATION-INVALID",
    }
}

fn read_profile(path: &Path) -> Result<Option<ApplicationLockProfile>, &'static str> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err("RO-LOCK-CONFIGURATION-INVALID"),
    };
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || metadata.len() > MAX_PROFILE_BYTES
    {
        return Err("RO-LOCK-CONFIGURATION-INVALID");
    }
    let bytes = fs::read(path).map_err(|_| "RO-LOCK-CONFIGURATION-INVALID")?;
    let profile: ApplicationLockProfile =
        serde_json::from_slice(&bytes).map_err(|_| "RO-LOCK-CONFIGURATION-INVALID")?;
    profile.validate()?;
    Ok(Some(profile))
}

struct StagedProfile {
    path: PathBuf,
}

impl StagedProfile {
    fn publish(self, destination: &Path) -> Result<(), &'static str> {
        replace_file(&self.path, destination)
    }
}

impl Drop for StagedProfile {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

fn stage_profile(
    path: &Path,
    profile: &ApplicationLockProfile,
) -> Result<StagedProfile, &'static str> {
    profile.validate()?;
    let parent = path.parent().ok_or("RO-LOCK-CONFIGURATION-INVALID")?;
    fs::create_dir_all(parent).map_err(|_| "RO-LOCK-CONFIGURATION-WRITE-FAILED")?;
    let parent_metadata =
        fs::symlink_metadata(parent).map_err(|_| "RO-LOCK-CONFIGURATION-WRITE-FAILED")?;
    if parent_metadata.file_type().is_symlink() || !parent_metadata.is_dir() {
        return Err("RO-LOCK-CONFIGURATION-WRITE-FAILED");
    }
    if let Ok(metadata) = fs::symlink_metadata(path)
        && (metadata.file_type().is_symlink() || !metadata.is_file())
    {
        return Err("RO-LOCK-CONFIGURATION-WRITE-FAILED");
    }
    let bytes =
        serde_json::to_vec_pretty(profile).map_err(|_| "RO-LOCK-CONFIGURATION-WRITE-FAILED")?;
    let staging = parent.join(format!(".{PROFILE_FILE}.{}.staging", std::process::id()));
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&staging)
        .map_err(|_| "RO-LOCK-CONFIGURATION-WRITE-FAILED")?;
    let result = (|| {
        file.write_all(&bytes)
            .map_err(|_| "RO-LOCK-CONFIGURATION-WRITE-FAILED")?;
        file.write_all(b"\n")
            .map_err(|_| "RO-LOCK-CONFIGURATION-WRITE-FAILED")?;
        file.sync_all()
            .map_err(|_| "RO-LOCK-CONFIGURATION-WRITE-FAILED")?;
        drop(file);
        Ok(StagedProfile {
            path: staging.clone(),
        })
    })();
    if result.is_err() {
        let _ = fs::remove_file(&staging);
    }
    result
}

#[cfg(windows)]
fn replace_file(staging: &Path, destination: &Path) -> Result<(), &'static str> {
    use windows_sys::Win32::Storage::FileSystem::{
        MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW,
    };
    let staging = wide_path(staging);
    let destination = wide_path(destination);
    let replaced = unsafe {
        MoveFileExW(
            staging.as_ptr(),
            destination.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if replaced == 0 {
        Err("RO-LOCK-CONFIGURATION-WRITE-FAILED")
    } else {
        Ok(())
    }
}

#[cfg(not(windows))]
fn replace_file(staging: &Path, destination: &Path) -> Result<(), &'static str> {
    fs::rename(staging, destination).map_err(|_| "RO-LOCK-CONFIGURATION-WRITE-FAILED")
}

#[cfg(windows)]
fn wide_path(path: &Path) -> Vec<u16> {
    use std::os::windows::ffi::OsStrExt;
    path.as_os_str().encode_wide().chain(Some(0)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
    use std::sync::mpsc;

    static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(1);

    fn manager() -> ApplicationLockManager {
        let root = std::env::temp_dir().join(format!(
            "research-observatory-lock-test-{}-{}",
            std::process::id(),
            TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        ApplicationLockManager::new(&root)
    }

    #[test]
    fn profile_contract_rejects_unknown_timeout_and_sensitive_name_controls() {
        assert!(
            ApplicationLockProfile::new(Some("Local researcher".to_owned()), 15)
                .validate()
                .is_ok()
        );
        assert_eq!(
            ApplicationLockProfile::new(None, 7).validate(),
            Err("RO-LOCK-CONFIGURATION-INVALID")
        );
        assert_eq!(
            ApplicationLockProfile::new(Some("name\npath".to_owned()), 5).validate(),
            Err("RO-LOCK-CONFIGURATION-INVALID")
        );
        let unknown = serde_json::json!({
            "schemaVersion": "1.0",
            "documentType": "research-observatory-application-lock-profile",
            "profileName": null,
            "inactivityTimeoutMinutes": 0,
            "restartPolicy": "lock-when-inactivity-enabled",
            "lockAuthority": "desktop-native-supervisor",
            "reauthentication": REAUTHENTICATION,
            "protectedActionPolicy": "invalidate-generation-stop-core-discard-renderer-state",
            "durableOperationPolicy": "w1-stop-all-future-continuation-requires-explicit-allowlist",
            "threatBoundary": "application-session-protection-not-windows-account-isolation",
            "unexpected": true
        });
        assert!(serde_json::from_value::<ApplicationLockProfile>(unknown).is_err());
    }

    #[test]
    fn manual_lock_invalidates_actions_and_hides_profile_name() {
        let manager = manager();
        {
            let mut inner = manager.shared.lock().expect("lock mutex");
            inner.profile.profile_name = Some("Sensitive profile".to_owned());
        }
        let ticket = manager.begin_protected_action().expect("unlocked ticket");
        let (snapshot, changed) = manager.lock(ApplicationLockReason::Manual);
        assert!(changed);
        assert_eq!(snapshot.state, ApplicationLockState::Locked);
        assert_eq!(snapshot.profile_name, None);
        assert_eq!(
            manager.finish_protected_action(ticket),
            Err("RO-APPLICATION-LOCKED")
        );
        assert_eq!(
            manager.begin_protected_action(),
            Err("RO-APPLICATION-LOCKED")
        );
    }

    #[test]
    fn denied_cancelled_and_failed_core_paths_remain_locked() {
        let manager = manager();
        manager.lock(ApplicationLockReason::Manual);
        let cancelled = manager
            .complete_test_reauthentication(VerificationOutcome::Cancelled, true)
            .expect("cancelled attempt");
        assert_eq!(cancelled.outcome, VerificationOutcome::Cancelled);
        assert_eq!(cancelled.reason_code, "RO-LOCK-AUTH-CANCELLED");
        let denied = manager
            .complete_test_reauthentication(VerificationOutcome::Denied, true)
            .expect("denied attempt");
        assert_eq!(denied.outcome, VerificationOutcome::Denied);
        assert_eq!(denied.reason_code, "RO-LOCK-AUTH-DENIED");
        assert!(manager.status().retry_after_seconds > 0);
        manager.shared.lock().expect("lock mutex").retry_at = None;
        let core_failed = manager
            .complete_test_reauthentication(VerificationOutcome::Succeeded, false)
            .expect("core failure attempt");
        assert_eq!(core_failed.outcome, VerificationOutcome::Failed);
        assert_eq!(core_failed.reason_code, "RO-LOCK-CORE-UNAVAILABLE");
        assert_eq!(manager.status().state, ApplicationLockState::Locked);
    }

    #[test]
    fn provider_outcome_matrix_only_starts_core_and_unlocks_on_success() {
        for outcome in [
            VerificationOutcome::Cancelled,
            VerificationOutcome::Denied,
            VerificationOutcome::Unavailable,
            VerificationOutcome::Busy,
            VerificationOutcome::Failed,
            VerificationOutcome::Succeeded,
        ] {
            let manager = manager();
            manager.lock(ApplicationLockReason::Manual);
            let starts = AtomicUsize::new(0);
            let attempt = manager
                .reauthenticate_with(
                    &|| outcome,
                    || {
                        starts.fetch_add(1, Ordering::SeqCst);
                        RuntimeState::Ready
                    },
                    || {},
                )
                .expect("provider attempt");
            let succeeded = outcome == VerificationOutcome::Succeeded;
            assert_eq!(starts.load(Ordering::SeqCst), usize::from(succeeded));
            assert_eq!(
                attempt.snapshot.state,
                if succeeded {
                    ApplicationLockState::Unlocked
                } else {
                    ApplicationLockState::Locked
                }
            );
            assert_eq!(attempt.outcome, outcome);
        }
    }

    #[test]
    fn idle_deadline_locks_in_native_state_even_without_renderer_activity() {
        let manager = manager();
        {
            let mut inner = manager.shared.lock().expect("lock mutex");
            inner.profile.inactivity_timeout_minutes = 5;
            inner.last_activity = Instant::now() - Duration::from_secs(301);
        }
        let snapshot = manager.lock_if_idle().expect("idle lock");
        assert_eq!(snapshot.state, ApplicationLockState::Locked);
        assert_eq!(snapshot.reason, Some(ApplicationLockReason::Inactivity));
    }

    #[test]
    fn verified_same_user_unlocks_without_restoring_sensitive_identity_to_audit() {
        let manager = manager();
        manager.lock(ApplicationLockReason::Manual);
        let attempt = manager
            .complete_test_reauthentication(VerificationOutcome::Succeeded, true)
            .expect("successful attempt");
        assert_eq!(attempt.outcome, VerificationOutcome::Succeeded);
        assert_eq!(attempt.snapshot.state, ApplicationLockState::Unlocked);
        let serialized = serde_json::to_string(&manager.audit()).expect("audit json");
        assert!(!serialized.contains("profileName"));
        assert!(!serialized.contains("username"));
        assert!(!serialized.contains("project"));
    }

    #[test]
    fn concurrent_reauthentication_admits_one_prompt_and_preserves_backoff() {
        let manager = manager();
        manager.lock(ApplicationLockReason::Manual);
        let prompt_count = Arc::new(AtomicUsize::new(0));
        let (started_tx, started_rx) = mpsc::sync_channel(1);
        let (release_tx, release_rx) = mpsc::sync_channel(1);
        let worker_manager = manager.clone();
        let worker_count = Arc::clone(&prompt_count);
        let release_rx = Arc::new(Mutex::new(release_rx));
        let worker = std::thread::spawn(move || {
            let provider = || {
                worker_count.fetch_add(1, Ordering::SeqCst);
                started_tx.send(()).expect("signal prompt");
                release_rx
                    .lock()
                    .expect("release mutex")
                    .recv()
                    .expect("release prompt");
                VerificationOutcome::Denied
            };
            worker_manager.reauthenticate_with(&provider, || RuntimeState::Ready, || {})
        });
        started_rx.recv().expect("prompt admitted");
        let second_count = Arc::clone(&prompt_count);
        let busy = manager
            .reauthenticate_with(
                &|| {
                    second_count.fetch_add(1, Ordering::SeqCst);
                    VerificationOutcome::Succeeded
                },
                || RuntimeState::Ready,
                || {},
            )
            .expect("busy attempt");
        assert_eq!(busy.outcome, VerificationOutcome::Busy);
        assert_eq!(busy.reason_code, "RO-LOCK-RATE-LIMITED");
        release_tx.send(()).expect("release first prompt");
        let denied = worker
            .join()
            .expect("worker result")
            .expect("denied attempt");
        assert_eq!(denied.outcome, VerificationOutcome::Denied);
        assert_eq!(prompt_count.load(Ordering::SeqCst), 1);
        assert!(manager.status().retry_after_seconds > 0);
    }

    #[test]
    fn cancellation_and_core_failure_release_the_reauthentication_reservation() {
        let manager = manager();
        manager.lock(ApplicationLockReason::Manual);
        let cancelled = manager
            .reauthenticate_with(
                &|| VerificationOutcome::Cancelled,
                || RuntimeState::Ready,
                || {},
            )
            .expect("cancelled attempt");
        assert_eq!(cancelled.outcome, VerificationOutcome::Cancelled);
        let failed = manager
            .reauthenticate_with(
                &|| VerificationOutcome::Succeeded,
                || RuntimeState::RecoveryRequired,
                || {},
            )
            .expect("core failure attempt");
        assert_eq!(failed.outcome, VerificationOutcome::Failed);
        assert_eq!(failed.reason_code, "RO-LOCK-CORE-UNAVAILABLE");
        assert!(
            !manager
                .shared
                .lock()
                .expect("lock mutex")
                .reauthentication_in_progress
        );
        assert_eq!(manager.status().state, ApplicationLockState::Locked);
    }

    #[test]
    fn unlocked_and_stale_attempts_cannot_invoke_or_publish_provider_success() {
        let unlocked = manager();
        let provider_calls = AtomicUsize::new(0);
        let core_starts = AtomicUsize::new(0);
        let attempt = unlocked.reauthenticate_with(
            &|| {
                provider_calls.fetch_add(1, Ordering::SeqCst);
                VerificationOutcome::Succeeded
            },
            || {
                core_starts.fetch_add(1, Ordering::SeqCst);
                RuntimeState::Ready
            },
            || {},
        );
        assert_eq!(attempt, Err("RO-LOCK-AUTH-NOT-LOCKED"));
        assert_eq!(provider_calls.load(Ordering::SeqCst), 0);
        assert_eq!(core_starts.load(Ordering::SeqCst), 0);

        let manager = manager();
        manager.lock(ApplicationLockReason::Manual);
        let racing_manager = manager.clone();
        let stops = AtomicUsize::new(0);
        let stale = manager
            .reauthenticate_with(
                &|| VerificationOutcome::Succeeded,
                || {
                    racing_manager.lock(ApplicationLockReason::Manual);
                    RuntimeState::Ready
                },
                || {
                    stops.fetch_add(1, Ordering::SeqCst);
                },
            )
            .expect("stale attempt");
        assert_eq!(stale.outcome, VerificationOutcome::Failed);
        assert_eq!(stale.reason_code, "RO-LOCK-AUTH-STALE");
        assert_eq!(stale.snapshot.state, ApplicationLockState::Locked);
        assert_eq!(stops.load(Ordering::SeqCst), 1);
    }

    #[test]
    fn provider_panic_releases_reservation_and_preserves_locked_state() {
        let manager = manager();
        manager.lock(ApplicationLockReason::Manual);
        let result = std::panic::catch_unwind({
            let manager = manager.clone();
            move || {
                manager.reauthenticate_with(
                    &|| panic!("provider panic"),
                    || RuntimeState::Ready,
                    || {},
                )
            }
        });
        assert!(result.is_err());
        assert!(
            !manager
                .shared
                .lock()
                .expect("lock mutex")
                .reauthentication_in_progress
        );
        assert_eq!(manager.status().state, ApplicationLockState::Locked);
    }

    #[test]
    fn concurrent_lock_prevents_profile_publication_and_removes_staging() {
        let manager = manager();
        let (staged_tx, staged_rx) = mpsc::sync_channel(1);
        let (release_tx, release_rx) = mpsc::sync_channel(1);
        let worker_manager = manager.clone();
        let worker = std::thread::spawn(move || {
            worker_manager.configure_with_hook(Some("Local researcher".to_owned()), 15, || {
                staged_tx.send(()).expect("profile staged");
                release_rx.recv().expect("release profile");
            })
        });
        staged_rx.recv().expect("profile stage reached");
        manager.lock(ApplicationLockReason::Manual);
        release_tx.send(()).expect("release staged profile");
        assert_eq!(
            worker.join().expect("profile worker"),
            Err("RO-APPLICATION-LOCKED")
        );
        assert!(!manager.profile_path.exists());
        let parent = manager.profile_path.parent().expect("profile parent");
        assert!(
            fs::read_dir(parent)
                .expect("security directory")
                .all(|entry| !entry
                    .expect("directory entry")
                    .file_name()
                    .to_string_lossy()
                    .contains("staging"))
        );
    }
}
