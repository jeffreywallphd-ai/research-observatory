use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::supervisor::{
    RuntimeDiagnostic, RuntimeResourceUsage, RuntimeSnapshot, RuntimeSupervisor,
};

const MAX_BUNDLE_BYTES: usize = 65_536;
const MAX_EXPORTED_DIAGNOSTICS: usize = 32;
const SUPPORT_DIRECTORY: &str = "support-exports";

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ComponentVersion {
    component_id: &'static str,
    version: &'static str,
    contract_version: &'static str,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StorageDiagnostic {
    storage_id: &'static str,
    status: &'static str,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SupportBundleDocument {
    schema_version: &'static str,
    document_type: &'static str,
    bundle_id: String,
    generated_at_unix_ms: u64,
    components: [ComponentVersion; 2],
    runtime: RuntimeSnapshot,
    storage: [StorageDiagnostic; 1],
    resources: RuntimeResourceUsage,
    recent_diagnostics: Vec<RuntimeDiagnostic>,
    exclusions: [&'static str; 9],
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SupportBundlePreview {
    preview_id: String,
    output_directory: String,
    byte_length: usize,
    sha256: String,
    document_json: String,
    bundle: SupportBundleDocument,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SupportBundleExport {
    bundle_id: String,
    path: String,
    byte_length: usize,
    sha256: String,
}

impl SupportBundlePreview {
    pub fn preview_id(&self) -> &str {
        &self.preview_id
    }

    pub fn byte_length(&self) -> usize {
        self.byte_length
    }

    pub fn sha256(&self) -> &str {
        &self.sha256
    }

    pub fn document_json(&self) -> &str {
        &self.document_json
    }

    pub fn bundle(&self) -> &SupportBundleDocument {
        &self.bundle
    }
}

impl SupportBundleDocument {
    pub fn bundle_id(&self) -> &str {
        &self.bundle_id
    }
}

impl SupportBundleExport {
    pub fn path(&self) -> &str {
        &self.path
    }

    pub fn byte_length(&self) -> usize {
        self.byte_length
    }

    pub fn sha256(&self) -> &str {
        &self.sha256
    }
}

struct PendingPreview {
    preview: SupportBundlePreview,
    bytes: Vec<u8>,
}

impl Drop for PendingPreview {
    fn drop(&mut self) {
        self.bytes.fill(0);
    }
}

pub struct PreparedSupportBundlePreview {
    pending: Option<PendingPreview>,
}

pub struct StagedSupportBundleExport {
    preview_id: String,
    output_directory: PathBuf,
    staging: PathBuf,
    destination: PathBuf,
    export: SupportBundleExport,
}

impl Drop for StagedSupportBundleExport {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.staging);
    }
}

#[derive(Clone, Default)]
pub struct SupportBundleManager {
    pending: Arc<Mutex<Option<PendingPreview>>>,
}

impl SupportBundleManager {
    pub fn preview(
        &self,
        application_data: &Path,
        supervisor: &RuntimeSupervisor,
    ) -> Result<SupportBundlePreview, &'static str> {
        let prepared = self.prepare_preview(application_data, supervisor)?;
        self.publish_preview(prepared)
    }

    pub fn prepare_preview(
        &self,
        application_data: &Path,
        supervisor: &RuntimeSupervisor,
    ) -> Result<PreparedSupportBundlePreview, &'static str> {
        let intended_output = application_data.join(SUPPORT_DIRECTORY);
        let (output_directory, storage_status) = match verified_support_directory(application_data)
        {
            Ok(output_directory) => (output_directory, "available"),
            Err(_) => (intended_output, "unavailable"),
        };
        let bundle_id = secure_random_hex::<16>()?;
        let preview_id = secure_random_hex::<16>()?;
        let mut recent_diagnostics = supervisor.diagnostics();
        if recent_diagnostics.len() > MAX_EXPORTED_DIAGNOSTICS {
            recent_diagnostics.drain(..recent_diagnostics.len() - MAX_EXPORTED_DIAGNOSTICS);
        }
        let generated_at_unix_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| "RO-SUPPORT-CLOCK-FAILED")?
            .as_millis()
            .try_into()
            .map_err(|_| "RO-SUPPORT-CLOCK-FAILED")?;
        let bundle = SupportBundleDocument {
            schema_version: "1.0",
            document_type: "research-observatory-support-bundle",
            bundle_id,
            generated_at_unix_ms,
            components: [
                ComponentVersion {
                    component_id: "desktop",
                    version: env!("CARGO_PKG_VERSION"),
                    contract_version: "1.0.0",
                },
                ComponentVersion {
                    component_id: "core-api",
                    version: "0.1.0",
                    contract_version: "1.0.0",
                },
            ],
            runtime: supervisor.status(),
            storage: [StorageDiagnostic {
                storage_id: "application-data",
                status: storage_status,
            }],
            resources: supervisor.resource_usage(),
            recent_diagnostics,
            exclusions: [
                "project-documents",
                "imported-sources",
                "manuscript-content",
                "search-and-query-text",
                "credentials-and-tokens",
                "environment-variables",
                "raw-process-logs",
                "process-identifiers",
                "absolute-storage-paths",
            ],
        };
        let mut bytes =
            serde_json::to_vec_pretty(&bundle).map_err(|_| "RO-SUPPORT-SERIALIZE-FAILED")?;
        bytes.push(b'\n');
        if bytes.len() > MAX_BUNDLE_BYTES {
            return Err("RO-SUPPORT-BUNDLE-OVERSIZE");
        }
        let preview = SupportBundlePreview {
            preview_id,
            output_directory: display_path(&output_directory)?,
            byte_length: bytes.len(),
            sha256: sha256_hex(&bytes),
            document_json: String::from_utf8(bytes.clone())
                .map_err(|_| "RO-SUPPORT-SERIALIZE-FAILED")?,
            bundle,
        };
        Ok(PreparedSupportBundlePreview {
            pending: Some(PendingPreview { preview, bytes }),
        })
    }

    pub fn publish_preview(
        &self,
        mut prepared: PreparedSupportBundlePreview,
    ) -> Result<SupportBundlePreview, &'static str> {
        let pending = prepared.pending.take().ok_or("RO-SUPPORT-STATE-FAILED")?;
        let preview = pending.preview.clone();
        *self.pending.lock().map_err(|_| "RO-SUPPORT-STATE-FAILED")? = Some(pending);
        Ok(preview)
    }

    pub fn export(
        &self,
        application_data: &Path,
        preview_id: &str,
    ) -> Result<SupportBundleExport, &'static str> {
        let staged = self.stage_export(application_data, preview_id)?;
        self.publish_export(staged)
    }

    pub fn stage_export(
        &self,
        application_data: &Path,
        preview_id: &str,
    ) -> Result<StagedSupportBundleExport, &'static str> {
        if !canonical_hex(preview_id, 32) {
            return Err("RO-SUPPORT-PREVIEW-INVALID");
        }
        let locked = self.pending.lock().map_err(|_| "RO-SUPPORT-STATE-FAILED")?;
        let current = locked.as_ref().ok_or("RO-SUPPORT-PREVIEW-STALE")?;
        if current.preview.preview_id != preview_id {
            return Err("RO-SUPPORT-PREVIEW-STALE");
        }
        let bundle_id = current.preview.bundle.bundle_id.clone();
        let byte_length = current.preview.byte_length;
        let sha256 = current.preview.sha256.clone();
        let mut bytes = current.bytes.clone();
        drop(locked);
        let output_directory = verified_support_directory(application_data)?;
        let filename = format!("research-observatory-support-{bundle_id}.json");
        let destination = output_directory.join(filename);
        let destination_display = display_path(&destination)?;
        let staging = output_directory.join(format!(
            ".research-observatory-support-{}.staging",
            secure_random_hex::<16>()?
        ));
        let staged_result = write_staged_bundle(&output_directory, &staging, &bytes);
        bytes.fill(0);
        staged_result?;
        Ok(StagedSupportBundleExport {
            preview_id: preview_id.to_owned(),
            output_directory,
            staging,
            export: SupportBundleExport {
                bundle_id,
                path: destination_display,
                byte_length,
                sha256,
            },
            destination,
        })
    }

    pub fn publish_export(
        &self,
        staged: StagedSupportBundleExport,
    ) -> Result<SupportBundleExport, &'static str> {
        let mut locked = self.pending.lock().map_err(|_| "RO-SUPPORT-STATE-FAILED")?;
        let current = locked.as_ref().ok_or("RO-SUPPORT-PREVIEW-STALE")?;
        if current.preview.preview_id != staged.preview_id {
            return Err("RO-SUPPORT-PREVIEW-STALE");
        }
        publish_staged_bundle(
            &staged.output_directory,
            &staged.staging,
            &staged.destination,
        )?;
        let export = staged.export.clone();
        locked.take();
        Ok(export)
    }

    pub fn clear_pending(&self) {
        if let Ok(mut pending) = self.pending.lock() {
            pending.take();
        }
    }

    #[cfg(test)]
    fn has_pending(&self) -> bool {
        self.pending.lock().is_ok_and(|pending| pending.is_some())
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn canonical_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn display_path(path: &Path) -> Result<String, &'static str> {
    path.to_str()
        .filter(|value| !value.chars().any(char::is_control) && value.len() <= 512)
        .map(str::to_owned)
        .ok_or("RO-SUPPORT-PATH-INVALID")
}

fn verified_support_directory(application_data: &Path) -> Result<PathBuf, &'static str> {
    fs::create_dir_all(application_data).map_err(|_| "RO-SUPPORT-PATH-UNAVAILABLE")?;
    reject_redirect(application_data)?;
    let application_data =
        fs::canonicalize(application_data).map_err(|_| "RO-SUPPORT-PATH-UNAVAILABLE")?;
    let output_directory = application_data.join(SUPPORT_DIRECTORY);
    fs::create_dir_all(&output_directory).map_err(|_| "RO-SUPPORT-PATH-UNAVAILABLE")?;
    reject_redirect(&output_directory)?;
    let canonical_output =
        fs::canonicalize(&output_directory).map_err(|_| "RO-SUPPORT-PATH-UNAVAILABLE")?;
    if canonical_output.parent() != Some(application_data.as_path()) {
        return Err("RO-SUPPORT-PATH-REDIRECTED");
    }
    Ok(canonical_output)
}

fn reject_redirect(path: &Path) -> Result<(), &'static str> {
    let metadata = fs::symlink_metadata(path).map_err(|_| "RO-SUPPORT-PATH-UNAVAILABLE")?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() || is_reparse_point(&metadata) {
        return Err("RO-SUPPORT-PATH-REDIRECTED");
    }
    Ok(())
}

#[cfg(windows)]
fn is_reparse_point(metadata: &fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;
    metadata.file_attributes() & 0x400 != 0
}

#[cfg(not(windows))]
fn is_reparse_point(_metadata: &fs::Metadata) -> bool {
    false
}

#[cfg(windows)]
fn open_directory_guard(path: &Path) -> Result<File, &'static str> {
    use std::os::windows::fs::OpenOptionsExt;
    use windows_sys::Win32::Storage::FileSystem::{
        FILE_FLAG_BACKUP_SEMANTICS, FILE_SHARE_READ, FILE_SHARE_WRITE,
    };
    OpenOptions::new()
        .read(true)
        .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE)
        .custom_flags(FILE_FLAG_BACKUP_SEMANTICS)
        .open(path)
        .map_err(|_| "RO-SUPPORT-PATH-UNAVAILABLE")
}

#[cfg(not(windows))]
fn open_directory_guard(path: &Path) -> Result<File, &'static str> {
    File::open(path).map_err(|_| "RO-SUPPORT-PATH-UNAVAILABLE")
}

fn write_staged_bundle(
    directory: &Path,
    destination: &Path,
    bytes: &[u8],
) -> Result<(), &'static str> {
    let _directory_guard = open_directory_guard(directory)?;
    reject_redirect(directory)?;
    #[cfg(windows)]
    use std::os::windows::fs::OpenOptionsExt;
    let mut options = OpenOptions::new();
    options.read(true).write(true).create_new(true);
    #[cfg(windows)]
    options.share_mode(windows_sys::Win32::Storage::FileSystem::FILE_SHARE_READ);
    let mut file = options
        .open(destination)
        .map_err(|_| "RO-SUPPORT-WRITE-FAILED")?;
    if file
        .write_all(bytes)
        .and_then(|_| file.sync_all())
        .and_then(|_| file.seek(SeekFrom::Start(0)))
        .is_err()
    {
        drop(file);
        let _ = fs::remove_file(destination);
        return Err("RO-SUPPORT-WRITE-FAILED");
    }
    let mut installed = Vec::with_capacity(bytes.len());
    if file.read_to_end(&mut installed).is_err() || installed != bytes {
        drop(file);
        let _ = fs::remove_file(destination);
        return Err("RO-SUPPORT-WRITE-FAILED");
    }
    reject_redirect(directory)?;
    Ok(())
}

fn publish_staged_bundle(
    directory: &Path,
    staging: &Path,
    destination: &Path,
) -> Result<(), &'static str> {
    let _directory_guard = open_directory_guard(directory)?;
    reject_redirect(directory)?;
    if staging.parent() != Some(directory) || destination.parent() != Some(directory) {
        return Err("RO-SUPPORT-PATH-REDIRECTED");
    }
    publish_new_file(staging, destination)?;
    reject_redirect(directory)
}

#[cfg(windows)]
fn publish_new_file(staging: &Path, destination: &Path) -> Result<(), &'static str> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{MOVEFILE_WRITE_THROUGH, MoveFileExW};

    let staging: Vec<u16> = staging.as_os_str().encode_wide().chain(Some(0)).collect();
    let destination: Vec<u16> = destination
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    if unsafe {
        MoveFileExW(
            staging.as_ptr(),
            destination.as_ptr(),
            MOVEFILE_WRITE_THROUGH,
        )
    } == 0
    {
        Err("RO-SUPPORT-WRITE-FAILED")
    } else {
        Ok(())
    }
}

#[cfg(not(windows))]
fn publish_new_file(staging: &Path, destination: &Path) -> Result<(), &'static str> {
    fs::hard_link(staging, destination).map_err(|_| "RO-SUPPORT-WRITE-FAILED")?;
    fs::remove_file(staging).map_err(|_| {
        let _ = fs::remove_file(destination);
        "RO-SUPPORT-WRITE-FAILED"
    })
}

fn secure_random_hex<const N: usize>() -> Result<String, &'static str> {
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
        .ok_or("RO-SUPPORT-RANDOM-FAILED")
}

#[cfg(not(windows))]
fn fill_secure_random(target: &mut [u8]) -> Result<(), &'static str> {
    File::open("/dev/urandom")
        .and_then(|mut source| source.read_exact(target))
        .map_err(|_| "RO-SUPPORT-RANDOM-FAILED")
}

#[cfg(test)]
mod tests {
    use super::{MAX_BUNDLE_BYTES, SupportBundleManager, canonical_hex};
    use crate::application_lock::{ApplicationLockManager, ApplicationLockReason};
    use crate::supervisor::RuntimeSupervisor;
    use std::sync::atomic::{AtomicU64, Ordering};

    static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(1);

    fn test_root(name: &str) -> std::path::PathBuf {
        std::env::temp_dir().join(format!(
            "{name}-{}-{}",
            std::process::id(),
            TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ))
    }

    #[test]
    fn preview_is_bounded_redacted_and_export_is_single_use() {
        let root = test_root("ro-support-test");
        let _ = std::fs::remove_dir_all(&root);
        let manager = SupportBundleManager::default();
        let supervisor = RuntimeSupervisor::new(Err("RO-CORE-INTEGRITY-FAILED"));
        let preview = manager
            .preview(&root, &supervisor)
            .expect("support preview");
        assert!(canonical_hex(&preview.preview_id, 32));
        assert!(preview.byte_length <= MAX_BUNDLE_BYTES);
        let serialized = serde_json::to_string(&preview.bundle).expect("serialize preview");
        for forbidden in [
            "Bearer hunter2",
            "environmentVariables",
            "processId",
            "absolutePath",
            "C:\\\\Users",
        ] {
            assert!(
                !serialized.contains(forbidden),
                "support preview contained {forbidden}"
            );
        }
        let exported = manager
            .export(&root, &preview.preview_id)
            .expect("support export");
        assert_eq!(exported.byte_length, preview.byte_length);
        assert_eq!(exported.sha256, preview.sha256);
        assert_eq!(
            std::fs::read(&exported.path).expect("read export").len(),
            preview.byte_length
        );
        assert_eq!(
            manager.export(&root, &preview.preview_id),
            Err("RO-SUPPORT-PREVIEW-STALE")
        );
        std::fs::remove_dir_all(root).expect("remove support fixture");
    }

    #[test]
    fn malformed_preview_identity_is_denied_without_consuming_the_pending_preview() {
        let root = test_root("ro-support-id-test");
        let _ = std::fs::remove_dir_all(&root);
        let manager = SupportBundleManager::default();
        let supervisor = RuntimeSupervisor::new(Err("RO-CORE-INTEGRITY-FAILED"));
        let preview = manager
            .preview(&root, &supervisor)
            .expect("support preview");
        assert_eq!(
            manager.export(&root, "../private"),
            Err("RO-SUPPORT-PREVIEW-INVALID")
        );
        assert_eq!(
            manager.export(&root, &"f".repeat(32)),
            Err("RO-SUPPORT-PREVIEW-STALE")
        );
        assert!(manager.export(&root, &preview.preview_id).is_ok());
        std::fs::remove_dir_all(root).expect("remove support fixture");
    }

    #[test]
    fn lock_prevents_preview_and_export_publication_and_clears_pending_state() {
        let root = test_root("ro-support-lock-test");
        let manager = SupportBundleManager::default();
        let supervisor = RuntimeSupervisor::new(Err("RO-CORE-INTEGRITY-FAILED"));
        let lock = ApplicationLockManager::new(&root.join("lock-profile"));

        let preview_ticket = lock.begin_protected_action().expect("preview ticket");
        let prepared = manager
            .prepare_preview(&root, &supervisor)
            .expect("prepared preview");
        lock.lock(ApplicationLockReason::Manual);
        assert_eq!(
            lock.commit_protected_action(preview_ticket, || manager.publish_preview(prepared)),
            Err("RO-APPLICATION-LOCKED")
        );
        assert!(!manager.has_pending());

        let unlocked_lock = ApplicationLockManager::new(&root.join("separate-lock-profile"));
        let preview = manager
            .preview(&root, &supervisor)
            .expect("support preview");
        let export_ticket = unlocked_lock
            .begin_protected_action()
            .expect("export ticket");
        let staged = manager
            .stage_export(&root, preview.preview_id())
            .expect("staged export");
        let destination = staged.destination.clone();
        let staging = staged.staging.clone();
        unlocked_lock.lock(ApplicationLockReason::Manual);
        manager.clear_pending();
        assert_eq!(
            unlocked_lock.commit_protected_action(export_ticket, || manager.publish_export(staged)),
            Err("RO-APPLICATION-LOCKED")
        );
        assert!(!destination.exists());
        assert!(!staging.exists());
        assert!(!manager.has_pending());
        std::fs::remove_dir_all(root).expect("remove support fixture");
    }

    #[test]
    fn preexisting_hardlink_at_the_exact_export_name_is_not_followed() {
        let root = test_root("ro-support-hardlink");
        let _ = std::fs::remove_dir_all(&root);
        let manager = SupportBundleManager::default();
        let supervisor = RuntimeSupervisor::new(Err("RO-CORE-INTEGRITY-FAILED"));
        let preview = manager
            .preview(&root, &supervisor)
            .expect("support preview");
        let outside = root.join("outside.txt");
        std::fs::write(&outside, b"outside remains unchanged").expect("write outside sentinel");
        let destination = root.join("support-exports").join(format!(
            "research-observatory-support-{}.json",
            preview.bundle().bundle_id()
        ));
        std::fs::hard_link(&outside, &destination).expect("create exact-name hardlink");
        assert_eq!(
            manager.export(&root, preview.preview_id()),
            Err("RO-SUPPORT-WRITE-FAILED")
        );
        assert_eq!(
            std::fs::read(&outside).expect("read outside sentinel"),
            b"outside remains unchanged"
        );
        std::fs::remove_dir_all(root).expect("remove support fixture");
    }

    #[cfg(windows)]
    #[test]
    fn redirected_support_directory_is_rejected() {
        use std::process::Command;

        let root = test_root("ro-support-junction");
        let outside = test_root("ro-support-outside");
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
        std::fs::create_dir_all(&root).expect("create application data root");
        std::fs::create_dir_all(&outside).expect("create outside root");
        let junction = root.join("support-exports");
        let status = Command::new("cmd")
            .args([
                "/c",
                "mklink",
                "/J",
                junction.to_str().expect("junction path"),
                outside.to_str().expect("outside path"),
            ])
            .status()
            .expect("create support junction");
        assert!(status.success(), "mklink /J failed");

        let manager = SupportBundleManager::default();
        let supervisor = RuntimeSupervisor::new(Err("RO-CORE-INTEGRITY-FAILED"));
        let preview = manager
            .preview(&root, &supervisor)
            .expect("partial support preview");
        let serialized = serde_json::to_value(preview.bundle()).expect("serialize partial preview");
        assert_eq!(serialized["storage"][0]["status"], "unavailable");
        assert_eq!(
            manager.export(&root, preview.preview_id()),
            Err("RO-SUPPORT-PATH-REDIRECTED")
        );
        assert!(
            std::fs::read_dir(&outside)
                .expect("read outside root")
                .next()
                .is_none(),
            "redirected support directory received output"
        );

        std::fs::remove_dir(&junction).expect("remove support junction");
        std::fs::remove_dir_all(root).expect("remove application data root");
        std::fs::remove_dir_all(outside).expect("remove outside root");
    }
}
