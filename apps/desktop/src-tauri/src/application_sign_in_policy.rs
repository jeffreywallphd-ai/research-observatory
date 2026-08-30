use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub(crate) const LEGACY_PROFILE_FILE: &str = "application-lock-profile.v1.json";
pub(crate) const POLICY_FILE: &str = "application-sign-in-policy.v1.json";
const MAX_POLICY_BYTES: u64 = 16 * 1024;

const DOCUMENT_TYPE: &str = "research-observatory-application-sign-in-policy";
const LEGACY_DOCUMENT_TYPE: &str = "research-observatory-application-lock-profile";
const RESTART_POLICY: &str = "lock-when-inactivity-enabled";
const LOCK_AUTHORITY: &str = "desktop-native-supervisor";
const TRANSITION_AUTHORITY: &str = "native-provider-proof-confirmation-cas";
const LEGACY_REAUTHENTICATION: &str = "windows-current-user-credentials-same-sid";
const PROTECTED_ACTION_POLICY: &str = "invalidate-generation-stop-core-discard-renderer-state";
const DURABLE_OPERATION_POLICY: &str =
    "w1-stop-all-future-continuation-requires-explicit-allowlist";
const THREAT_BOUNDARY: &str = "application-session-protection-not-windows-account-isolation";

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum SignInMode {
    None,
    WindowsPassword,
    WindowsHello,
}

impl SignInMode {
    pub(crate) fn is_protected(self) -> bool {
        self != Self::None
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct SignInPolicy {
    schema_version: String,
    document_type: String,
    revision: u64,
    pub(crate) mode: SignInMode,
    pub(crate) profile_name: Option<String>,
    pub(crate) inactivity_timeout_minutes: u8,
    restart_policy: String,
    lock_authority: String,
    transition_authority: String,
    protected_action_policy: String,
    durable_operation_policy: String,
    threat_boundary: String,
}

impl SignInPolicy {
    pub(crate) fn explicit_none() -> Self {
        Self::new(1, SignInMode::None, None, 0)
    }

    pub(crate) fn new(
        revision: u64,
        mode: SignInMode,
        profile_name: Option<String>,
        inactivity_timeout_minutes: u8,
    ) -> Self {
        Self {
            schema_version: "1.0".to_owned(),
            document_type: DOCUMENT_TYPE.to_owned(),
            revision,
            mode,
            profile_name,
            inactivity_timeout_minutes,
            restart_policy: RESTART_POLICY.to_owned(),
            lock_authority: LOCK_AUTHORITY.to_owned(),
            transition_authority: TRANSITION_AUTHORITY.to_owned(),
            protected_action_policy: PROTECTED_ACTION_POLICY.to_owned(),
            durable_operation_policy: DURABLE_OPERATION_POLICY.to_owned(),
            threat_boundary: THREAT_BOUNDARY.to_owned(),
        }
    }

    pub(crate) fn normalized_target(
        revision: u64,
        mode: SignInMode,
        profile_name: Option<String>,
        inactivity_timeout_minutes: u8,
    ) -> Result<Self, &'static str> {
        let profile_name = profile_name
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty());
        let policy = Self::new(revision, mode, profile_name, inactivity_timeout_minutes);
        policy.validate()?;
        Ok(policy)
    }

    pub(crate) fn revision(&self) -> u64 {
        self.revision
    }

    pub(crate) fn validate(&self) -> Result<(), &'static str> {
        if self.schema_version != "1.0"
            || self.document_type != DOCUMENT_TYPE
            || self.revision == 0
            || self.restart_policy != RESTART_POLICY
            || self.lock_authority != LOCK_AUTHORITY
            || self.transition_authority != TRANSITION_AUTHORITY
            || self.protected_action_policy != PROTECTED_ACTION_POLICY
            || self.durable_operation_policy != DURABLE_OPERATION_POLICY
            || self.threat_boundary != THREAT_BOUNDARY
            || !matches!(self.inactivity_timeout_minutes, 0 | 5 | 15 | 30 | 60)
            || (self.mode == SignInMode::None && self.inactivity_timeout_minutes != 0)
        {
            return Err("RO-SIGN-IN-POLICY-INVALID");
        }
        validate_profile_name(self.profile_name.as_deref())
    }

    pub(crate) fn canonical_bytes(&self) -> Result<Vec<u8>, &'static str> {
        self.validate()?;
        let mut bytes =
            serde_json::to_vec_pretty(self).map_err(|_| "RO-SIGN-IN-POLICY-WRITE-FAILED")?;
        bytes.push(b'\n');
        Ok(bytes)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct LegacyApplicationLockProfile {
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

impl LegacyApplicationLockProfile {
    fn validate(&self) -> Result<(), &'static str> {
        if self.schema_version != "1.0"
            || self.document_type != LEGACY_DOCUMENT_TYPE
            || self.restart_policy != RESTART_POLICY
            || self.lock_authority != LOCK_AUTHORITY
            || self.reauthentication != LEGACY_REAUTHENTICATION
            || self.protected_action_policy != PROTECTED_ACTION_POLICY
            || self.durable_operation_policy != DURABLE_OPERATION_POLICY
            || self.threat_boundary != THREAT_BOUNDARY
            || !matches!(self.inactivity_timeout_minutes, 0 | 5 | 15 | 30 | 60)
        {
            return Err("RO-SIGN-IN-POLICY-INVALID");
        }
        validate_profile_name(self.profile_name.as_deref())
    }

    fn migrate(self) -> SignInPolicy {
        SignInPolicy::new(
            1,
            SignInMode::WindowsPassword,
            self.profile_name,
            self.inactivity_timeout_minutes,
        )
    }
}

fn validate_profile_name(value: Option<&str>) -> Result<(), &'static str> {
    if value.is_some_and(|name| {
        name.is_empty() || name.chars().count() > 80 || name.chars().any(char::is_control)
    }) {
        return Err("RO-SIGN-IN-POLICY-INVALID");
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum PolicyLoadState {
    Valid,
    Migrated,
    Invalid,
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
struct FileAuthority {
    present: bool,
    sha256: Option<String>,
    length: u64,
    volume_serial: u64,
    file_index: u64,
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub(crate) struct PolicySourceAuthority {
    canonical: FileAuthority,
    legacy: FileAuthority,
    parent: FileAuthority,
}

#[derive(Clone, Debug)]
pub(crate) struct LoadedPolicy {
    pub(crate) policy: SignInPolicy,
    pub(crate) state: PolicyLoadState,
    pub(crate) source: PolicySourceAuthority,
}

#[derive(Clone, Debug)]
pub(crate) struct PolicyStore {
    security_dir: PathBuf,
    canonical_path: PathBuf,
    legacy_path: PathBuf,
    mutex_name: String,
}

#[cfg(windows)]
pub(crate) struct ApplicationInstanceGuard {
    handle: isize,
}

#[cfg(windows)]
impl ApplicationInstanceGuard {
    pub(crate) fn acquire(application_data: &Path) -> Result<Self, &'static str> {
        use std::os::windows::ffi::OsStrExt;
        use windows_sys::Win32::Foundation::{CloseHandle, ERROR_ALREADY_EXISTS, GetLastError};
        use windows_sys::Win32::System::Threading::CreateMutexW;

        let stable_root = stable_application_data_path(application_data);
        let normalized = stable_root.to_string_lossy().to_lowercase();
        let name = format!(
            "Global\\ResearchObservatory.DesktopInstance.{}",
            sha256_hex(normalized.as_bytes())
        );
        let name: Vec<u16> = std::ffi::OsStr::new(&name)
            .encode_wide()
            .chain(Some(0))
            .collect();
        // Object lifetime, not thread-affine mutex ownership, is the lease. Holding
        // the only handle keeps the name occupied and lets any final Arc holder close
        // it safely; process termination closes it automatically.
        let handle = unsafe { CreateMutexW(std::ptr::null(), 0, name.as_ptr()) };
        if handle.is_null() {
            return Err("RO-DESKTOP-INSTANCE-UNAVAILABLE");
        }
        if unsafe { GetLastError() } == ERROR_ALREADY_EXISTS {
            unsafe { CloseHandle(handle) };
            return Err("RO-DESKTOP-ALREADY-RUNNING");
        }
        Ok(Self {
            handle: handle as isize,
        })
    }
}

#[cfg(windows)]
impl Drop for ApplicationInstanceGuard {
    fn drop(&mut self) {
        unsafe {
            let handle = self.handle as windows_sys::Win32::Foundation::HANDLE;
            windows_sys::Win32::Foundation::CloseHandle(handle);
        }
    }
}

#[cfg(not(windows))]
pub(crate) struct ApplicationInstanceGuard;

#[cfg(not(windows))]
impl ApplicationInstanceGuard {
    pub(crate) fn acquire(_application_data: &Path) -> Result<Self, &'static str> {
        Ok(Self)
    }
}

impl PolicyStore {
    pub(crate) fn new(application_data: &Path) -> Self {
        let application_data = stable_application_data_path(application_data);
        let security_dir = application_data.join("security");
        let canonical_path = security_dir.join(POLICY_FILE);
        let legacy_path = security_dir.join(LEGACY_PROFILE_FILE);
        let normalized = canonical_path.to_string_lossy().to_lowercase();
        let mutex_name = format!(
            "Local\\ResearchObservatory.SignInPolicy.{}",
            sha256_hex(normalized.as_bytes())
        );
        Self {
            security_dir,
            canonical_path,
            legacy_path,
            mutex_name,
        }
    }

    #[cfg(test)]
    pub(crate) fn canonical_path(&self) -> &Path {
        &self.canonical_path
    }

    pub(crate) fn initialize(&self) -> LoadedPolicy {
        if self.ensure_security_dir().is_err() {
            return self.invalid_loaded();
        }
        let Ok(_guard) = self.lock() else {
            return self.invalid_loaded();
        };
        self.cleanup_staging();
        let Ok(source) = self.source_authority() else {
            return self.invalid_loaded();
        };
        match read_bounded_file(&self.canonical_path) {
            Ok(Some(bytes)) => match parse_policy(&bytes) {
                Ok(policy) => LoadedPolicy {
                    policy,
                    state: PolicyLoadState::Valid,
                    source,
                },
                Err(_) => LoadedPolicy {
                    policy: SignInPolicy::explicit_none(),
                    state: PolicyLoadState::Invalid,
                    source,
                },
            },
            Ok(None) => self.initialize_without_canonical(source),
            Err(_) => LoadedPolicy {
                policy: SignInPolicy::explicit_none(),
                state: PolicyLoadState::Invalid,
                source,
            },
        }
    }

    fn initialize_without_canonical(&self, source: PolicySourceAuthority) -> LoadedPolicy {
        let (policy, state) = match read_bounded_file(&self.legacy_path) {
            Ok(Some(bytes)) => match parse_legacy(&bytes) {
                Ok(legacy) => (legacy.migrate(), PolicyLoadState::Migrated),
                Err(_) => {
                    return LoadedPolicy {
                        policy: SignInPolicy::explicit_none(),
                        state: PolicyLoadState::Invalid,
                        source,
                    };
                }
            },
            Ok(None) => (SignInPolicy::explicit_none(), PolicyLoadState::Valid),
            Err(_) => {
                return LoadedPolicy {
                    policy: SignInPolicy::explicit_none(),
                    state: PolicyLoadState::Invalid,
                    source,
                };
            }
        };
        let Ok(staged) = self.stage(&policy) else {
            return LoadedPolicy {
                policy,
                state: PolicyLoadState::Invalid,
                source,
            };
        };
        if self.source_authority().ok().as_ref() != Some(&source)
            || staged.publish_new(&self.canonical_path).is_err()
        {
            return LoadedPolicy {
                policy,
                state: PolicyLoadState::Invalid,
                source,
            };
        }
        let source = self.source_authority().unwrap_or_default();
        LoadedPolicy {
            policy,
            state,
            source,
        }
    }

    fn invalid_loaded(&self) -> LoadedPolicy {
        LoadedPolicy {
            policy: SignInPolicy::explicit_none(),
            state: PolicyLoadState::Invalid,
            source: self.source_authority().unwrap_or_default(),
        }
    }

    pub(crate) fn lock(&self) -> Result<CrossProcessGuard, &'static str> {
        CrossProcessGuard::acquire(&self.mutex_name)
    }

    pub(crate) fn source_authority(&self) -> Result<PolicySourceAuthority, &'static str> {
        Ok(PolicySourceAuthority {
            canonical: file_authority(&self.canonical_path)?,
            legacy: file_authority(&self.legacy_path)?,
            parent: file_authority(&self.security_dir)?,
        })
    }

    pub(crate) fn stage(&self, policy: &SignInPolicy) -> Result<StagedPolicy, &'static str> {
        self.ensure_security_dir()?;
        let bytes = policy.canonical_bytes()?;
        let random = secure_random_hex::<16>()?;
        let path = self
            .security_dir
            .join(format!(".{POLICY_FILE}.{random}.staging"));
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&path)
            .map_err(|_| "RO-SIGN-IN-POLICY-WRITE-FAILED")?;
        let result = (|| {
            file.write_all(&bytes)
                .map_err(|_| "RO-SIGN-IN-POLICY-WRITE-FAILED")?;
            file.sync_all()
                .map_err(|_| "RO-SIGN-IN-POLICY-WRITE-FAILED")?;
            Ok(StagedPolicy { path: path.clone() })
        })();
        if result.is_err() {
            let _ = fs::remove_file(&path);
        }
        result
    }

    pub(crate) fn publish(
        &self,
        staged: StagedPolicy,
        expected: &PolicySourceAuthority,
    ) -> Result<PolicySourceAuthority, &'static str> {
        self.ensure_security_dir()?;
        let current = self.source_authority()?;
        if &current != expected {
            return Err("RO-SIGN-IN-POLICY-CONFLICT");
        }
        if current.canonical.present {
            staged.publish_replace(&self.canonical_path)?;
        } else {
            staged.publish_new(&self.canonical_path)?;
        }
        self.source_authority()
    }

    pub(crate) fn committed_source(
        &self,
        expected: &SignInPolicy,
    ) -> Result<Option<PolicySourceAuthority>, &'static str> {
        let Some(bytes) = read_bounded_file(&self.canonical_path)? else {
            return Ok(None);
        };
        if bytes != expected.canonical_bytes()? {
            return Ok(None);
        }
        parse_policy(&bytes)?;
        self.source_authority().map(Some)
    }

    fn ensure_security_dir(&self) -> Result<(), &'static str> {
        fs::create_dir_all(&self.security_dir).map_err(|_| "RO-SIGN-IN-POLICY-WRITE-FAILED")?;
        reject_reparse(&self.security_dir)
    }

    fn cleanup_staging(&self) {
        let Ok(entries) = fs::read_dir(&self.security_dir) else {
            return;
        };
        let prefix = format!(".{POLICY_FILE}.");
        for entry in entries.flatten() {
            let name = entry.file_name();
            let name = name.to_string_lossy();
            if name.starts_with(&prefix) && name.ends_with(".staging") {
                let _ = fs::remove_file(entry.path());
            }
        }
    }
}

fn stable_application_data_path(path: &Path) -> PathBuf {
    let absolute = std::path::absolute(path).unwrap_or_else(|_| path.to_path_buf());
    let mut cursor = absolute.as_path();
    let mut missing = Vec::new();
    loop {
        if let Ok(mut canonical) = dunce::canonicalize(cursor) {
            for component in missing.iter().rev() {
                canonical.push(component);
            }
            return canonical;
        }
        let Some(name) = cursor.file_name() else {
            return absolute;
        };
        missing.push(name.to_os_string());
        let Some(parent) = cursor.parent() else {
            return absolute;
        };
        cursor = parent;
    }
}

fn parse_policy(bytes: &[u8]) -> Result<SignInPolicy, &'static str> {
    let policy: SignInPolicy =
        serde_json::from_slice(bytes).map_err(|_| "RO-SIGN-IN-POLICY-INVALID")?;
    policy.validate()?;
    Ok(policy)
}

fn parse_legacy(bytes: &[u8]) -> Result<LegacyApplicationLockProfile, &'static str> {
    let profile: LegacyApplicationLockProfile =
        serde_json::from_slice(bytes).map_err(|_| "RO-SIGN-IN-POLICY-INVALID")?;
    profile.validate()?;
    Ok(profile)
}

fn file_authority(path: &Path) -> Result<FileAuthority, &'static str> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(FileAuthority::default());
        }
        Err(_) => return Err("RO-SIGN-IN-POLICY-INVALID"),
    };
    if is_reparse(&metadata) {
        return Err("RO-SIGN-IN-POLICY-INVALID");
    }
    if metadata.is_dir() {
        let directory = open_directory_no_follow(path)?;
        let opened = directory
            .metadata()
            .map_err(|_| "RO-SIGN-IN-POLICY-INVALID")?;
        if is_reparse(&opened) || !opened.is_dir() {
            return Err("RO-SIGN-IN-POLICY-INVALID");
        }
        let (volume_serial, file_index) = file_identity(&directory, &opened)?;
        return Ok(FileAuthority {
            present: true,
            length: 0,
            volume_serial,
            file_index,
            sha256: None,
        });
    }
    if !metadata.is_file() || metadata.len() > MAX_POLICY_BYTES {
        return Err("RO-SIGN-IN-POLICY-INVALID");
    }
    let mut file = open_no_follow(path)?;
    let opened = file.metadata().map_err(|_| "RO-SIGN-IN-POLICY-INVALID")?;
    if is_reparse(&opened) || !opened.is_file() || opened.len() > MAX_POLICY_BYTES {
        return Err("RO-SIGN-IN-POLICY-INVALID");
    }
    let (volume_serial, file_index) = file_identity(&file, &opened)?;
    let mut bytes = Vec::with_capacity(opened.len() as usize);
    file.read_to_end(&mut bytes)
        .map_err(|_| "RO-SIGN-IN-POLICY-INVALID")?;
    if bytes.len() as u64 != opened.len() {
        return Err("RO-SIGN-IN-POLICY-INVALID");
    }
    Ok(FileAuthority {
        present: true,
        sha256: Some(sha256_hex(&bytes)),
        length: bytes.len() as u64,
        volume_serial,
        file_index,
    })
}

#[cfg(windows)]
fn open_directory_no_follow(path: &Path) -> Result<File, &'static str> {
    use std::os::windows::fs::OpenOptionsExt;
    use windows_sys::Win32::Storage::FileSystem::{
        FILE_FLAG_BACKUP_SEMANTICS, FILE_FLAG_OPEN_REPARSE_POINT, FILE_SHARE_DELETE,
        FILE_SHARE_READ, FILE_SHARE_WRITE,
    };

    OpenOptions::new()
        .read(true)
        .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE)
        .custom_flags(FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT)
        .open(path)
        .map_err(|_| "RO-SIGN-IN-POLICY-INVALID")
}

#[cfg(not(windows))]
fn open_directory_no_follow(path: &Path) -> Result<File, &'static str> {
    File::open(path).map_err(|_| "RO-SIGN-IN-POLICY-INVALID")
}

#[cfg(windows)]
fn file_identity(file: &File, _metadata: &fs::Metadata) -> Result<(u64, u64), &'static str> {
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Storage::FileSystem::{
        BY_HANDLE_FILE_INFORMATION, GetFileInformationByHandle,
    };

    let mut information = std::mem::MaybeUninit::<BY_HANDLE_FILE_INFORMATION>::zeroed();
    let ok = unsafe { GetFileInformationByHandle(file.as_raw_handle(), information.as_mut_ptr()) };
    if ok == 0 {
        return Err("RO-SIGN-IN-POLICY-INVALID");
    }
    let information = unsafe { information.assume_init() };
    let file_index =
        (u64::from(information.nFileIndexHigh) << 32) | u64::from(information.nFileIndexLow);
    Ok((u64::from(information.dwVolumeSerialNumber), file_index))
}

#[cfg(not(windows))]
fn file_identity(_file: &File, metadata: &fs::Metadata) -> Result<(u64, u64), &'static str> {
    use std::os::unix::fs::MetadataExt;

    Ok((metadata.dev(), metadata.ino()))
}

fn read_bounded_file(path: &Path) -> Result<Option<Vec<u8>>, &'static str> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err("RO-SIGN-IN-POLICY-INVALID"),
    };
    if is_reparse(&metadata) || !metadata.is_file() || metadata.len() > MAX_POLICY_BYTES {
        return Err("RO-SIGN-IN-POLICY-INVALID");
    }
    let mut file = open_no_follow(path)?;
    let opened = file.metadata().map_err(|_| "RO-SIGN-IN-POLICY-INVALID")?;
    if is_reparse(&opened) || !opened.is_file() || opened.len() > MAX_POLICY_BYTES {
        return Err("RO-SIGN-IN-POLICY-INVALID");
    }
    let mut bytes = Vec::with_capacity(opened.len() as usize);
    file.read_to_end(&mut bytes)
        .map_err(|_| "RO-SIGN-IN-POLICY-INVALID")?;
    if bytes.len() as u64 != opened.len() {
        return Err("RO-SIGN-IN-POLICY-INVALID");
    }
    Ok(Some(bytes))
}

#[cfg(windows)]
fn open_no_follow(path: &Path) -> Result<File, &'static str> {
    use std::os::windows::fs::OpenOptionsExt;
    use windows_sys::Win32::Storage::FileSystem::FILE_FLAG_OPEN_REPARSE_POINT;

    OpenOptions::new()
        .read(true)
        .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
        .open(path)
        .map_err(|_| "RO-SIGN-IN-POLICY-INVALID")
}

#[cfg(not(windows))]
fn open_no_follow(path: &Path) -> Result<File, &'static str> {
    File::open(path).map_err(|_| "RO-SIGN-IN-POLICY-INVALID")
}

fn reject_reparse(path: &Path) -> Result<(), &'static str> {
    let metadata = fs::symlink_metadata(path).map_err(|_| "RO-SIGN-IN-POLICY-WRITE-FAILED")?;
    if is_reparse(&metadata) || !metadata.is_dir() {
        Err("RO-SIGN-IN-POLICY-WRITE-FAILED")
    } else {
        Ok(())
    }
}

#[cfg(windows)]
fn is_reparse(metadata: &fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;
    use windows_sys::Win32::Storage::FileSystem::FILE_ATTRIBUTE_REPARSE_POINT;

    metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
}

#[cfg(not(windows))]
fn is_reparse(metadata: &fs::Metadata) -> bool {
    metadata.file_type().is_symlink()
}

pub(crate) struct StagedPolicy {
    path: PathBuf,
}

impl StagedPolicy {
    fn publish_new(mut self, destination: &Path) -> Result<(), &'static str> {
        publish_file(&self.path, destination, false)?;
        self.path = PathBuf::new();
        Ok(())
    }

    fn publish_replace(mut self, destination: &Path) -> Result<(), &'static str> {
        publish_file(&self.path, destination, true)?;
        self.path = PathBuf::new();
        Ok(())
    }
}

impl Drop for StagedPolicy {
    fn drop(&mut self) {
        if !self.path.as_os_str().is_empty() {
            let _ = fs::remove_file(&self.path);
        }
    }
}

#[cfg(windows)]
fn publish_file(staging: &Path, destination: &Path, replace: bool) -> Result<(), &'static str> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW,
    };

    reject_reparse(
        destination
            .parent()
            .ok_or("RO-SIGN-IN-POLICY-WRITE-FAILED")?,
    )?;
    if let Ok(metadata) = fs::symlink_metadata(destination)
        && (is_reparse(&metadata) || !metadata.is_file())
    {
        return Err("RO-SIGN-IN-POLICY-WRITE-FAILED");
    }
    let staging: Vec<u16> = staging.as_os_str().encode_wide().chain(Some(0)).collect();
    let destination: Vec<u16> = destination
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    let flags = MOVEFILE_WRITE_THROUGH
        | if replace {
            MOVEFILE_REPLACE_EXISTING
        } else {
            0
        };
    let moved = unsafe { MoveFileExW(staging.as_ptr(), destination.as_ptr(), flags) };
    if moved == 0 {
        Err("RO-SIGN-IN-POLICY-WRITE-FAILED")
    } else {
        Ok(())
    }
}

#[cfg(not(windows))]
fn publish_file(staging: &Path, destination: &Path, replace: bool) -> Result<(), &'static str> {
    if replace {
        fs::rename(staging, destination).map_err(|_| "RO-SIGN-IN-POLICY-WRITE-FAILED")
    } else {
        fs::hard_link(staging, destination).map_err(|_| "RO-SIGN-IN-POLICY-WRITE-FAILED")?;
        fs::remove_file(staging).map_err(|_| "RO-SIGN-IN-POLICY-WRITE-FAILED")
    }
}

#[cfg(windows)]
pub(crate) struct CrossProcessGuard {
    handle: windows_sys::Win32::Foundation::HANDLE,
}

#[cfg(windows)]
impl CrossProcessGuard {
    fn acquire(name: &str) -> Result<Self, &'static str> {
        use std::os::windows::ffi::OsStrExt;
        use windows_sys::Win32::Foundation::{WAIT_ABANDONED, WAIT_OBJECT_0};
        use windows_sys::Win32::System::Threading::{CreateMutexW, INFINITE, WaitForSingleObject};

        let name: Vec<u16> = std::ffi::OsStr::new(name)
            .encode_wide()
            .chain(Some(0))
            .collect();
        let handle = unsafe { CreateMutexW(std::ptr::null(), 0, name.as_ptr()) };
        if handle.is_null() {
            return Err("RO-SIGN-IN-POLICY-LOCK-FAILED");
        }
        let wait = unsafe { WaitForSingleObject(handle, INFINITE) };
        if wait != WAIT_OBJECT_0 && wait != WAIT_ABANDONED {
            unsafe { windows_sys::Win32::Foundation::CloseHandle(handle) };
            return Err("RO-SIGN-IN-POLICY-LOCK-FAILED");
        }
        Ok(Self { handle })
    }
}

#[cfg(windows)]
impl Drop for CrossProcessGuard {
    fn drop(&mut self) {
        unsafe {
            windows_sys::Win32::System::Threading::ReleaseMutex(self.handle);
            windows_sys::Win32::Foundation::CloseHandle(self.handle);
        }
    }
}

#[cfg(not(windows))]
pub(crate) struct CrossProcessGuard;

#[cfg(not(windows))]
impl CrossProcessGuard {
    fn acquire(_name: &str) -> Result<Self, &'static str> {
        Ok(Self)
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub(crate) fn secure_random_hex<const N: usize>() -> Result<String, &'static str> {
    let mut bytes = [0_u8; N];
    fill_secure_random(&mut bytes)?;
    let encoded = bytes.iter().map(|byte| format!("{byte:02x}")).collect();
    bytes.fill(0);
    Ok(encoded)
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
    (status >= 0)
        .then_some(())
        .ok_or("RO-SIGN-IN-POLICY-RANDOM-FAILED")
}

#[cfg(not(windows))]
fn fill_secure_random(target: &mut [u8]) -> Result<(), &'static str> {
    File::open("/dev/urandom")
        .and_then(|mut source| source.read_exact(target))
        .map_err(|_| "RO-SIGN-IN-POLICY-RANDOM-FAILED")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(1);

    fn root(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "ro-sign-in-policy-{name}-{}-{}",
            std::process::id(),
            TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ))
    }

    fn exact_legacy(profile_name: Option<&str>, timeout: u8) -> Vec<u8> {
        format!(
            concat!(
                "{{\n",
                "  \"schemaVersion\": \"1.0\",\n",
                "  \"documentType\": \"research-observatory-application-lock-profile\",\n",
                "  \"profileName\": {},\n",
                "  \"inactivityTimeoutMinutes\": {},\n",
                "  \"restartPolicy\": \"lock-when-inactivity-enabled\",\n",
                "  \"lockAuthority\": \"desktop-native-supervisor\",\n",
                "  \"reauthentication\": \"windows-current-user-credentials-same-sid\",\n",
                "  \"protectedActionPolicy\": \"invalidate-generation-stop-core-discard-renderer-state\",\n",
                "  \"durableOperationPolicy\": \"w1-stop-all-future-continuation-requires-explicit-allowlist\",\n",
                "  \"threatBoundary\": \"application-session-protection-not-windows-account-isolation\"\n",
                "}}\n"
            ),
            profile_name
                .map(|value| serde_json::to_string(value).expect("name json"))
                .unwrap_or_else(|| "null".to_owned()),
            timeout
        )
        .into_bytes()
    }

    #[test]
    fn absent_state_becomes_explicit_none_and_reopens() {
        let root = root("absent");
        let store = PolicyStore::new(&root);
        let loaded = store.initialize();
        assert_eq!(loaded.state, PolicyLoadState::Valid);
        assert_eq!(loaded.policy.mode, SignInMode::None);
        assert_eq!(loaded.policy.revision(), 1);
        assert!(store.canonical_path().is_file());
        let reopened = PolicyStore::new(&root).initialize();
        assert_eq!(reopened.policy, loaded.policy);
    }

    #[test]
    fn exact_legacy_zero_and_nonzero_profiles_migrate_without_rewriting_predecessor() {
        for (name, timeout) in [
            (Some("  Δ Researcher  "), 0),
            (None, 5),
            (Some("Researcher"), 15),
            (None, 30),
            (Some("Lab profile"), 60),
        ] {
            let root = root("legacy");
            let security = root.join("security");
            fs::create_dir_all(&security).expect("security dir");
            let bytes = exact_legacy(name, timeout);
            fs::write(security.join(LEGACY_PROFILE_FILE), &bytes).expect("legacy profile");
            let loaded = PolicyStore::new(&root).initialize();
            assert_eq!(loaded.state, PolicyLoadState::Migrated);
            assert_eq!(loaded.policy.mode, SignInMode::WindowsPassword);
            assert_eq!(loaded.policy.profile_name.as_deref(), name);
            assert_eq!(loaded.policy.inactivity_timeout_minutes, timeout);
            assert_eq!(
                fs::read(security.join(LEGACY_PROFILE_FILE)).expect("legacy bytes"),
                bytes
            );
        }
    }

    #[test]
    fn invalid_canonical_never_falls_back_to_valid_legacy_or_none() {
        let root = root("invalid-canonical");
        let security = root.join("security");
        fs::create_dir_all(&security).expect("security dir");
        fs::write(
            security.join(POLICY_FILE),
            b"{\"schemaVersion\":\"future\"}",
        )
        .expect("canonical");
        fs::write(
            security.join(LEGACY_PROFILE_FILE),
            exact_legacy(Some("legacy"), 15),
        )
        .expect("legacy");
        let loaded = PolicyStore::new(&root).initialize();
        assert_eq!(loaded.state, PolicyLoadState::Invalid);
    }

    #[test]
    fn policy_rejects_unknown_modes_fields_revisions_and_none_with_timeout() {
        assert!(SignInPolicy::normalized_target(1, SignInMode::None, None, 0).is_ok());
        assert_eq!(
            SignInPolicy::normalized_target(1, SignInMode::None, None, 5),
            Err("RO-SIGN-IN-POLICY-INVALID")
        );
        assert_eq!(
            SignInPolicy::normalized_target(0, SignInMode::WindowsPassword, None, 0),
            Err("RO-SIGN-IN-POLICY-INVALID")
        );
        let mut value = serde_json::to_value(SignInPolicy::explicit_none()).expect("policy");
        value["mode"] = serde_json::json!("future-provider");
        assert!(serde_json::from_value::<SignInPolicy>(value).is_err());
        let mut value = serde_json::to_value(SignInPolicy::explicit_none()).expect("policy");
        value["unexpected"] = serde_json::json!(true);
        assert!(serde_json::from_value::<SignInPolicy>(value).is_err());
    }

    #[test]
    fn compare_and_swap_denies_stale_manager_and_preserves_first_success() {
        let root = root("cas");
        let first = PolicyStore::new(&root);
        let second = PolicyStore::new(&root);
        let first_loaded = first.initialize();
        let second_loaded = second.initialize();
        let next = SignInPolicy::normalized_target(
            2,
            SignInMode::WindowsPassword,
            Some("first".to_owned()),
            0,
        )
        .expect("first policy");
        let _guard = first.lock().expect("first lock");
        let staged = first.stage(&next).expect("stage first");
        first
            .publish(staged, &first_loaded.source)
            .expect("publish first");
        drop(_guard);

        let stale = SignInPolicy::normalized_target(
            2,
            SignInMode::WindowsHello,
            Some("second".to_owned()),
            0,
        )
        .expect("second policy");
        let _guard = second.lock().expect("second lock");
        let staged = second.stage(&stale).expect("stage second");
        assert_eq!(
            second.publish(staged, &second_loaded.source),
            Err("RO-SIGN-IN-POLICY-CONFLICT")
        );
        assert_eq!(PolicyStore::new(&root).initialize().policy, next);
    }

    #[test]
    fn restart_discards_orphan_staging_without_changing_committed_policy() {
        let root = root("orphan-staging");
        let store = PolicyStore::new(&root);
        let committed = store.initialize();
        let before = fs::read(store.canonical_path()).expect("committed policy");
        let orphan = store
            .canonical_path()
            .parent()
            .expect("security dir")
            .join(format!(".{POLICY_FILE}.deadbeef.staging"));
        fs::write(&orphan, b"partial transition").expect("orphan staging");

        let reopened = PolicyStore::new(&root).initialize();
        assert_eq!(reopened.policy, committed.policy);
        assert!(!orphan.exists());
        assert_eq!(
            fs::read(store.canonical_path()).expect("committed policy"),
            before
        );
    }

    #[test]
    fn invalid_legacy_state_fails_locked_without_creating_a_canonical_downgrade() {
        let root = root("invalid-legacy");
        let store = PolicyStore::new(&root);
        fs::create_dir_all(store.legacy_path.parent().expect("security dir"))
            .expect("security dir");
        fs::write(&store.legacy_path, b"{\"schemaVersion\":\"future\"}\n").expect("invalid legacy");
        let loaded = store.initialize();
        assert_eq!(loaded.state, PolicyLoadState::Invalid);
        assert!(!store.canonical_path().exists());
    }

    #[test]
    fn equivalent_paths_share_one_canonical_store_and_mutex_identity() {
        let root = root("stable-path");
        fs::create_dir_all(&root).expect("application data");
        let alias = root
            .parent()
            .expect("parent")
            .join(".")
            .join(root.file_name().expect("leaf"));
        let direct = PolicyStore::new(&root);
        let aliased = PolicyStore::new(&alias);
        assert_eq!(direct.security_dir, aliased.security_dir);
        assert_eq!(direct.mutex_name, aliased.mutex_name);
    }
}
