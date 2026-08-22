use std::collections::VecDeque;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

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
        let profile_name = profile_name
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty());
        let profile = ApplicationLockProfile::new(profile_name, inactivity_timeout_minutes);
        profile.validate()?;
        {
            let inner = self.shared.lock().expect("lock mutex poisoned");
            if inner.state != ApplicationLockState::Unlocked {
                return Err("RO-APPLICATION-LOCKED");
            }
        }
        write_profile(&self.profile_path, &profile)?;
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.state != ApplicationLockState::Unlocked {
            return Err("RO-APPLICATION-LOCKED");
        }
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
    ) -> Result<ApplicationLockSnapshot, &'static str> {
        {
            let mut inner = self.shared.lock().expect("lock mutex poisoned");
            if inner.state == ApplicationLockState::Unlocked {
                return Ok(inner.snapshot());
            }
            if inner
                .retry_at
                .is_some_and(|deadline| deadline > Instant::now())
            {
                inner.record("application-unlock", "denied", "RO-LOCK-RATE-LIMITED");
                return Err("RO-LOCK-RATE-LIMITED");
            }
        }

        match verify_current_windows_user() {
            ReauthenticationResult::Cancelled => {
                self.shared.lock().expect("lock mutex poisoned").record(
                    "application-unlock",
                    "cancelled",
                    "RO-LOCK-AUTH-CANCELLED",
                );
                Err("RO-LOCK-AUTH-CANCELLED")
            }
            ReauthenticationResult::Denied => {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.failed_attempts = inner.failed_attempts.saturating_add(1);
                let exponent = inner.failed_attempts.saturating_sub(1).min(5);
                inner.retry_at = Some(Instant::now() + Duration::from_secs(1_u64 << exponent));
                inner.record("application-unlock", "denied", "RO-LOCK-AUTH-DENIED");
                Err("RO-LOCK-AUTH-DENIED")
            }
            ReauthenticationResult::Verified => {
                let runtime = supervisor.start();
                if runtime.state != RuntimeState::Ready {
                    self.shared.lock().expect("lock mutex poisoned").record(
                        "application-unlock",
                        "failed",
                        "RO-LOCK-CORE-UNAVAILABLE",
                    );
                    return Err("RO-LOCK-CORE-UNAVAILABLE");
                }
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.state = ApplicationLockState::Unlocked;
                inner.reason = None;
                inner.failed_attempts = 0;
                inner.retry_at = None;
                inner.last_activity = Instant::now();
                inner.record("application-unlock", "succeeded", "RO-LOCK-UNLOCKED");
                Ok(inner.snapshot())
            }
        }
    }

    #[cfg(test)]
    fn complete_test_reauthentication(
        &self,
        result: ReauthenticationResult,
        core_ready: bool,
    ) -> Result<ApplicationLockSnapshot, &'static str> {
        match result {
            ReauthenticationResult::Cancelled => Err("RO-LOCK-AUTH-CANCELLED"),
            ReauthenticationResult::Denied => {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.failed_attempts = inner.failed_attempts.saturating_add(1);
                inner.retry_at = Some(Instant::now() + Duration::from_secs(1));
                Err("RO-LOCK-AUTH-DENIED")
            }
            ReauthenticationResult::Verified if !core_ready => Err("RO-LOCK-CORE-UNAVAILABLE"),
            ReauthenticationResult::Verified => {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.state = ApplicationLockState::Unlocked;
                inner.reason = None;
                inner.failed_attempts = 0;
                inner.retry_at = None;
                inner.last_activity = Instant::now();
                inner.record("application-unlock", "succeeded", "RO-LOCK-UNLOCKED");
                Ok(inner.snapshot())
            }
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

fn write_profile(path: &Path, profile: &ApplicationLockProfile) -> Result<(), &'static str> {
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
        replace_file(&staging, path)
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

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ReauthenticationResult {
    Verified,
    Cancelled,
    Denied,
}

#[cfg(windows)]
fn verify_current_windows_user() -> ReauthenticationResult {
    use std::ffi::c_void;
    use std::ptr::{null, null_mut};
    use windows_sys::Win32::Foundation::{CloseHandle, ERROR_CANCELLED, HANDLE};
    use windows_sys::Win32::Security::Credentials::{
        CREDUI_FLAGS_ALWAYS_SHOW_UI, CREDUI_FLAGS_COMPLETE_USERNAME, CREDUI_FLAGS_DO_NOT_PERSIST,
        CREDUI_FLAGS_EXCLUDE_CERTIFICATES, CredUIParseUserNameW, CredUIPromptForCredentialsW,
    };
    use windows_sys::Win32::Security::{
        EqualSid, GetTokenInformation, LOGON32_LOGON_INTERACTIVE, LOGON32_PROVIDER_DEFAULT,
        LogonUserW, TOKEN_QUERY, TOKEN_USER, TokenUser,
    };
    use windows_sys::Win32::System::Threading::{GetCurrentProcess, OpenProcessToken};

    struct SecretWide(Vec<u16>);
    impl Drop for SecretWide {
        fn drop(&mut self) {
            for value in &mut self.0 {
                unsafe { std::ptr::write_volatile(value, 0) };
            }
        }
    }
    struct OwnedHandle(HANDLE);
    impl Drop for OwnedHandle {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe { CloseHandle(self.0) };
            }
        }
    }
    fn token_sid(handle: HANDLE) -> Option<Vec<usize>> {
        let mut length = 0_u32;
        unsafe { GetTokenInformation(handle, TokenUser, null_mut(), 0, &mut length) };
        if length == 0 {
            return None;
        }
        let words = (length as usize).div_ceil(std::mem::size_of::<usize>());
        let mut buffer = vec![0_usize; words];
        if unsafe {
            GetTokenInformation(
                handle,
                TokenUser,
                buffer.as_mut_ptr().cast::<c_void>(),
                length,
                &mut length,
            )
        } == 0
        {
            return None;
        }
        Some(buffer)
    }

    let target: Vec<u16> = "Research Observatory local application lock\0"
        .encode_utf16()
        .collect();
    let mut username = SecretWide(vec![0_u16; 514]);
    let mut password = SecretWide(vec![0_u16; 256]);
    let status = unsafe {
        CredUIPromptForCredentialsW(
            null(),
            target.as_ptr(),
            null(),
            0,
            username.0.as_mut_ptr(),
            username.0.len() as u32,
            password.0.as_mut_ptr(),
            password.0.len() as u32,
            null_mut(),
            CREDUI_FLAGS_ALWAYS_SHOW_UI
                | CREDUI_FLAGS_DO_NOT_PERSIST
                | CREDUI_FLAGS_EXCLUDE_CERTIFICATES
                | CREDUI_FLAGS_COMPLETE_USERNAME,
        )
    };
    if status == ERROR_CANCELLED {
        return ReauthenticationResult::Cancelled;
    }
    if status != 0 {
        return ReauthenticationResult::Denied;
    }

    let mut user = SecretWide(vec![0_u16; 514]);
    let mut domain = SecretWide(vec![0_u16; 514]);
    if unsafe {
        CredUIParseUserNameW(
            username.0.as_ptr(),
            user.0.as_mut_ptr(),
            user.0.len() as u32,
            domain.0.as_mut_ptr(),
            domain.0.len() as u32,
        )
    } != 0
    {
        return ReauthenticationResult::Denied;
    }

    let mut submitted = OwnedHandle(null_mut());
    if unsafe {
        LogonUserW(
            user.0.as_ptr(),
            domain.0.as_ptr(),
            password.0.as_ptr(),
            LOGON32_LOGON_INTERACTIVE,
            LOGON32_PROVIDER_DEFAULT,
            &mut submitted.0,
        )
    } == 0
    {
        return ReauthenticationResult::Denied;
    }
    let mut current = OwnedHandle(null_mut());
    if unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut current.0) } == 0 {
        return ReauthenticationResult::Denied;
    }
    let Some(submitted_sid) = token_sid(submitted.0) else {
        return ReauthenticationResult::Denied;
    };
    let Some(current_sid) = token_sid(current.0) else {
        return ReauthenticationResult::Denied;
    };
    let submitted_user = unsafe { &*(submitted_sid.as_ptr().cast::<TOKEN_USER>()) };
    let current_user = unsafe { &*(current_sid.as_ptr().cast::<TOKEN_USER>()) };
    if unsafe { EqualSid(submitted_user.User.Sid, current_user.User.Sid) } == 0 {
        ReauthenticationResult::Denied
    } else {
        ReauthenticationResult::Verified
    }
}

#[cfg(not(windows))]
fn verify_current_windows_user() -> ReauthenticationResult {
    ReauthenticationResult::Denied
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manager() -> ApplicationLockManager {
        let root = std::env::temp_dir().join(format!(
            "research-observatory-lock-test-{}-{}",
            std::process::id(),
            Instant::now().elapsed().as_nanos()
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
        assert_eq!(
            manager.complete_test_reauthentication(ReauthenticationResult::Cancelled, true),
            Err("RO-LOCK-AUTH-CANCELLED")
        );
        assert_eq!(
            manager.complete_test_reauthentication(ReauthenticationResult::Denied, true),
            Err("RO-LOCK-AUTH-DENIED")
        );
        assert!(manager.status().retry_after_seconds > 0);
        assert_eq!(
            manager.complete_test_reauthentication(ReauthenticationResult::Verified, false),
            Err("RO-LOCK-CORE-UNAVAILABLE")
        );
        assert_eq!(manager.status().state, ApplicationLockState::Locked);
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
        let snapshot = manager
            .complete_test_reauthentication(ReauthenticationResult::Verified, true)
            .expect("unlock");
        assert_eq!(snapshot.state, ApplicationLockState::Unlocked);
        let serialized = serde_json::to_string(&manager.audit()).expect("audit json");
        assert!(!serialized.contains("profileName"));
        assert!(!serialized.contains("username"));
        assert!(!serialized.contains("project"));
    }
}
