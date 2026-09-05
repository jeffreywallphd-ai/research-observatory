pub mod application_lock;
pub mod application_lock_verification;
mod application_sign_in_policy;
pub mod directory_picker;
pub mod supervisor;
pub mod support_bundle;

use application_lock::{
    ApplicationLockAuditEvent, ApplicationLockManager, ApplicationLockReason,
    ApplicationLockSnapshot, ApplicationUnlockAttempt, PolicyTransitionResult, SignInMode,
};
use application_lock_verification::{
    VerificationAvailabilitySnapshot, VerificationOutcome, windows_hello_availability_snapshot,
};
use directory_picker::{
    CloseDisposition, DefaultParentOutcome, DirectoryOutcome, DirectoryPickerManager,
};
use supervisor::{
    CoreApiRequest, CoreApiResponse, RuntimeDiagnostic, RuntimeSnapshot, RuntimeState,
    RuntimeSupervisor, SupervisorConfig,
};
use support_bundle::{SupportBundleExport, SupportBundleManager, SupportBundlePreview};
use tauri::{App, AppHandle, Emitter, Manager, Runtime, State};

pub const PRODUCT_NAME: &str = "Research Observatory";

#[tauri::command]
async fn choose_project_directory(
    window: tauri::WebviewWindow,
    picker: State<'_, DirectoryPickerManager>,
    lock: State<'_, ApplicationLockManager>,
    message: tauri::ipc::Request<'_>,
) -> Result<DirectoryOutcome, ()> {
    let tauri::ipc::InvokeBody::Json(payload) = message.body() else {
        return Ok(DirectoryOutcome::Failed);
    };
    let Some(request) = directory_picker::decode_request(payload) else {
        return Ok(DirectoryOutcome::Failed);
    };
    let Some(owner) = directory_window_handle(&window) else {
        return Ok(DirectoryOutcome::Unavailable);
    };
    #[cfg(all(feature = "integration-harness", windows))]
    if window
        .try_state::<directory_integration_harness::Fixture>()
        .is_some_and(|fixture| fixture.revalidate().is_err())
    {
        return Ok(DirectoryOutcome::Unavailable);
    }
    let Ok(ticket) = lock.begin_protected_action() else {
        return Ok(DirectoryOutcome::Cancelled);
    };
    let manager = picker.inner().clone();
    let checking_manager = manager.clone();
    let checking_lock = lock.inner().clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        manager.choose(owner, request, move || {
            checking_manager.is_open() && checking_lock.finish_protected_action(ticket).is_ok()
        })
    })
    .await
    .unwrap_or(DirectoryOutcome::Failed);
    let result = if lock.finish_protected_action(ticket).is_err()
        || !picker.is_open()
        || directory_window_handle(&window) != Some(owner)
    {
        DirectoryOutcome::Cancelled
    } else {
        result
    };
    #[cfg(all(feature = "integration-harness", windows))]
    if window
        .try_state::<directory_integration_harness::Fixture>()
        .is_some()
    {
        directory_integration_harness::observe_result(&result);
    }
    Ok(result)
}

#[tauri::command]
async fn default_project_parent(
    window: tauri::WebviewWindow,
    picker: State<'_, DirectoryPickerManager>,
    lock: State<'_, ApplicationLockManager>,
    message: tauri::ipc::Request<'_>,
) -> Result<DefaultParentOutcome, ()> {
    if !matches!(message.body(), tauri::ipc::InvokeBody::Json(value) if value.as_object().is_some_and(|object| object.is_empty()))
    {
        return Ok(DefaultParentOutcome::Failed);
    }
    let Some(owner) = directory_window_handle(&window) else {
        return Ok(DefaultParentOutcome::Unavailable);
    };
    let Ok(ticket) = lock.begin_protected_action() else {
        return Ok(DefaultParentOutcome::Unavailable);
    };
    if !picker.is_open() {
        return Ok(DefaultParentOutcome::Unavailable);
    }
    #[cfg(all(feature = "integration-harness", windows))]
    let fixture_parent = window
        .try_state::<directory_integration_harness::Fixture>()
        .map(|fixture| fixture.revalidate().map(|()| fixture.projects.clone()));
    let result = tauri::async_runtime::spawn_blocking(move || {
        #[cfg(all(feature = "integration-harness", windows))]
        if let Some(path) = fixture_parent {
            return path.map_or(DefaultParentOutcome::Unavailable, |path| {
                DefaultParentOutcome::Available {
                    path: path.to_string_lossy().into_owned(),
                }
            });
        }
        directory_picker::default_project_parent()
    })
    .await
    .unwrap_or(DefaultParentOutcome::Failed);
    if lock.finish_protected_action(ticket).is_err()
        || !picker.is_open()
        || directory_window_handle(&window) != Some(owner)
    {
        return Ok(DefaultParentOutcome::Unavailable);
    }
    Ok(result)
}

fn directory_window_handle(window: &tauri::WebviewWindow) -> Option<isize> {
    let url = window.url().ok()?;
    if !directory_origin_allowed(window.label(), &url) {
        return None;
    }
    #[cfg(windows)]
    return window
        .hwnd()
        .ok()
        .map(|handle| handle.0 as isize)
        .filter(|handle| directory_picker::valid_owner(*handle));
    #[cfg(not(windows))]
    None
}

fn directory_origin_allowed(label: &str, url: &tauri::Url) -> bool {
    !(label != "main"
        || !matches!(
            (url.scheme(), url.host_str()),
            ("http" | "https", Some("tauri.localhost")) | ("tauri", Some("localhost"))
        )
        || url.port().is_some()
        || !url.username().is_empty()
        || url.password().is_some())
}

#[tauri::command]
async fn core_runtime_start(
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
) -> Result<RuntimeSnapshot, &'static str> {
    let ticket = lock.begin_protected_action()?;
    let result = dispatch_runtime_start(supervisor.inner().clone()).await;
    lock.finish_protected_action(ticket)?;
    result
}

#[tauri::command]
fn core_runtime_status(supervisor: State<'_, RuntimeSupervisor>) -> RuntimeSnapshot {
    supervisor.status()
}

#[tauri::command]
async fn core_runtime_retry(
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
) -> Result<RuntimeSnapshot, &'static str> {
    let ticket = lock.begin_protected_action()?;
    let result = dispatch_runtime_start(supervisor.inner().clone()).await;
    lock.finish_protected_action(ticket)?;
    result
}

#[tauri::command]
async fn core_runtime_stop(
    supervisor: State<'_, RuntimeSupervisor>,
) -> Result<RuntimeSnapshot, &'static str> {
    dispatch_runtime_stop(supervisor.inner().clone()).await
}

#[tauri::command]
fn core_runtime_diagnostics(supervisor: State<'_, RuntimeSupervisor>) -> Vec<RuntimeDiagnostic> {
    supervisor.diagnostics()
}

#[tauri::command]
async fn core_api_request(
    app: AppHandle,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: CoreApiRequest,
) -> Result<CoreApiResponse, &'static str> {
    let ticket = lock.begin_protected_action()?;
    #[cfg(all(feature = "integration-harness", windows))]
    if let Some(fixture) = app.try_state::<directory_integration_harness::Fixture>()
        && !fixture.permits_request(&request)
    {
        return Err("RO-FIXTURE-PATH-DENIED");
    }
    #[cfg(not(all(feature = "integration-harness", windows)))]
    let _ = app;
    let result = dispatch_core_api_request(supervisor.inner().clone(), request).await;
    lock.finish_protected_action(ticket)?;
    result
}

#[tauri::command]
async fn support_bundle_preview(
    app: AppHandle,
    supervisor: State<'_, RuntimeSupervisor>,
    manager: State<'_, SupportBundleManager>,
    lock: State<'_, ApplicationLockManager>,
) -> Result<SupportBundlePreview, &'static str> {
    let ticket = lock.begin_protected_action()?;
    let application_data = app
        .path()
        .app_local_data_dir()
        .map_err(|_| "RO-SUPPORT-PATH-UNAVAILABLE")?;
    let supervisor = supervisor.inner().clone();
    let manager = manager.inner().clone();
    let collection = manager.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        collection.prepare_preview(&application_data, &supervisor)
    })
    .await
    .map_err(|_| "RO-SUPPORT-COLLECTION-FAILED")??;
    lock.commit_protected_action(ticket, || manager.publish_preview(result))
}

#[tauri::command]
async fn support_bundle_export(
    app: AppHandle,
    manager: State<'_, SupportBundleManager>,
    lock: State<'_, ApplicationLockManager>,
    preview_id: String,
) -> Result<SupportBundleExport, &'static str> {
    let ticket = lock.begin_protected_action()?;
    let application_data = app
        .path()
        .app_local_data_dir()
        .map_err(|_| "RO-SUPPORT-PATH-UNAVAILABLE")?;
    let manager = manager.inner().clone();
    let staging = manager.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        staging.stage_export(&application_data, &preview_id)
    })
    .await
    .map_err(|_| "RO-SUPPORT-WRITE-FAILED")??;
    lock.commit_protected_action(ticket, || manager.publish_export(result))
}

#[tauri::command]
fn application_lock_status(lock: State<'_, ApplicationLockManager>) -> ApplicationLockSnapshot {
    lock.status()
}

#[tauri::command]
fn application_lock_activity(lock: State<'_, ApplicationLockManager>) {
    lock.record_activity();
}

#[tauri::command]
fn application_lock_audit(
    lock: State<'_, ApplicationLockManager>,
) -> Vec<ApplicationLockAuditEvent> {
    lock.audit()
}

#[tauri::command]
async fn application_lock_hello_availability() -> VerificationAvailabilitySnapshot {
    tauri::async_runtime::spawn_blocking(windows_hello_availability_snapshot)
        .await
        .unwrap_or(VerificationAvailabilitySnapshot {
            schema_version: "1.0",
            provider: "windows-hello",
            availability: application_lock_verification::VerificationAvailability::Failed,
        })
}

#[tauri::command]
fn application_lock_configure(
    profile_name: Option<String>,
    inactivity_timeout_minutes: u8,
) -> Result<ApplicationLockSnapshot, &'static str> {
    let _ = (profile_name, inactivity_timeout_minutes);
    Err("RO-SIGN-IN-TRANSITION-REQUIRED")
}

#[tauri::command]
async fn application_lock_now(
    app: AppHandle,
    supervisor: State<'_, RuntimeSupervisor>,
    support: State<'_, SupportBundleManager>,
    lock: State<'_, ApplicationLockManager>,
    picker: State<'_, DirectoryPickerManager>,
) -> Result<ApplicationLockSnapshot, &'static str> {
    let (snapshot, changed) = lock.lock(ApplicationLockReason::Manual);
    if changed {
        picker.cancel_pending();
        support.clear_pending();
        emit_lock_snapshot(&app, lock.inner(), &snapshot);
    }
    if changed {
        let supervisor = supervisor.inner().clone();
        tauri::async_runtime::spawn_blocking(move || supervisor.stop_for_application_lock())
            .await
            .map_err(|_| "RO-CORE-SUPERVISOR-FAILED")?;
    }
    Ok(snapshot)
}

#[tauri::command]
async fn application_lock_unlock(
    app: AppHandle,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
) -> Result<ApplicationUnlockAttempt, &'static str> {
    perform_application_lock_unlock(app, supervisor.inner().clone(), lock.inner().clone()).await
}

#[tauri::command]
async fn application_sign_in_transition_prepare(
    app: AppHandle,
    lock: State<'_, ApplicationLockManager>,
    target_mode: SignInMode,
    profile_name: Option<String>,
    inactivity_timeout_minutes: u8,
) -> Result<PolicyTransitionResult, &'static str> {
    let hello_window = main_window_handle(&app);
    let manager = lock.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        manager.prepare_policy_transition(
            target_mode,
            profile_name,
            inactivity_timeout_minutes,
            hello_window,
        )
    })
    .await
    .map_err(|_| "RO-SIGN-IN-TRANSITION-FAILED")?
}

#[tauri::command]
async fn application_sign_in_password_recovery_prepare(
    lock: State<'_, ApplicationLockManager>,
) -> Result<PolicyTransitionResult, &'static str> {
    let manager = lock.inner().clone();
    tauri::async_runtime::spawn_blocking(move || manager.prepare_password_recovery_reset())
        .await
        .map_err(|_| "RO-SIGN-IN-TRANSITION-FAILED")?
}

#[tauri::command]
async fn application_sign_in_transition_commit(
    app: AppHandle,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    picker: State<'_, DirectoryPickerManager>,
    handle: String,
    confirmed: bool,
) -> Result<PolicyTransitionResult, &'static str> {
    let manager = lock.inner().clone();
    let start_supervisor = supervisor.inner().clone();
    let stop_supervisor = supervisor.inner().clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        manager.commit_policy_transition_with_core(
            &handle,
            confirmed,
            || start_supervisor.start().state == RuntimeState::Ready,
            || {
                stop_supervisor.stop_for_application_lock();
            },
        )
    })
    .await
    .map_err(|_| "RO-SIGN-IN-TRANSITION-FAILED")?;
    if result.outcome == application_lock::PolicyTransitionOutcome::Committed {
        picker.cancel_pending();
        let _ = app.emit("application-lock-changed", &result.snapshot);
    }
    Ok(result)
}

async fn perform_application_lock_unlock(
    app: AppHandle,
    supervisor: RuntimeSupervisor,
    lock_manager: ApplicationLockManager,
) -> Result<ApplicationUnlockAttempt, &'static str> {
    let hello_window = main_window_handle(&app);
    let result = tauri::async_runtime::spawn_blocking(move || {
        lock_manager.reauthenticate(&supervisor, hello_window)
    })
    .await
    .map_err(|_| "RO-LOCK-AUTH-FAILED")??;
    if result.outcome == VerificationOutcome::Succeeded {
        let _ = app.emit("application-lock-changed", &result.snapshot);
    }
    Ok(result)
}

#[cfg(windows)]
fn main_window_handle(app: &AppHandle) -> Option<isize> {
    app.get_webview_window("main")
        .and_then(|window| window.hwnd().ok())
        .map(|handle| handle.0 as isize)
        .filter(|handle| *handle != 0)
}

#[cfg(not(windows))]
fn main_window_handle(_app: &AppHandle) -> Option<isize> {
    None
}

pub async fn dispatch_runtime_start(
    supervisor: RuntimeSupervisor,
) -> Result<RuntimeSnapshot, &'static str> {
    tauri::async_runtime::spawn_blocking(move || supervisor.start())
        .await
        .map_err(|_| "RO-CORE-SUPERVISOR-FAILED")
}

pub async fn dispatch_runtime_stop(
    supervisor: RuntimeSupervisor,
) -> Result<RuntimeSnapshot, &'static str> {
    tauri::async_runtime::spawn_blocking(move || supervisor.stop())
        .await
        .map_err(|_| "RO-CORE-SUPERVISOR-FAILED")
}

pub async fn dispatch_core_api_request(
    supervisor: RuntimeSupervisor,
    request: CoreApiRequest,
) -> Result<CoreApiResponse, &'static str> {
    tauri::async_runtime::spawn_blocking(move || supervisor.api_request(&request))
        .await
        .map_err(|_| "RO-CORE-API-FAILED")?
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    application_builder()
        .setup(|app| {
            let application_data = app
                .path()
                .app_local_data_dir()
                .map_err(|_| std::io::Error::other("application data unavailable"))?;
            setup_runtime(
                app,
                runtime_config(app),
                &application_data,
                DirectoryPickerManager::default(),
            )
        })
        .run(tauri::generate_context!())
        .expect("Research Observatory desktop runtime failed");
}

fn application_builder() -> tauri::Builder<tauri::Wry> {
    let handler: fn(tauri::ipc::Invoke<tauri::Wry>) -> bool = tauri::generate_handler![
        choose_project_directory,
        default_project_parent,
        core_runtime_start,
        core_runtime_status,
        core_runtime_retry,
        core_runtime_stop,
        core_runtime_diagnostics,
        core_api_request,
        support_bundle_preview,
        support_bundle_export,
        application_lock_status,
        application_lock_activity,
        application_lock_audit,
        application_lock_hello_availability,
        application_lock_configure,
        application_lock_now,
        application_lock_unlock,
        application_sign_in_transition_prepare,
        application_sign_in_password_recovery_prepare,
        application_sign_in_transition_commit
    ];
    tauri::Builder::default()
        .invoke_handler(move |invoke| {
            #[cfg(all(feature = "integration-harness", windows))]
            if invoke
                .message
                .webview()
                .try_state::<directory_integration_harness::Fixture>()
                .is_some()
                && matches!(
                    invoke.message.command(),
                    "support_bundle_preview"
                        | "support_bundle_export"
                        | "application_lock_unlock"
                        | "application_sign_in_transition_prepare"
                        | "application_sign_in_password_recovery_prepare"
                        | "application_sign_in_transition_commit"
                )
            {
                invoke.resolver.reject("RO-FIXTURE-ACTION-DENIED");
                return true;
            }
            handler(invoke)
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event
                && window.label() == "main"
            {
                let picker = window.state::<DirectoryPickerManager>().inner().clone();
                match picker.begin_close() {
                    CloseDisposition::WaitForCleanup => {
                        api.prevent_close();
                        let closing_window = window.clone();
                        tauri::async_runtime::spawn_blocking(move || {
                            picker.wait_for_cleanup();
                            // Tauri dispatches destruction to its UI thread. It
                            // must not join the STA while processing CloseRequested.
                            let _ = closing_window.destroy();
                        });
                    }
                    CloseDisposition::AlreadyClosing => {
                        api.prevent_close();
                        return;
                    }
                    CloseDisposition::CloseNow => {}
                }
                let supervisor = window.state::<RuntimeSupervisor>().inner().clone();
                tauri::async_runtime::spawn_blocking(move || supervisor.stop());
            }
        })
}

fn setup_runtime(
    app: &mut App,
    config: Result<SupervisorConfig, &'static str>,
    application_data: &std::path::Path,
    picker: DirectoryPickerManager,
) -> Result<(), Box<dyn std::error::Error>> {
    let supervisor = RuntimeSupervisor::new(config);
    let lock = ApplicationLockManager::acquire(application_data).map_err(std::io::Error::other)?;
    let support = SupportBundleManager::default();
    app.manage(supervisor.clone());
    app.manage(lock.clone());
    app.manage(support.clone());
    app.manage(picker.clone());
    if lock.is_unlocked() {
        let startup = supervisor.clone();
        tauri::async_runtime::spawn_blocking(move || startup.start());
    }
    start_lock_monitor(app.handle().clone(), lock, supervisor, support, picker);
    Ok(())
}

/// Disposable composition only: no command, environment switch, or production
/// startup path can activate this entry point.
#[cfg(all(feature = "integration-harness", windows))]
pub mod directory_integration_harness {
    use super::*;
    use crate::application_sign_in_policy::{POLICY_FILE, SignInPolicy};
    use serde_json::{Value, json};
    use std::ffi::{OsStr, OsString};
    use std::io::Write;
    use std::os::windows::{
        fs::{MetadataExt, OpenOptionsExt},
        io::AsRawHandle,
        process::CommandExt,
    };
    use std::path::{Path, PathBuf};
    use std::time::{Duration, Instant};
    use windows_sys::Win32::Storage::FileSystem::{
        BY_HANDLE_FILE_INFORMATION, GetFileInformationByHandle,
    };

    #[derive(Clone, Copy, Debug, Eq, PartialEq)]
    pub enum Mode {
        Selection,
        ManualLock,
        MainClose,
    }

    impl Mode {
        pub fn parse(value: &str) -> Option<Self> {
            match value {
                "selection" => Some(Self::Selection),
                "manual-lock" => Some(Self::ManualLock),
                "main-close" => Some(Self::MainClose),
                _ => None,
            }
        }
        fn name(self) -> &'static str {
            match self {
                Self::Selection => "selection",
                Self::ManualLock => "manual-lock",
                Self::MainClose => "main-close",
            }
        }
    }

    #[derive(Clone)]
    pub(crate) struct Fixture {
        root: PathBuf,
        application_data: PathBuf,
        pub(crate) projects: PathBuf,
        vault: PathBuf,
        webview: PathBuf,
        temporary: PathBuf,
        pins: std::sync::Arc<Vec<PinnedDirectory>>,
    }

    struct PinnedDirectory {
        path: PathBuf,
        handle: std::fs::File,
        identity: (u64, u64),
    }

    fn directory_identity(handle: &std::fs::File) -> Result<(u64, u64), &'static str> {
        let mut information = BY_HANDLE_FILE_INFORMATION::default();
        if unsafe { GetFileInformationByHandle(handle.as_raw_handle(), &mut information) } == 0
            || information.dwFileAttributes & 0x10 == 0
            || information.dwFileAttributes & 0x400 != 0
        {
            return Err("probe-fixture-identity-invalid");
        }
        Ok((
            u64::from(information.dwVolumeSerialNumber),
            (u64::from(information.nFileIndexHigh) << 32) | u64::from(information.nFileIndexLow),
        ))
    }

    fn open_pinned_directory(path: &Path) -> Result<std::fs::File, &'static str> {
        // List-directory + read attributes; share reads only. Attribute-only
        // handles do not participate in Windows share-delete denial. Denying
        // directory write/delete
        // sharing prevents rename and in-place reparse substitution while
        // ordinary creation/opening of child files remains available.
        std::fs::OpenOptions::new()
            .access_mode(0x81)
            .share_mode(0x1)
            .custom_flags(0x02000000 | 0x00200000)
            .open(path)
            .map_err(|_| "probe-fixture-pin-unavailable")
    }

    impl PinnedDirectory {
        fn acquire(path: PathBuf) -> Result<Self, &'static str> {
            let handle = open_pinned_directory(&path)?;
            let identity = directory_identity(&handle)?;
            Ok(Self {
                path,
                handle,
                identity,
            })
        }

        fn revalidate(&self) -> Result<(), &'static str> {
            // Inspect the already-open object before looking up the name. A
            // reparse attribute cannot be mistaken for an unchanged identity.
            if directory_identity(&self.handle)? != self.identity {
                return Err("probe-fixture-identity-invalid");
            }
            let current = open_pinned_directory(&self.path)?;
            if directory_identity(&current)? != self.identity {
                return Err("probe-fixture-identity-invalid");
            }
            Ok(())
        }
    }

    fn pin_ancestors(path: &Path) -> Result<Vec<PinnedDirectory>, &'static str> {
        let mut pins = Vec::new();
        let mut current = PathBuf::new();
        for component in path.components() {
            current.push(component);
            if current.is_absolute() {
                pins.push(PinnedDirectory::acquire(current.clone())?);
            }
        }
        Ok(pins)
    }

    fn emit(value: Value) {
        let mut output = std::io::stdout().lock();
        let _ = serde_json::to_writer(&mut output, &value);
        let _ = output.write_all(b"\n").and_then(|_| output.flush());
    }

    pub(crate) fn observe_result(result: &DirectoryOutcome) {
        let status = match result {
            DirectoryOutcome::Selected { .. } => "selected",
            DirectoryOutcome::Cancelled => "cancelled",
            DirectoryOutcome::Unavailable => "unavailable",
            DirectoryOutcome::Failed => "failed",
        };
        emit(json!({"kind":"tauri-directory-result", "status":status,
            "scope":"actual-tauri-ipc-fixture-storage-no-credential-proof"}));
    }

    fn validate_directory(path: &Path) -> Result<(), &'static str> {
        if !path.is_absolute() {
            return Err("probe-fixture-invalid");
        }
        let mut current = PathBuf::new();
        for component in path.components() {
            if matches!(
                component,
                std::path::Component::ParentDir | std::path::Component::CurDir
            ) {
                return Err("probe-fixture-invalid");
            }
            current.push(component);
            if !current.is_absolute() {
                continue;
            }
            let metadata =
                std::fs::symlink_metadata(&current).map_err(|_| "probe-fixture-unavailable")?;
            if !metadata.is_dir()
                || metadata.file_type().is_symlink()
                || metadata.file_attributes() & 0x400 != 0
            {
                return Err("probe-fixture-invalid");
            }
        }
        if dunce::canonicalize(path).map_err(|_| "probe-fixture-unavailable")? != path {
            return Err("probe-fixture-invalid");
        }
        Ok(())
    }

    fn repository() -> Result<PathBuf, &'static str> {
        let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let repo = manifest
            .ancestors()
            .nth(3)
            .ok_or("probe-repository-unavailable")?
            .to_owned();
        if repo.join("apps/desktop/src-tauri") != manifest {
            return Err("probe-repository-unavailable");
        }
        validate_directory(&manifest)?;
        validate_directory(&repo.join("artifacts/tmp"))?;
        Ok(repo)
    }

    fn valid_nonce(value: &str) -> bool {
        (1..=96).contains(&value.len())
            && value
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
    }

    fn validate_environment(names: impl IntoIterator<Item = OsString>) -> Result<(), &'static str> {
        if names.into_iter().any(|name| {
            name.to_string_lossy()
                .to_ascii_uppercase()
                .starts_with("WEBVIEW2_")
        }) {
            return Err("probe-webview-environment-override-denied");
        }
        Ok(())
    }

    impl Fixture {
        fn relative_root(&self) -> String {
            format!(
                "artifacts/tmp/{}",
                self.root.file_name().unwrap().to_string_lossy()
            )
        }

        fn create(nonce: &str) -> Result<Self, &'static str> {
            // Reject path-like input before resolving or inspecting any caller
            // target; an occupied child is never reused or cleaned up.
            if !valid_nonce(nonce) {
                return Err("probe-fixture-name-invalid");
            }
            let repo = repository()?;
            let mut pins = pin_ancestors(&repo.join("artifacts/tmp"))?;
            let root = repo
                .join("artifacts/tmp")
                .join(format!("directory-dialog-{nonce}"));
            std::fs::create_dir(&root).map_err(|_| "probe-fixture-create-denied")?;
            pins.push(PinnedDirectory::acquire(root.clone())?);
            validate_directory(&root)?;
            let mut fixture = Self {
                application_data: root.join("application-data"),
                projects: root.join("projects"),
                vault: root.join("vault"),
                webview: root.join("webview"),
                temporary: root.join("temporary"),
                root,
                pins: std::sync::Arc::new(Vec::new()),
            };
            for path in [
                &fixture.application_data,
                &fixture.projects,
                &fixture.vault,
                &fixture.webview,
                &fixture.temporary,
            ] {
                std::fs::create_dir(path).map_err(|_| "probe-fixture-create-denied")?;
                pins.push(PinnedDirectory::acquire(path.clone())?);
                validate_directory(path)?;
            }
            let security = fixture.application_data.join("security");
            std::fs::create_dir(&security).map_err(|_| "probe-fixture-create-denied")?;
            pins.push(PinnedDirectory::acquire(security.clone())?);
            let policy = SignInPolicy::normalized_target(1, SignInMode::WindowsPassword, None, 0)
                .and_then(|policy| policy.canonical_bytes())?;
            let mut file = std::fs::File::create_new(security.join(POLICY_FILE))
                .map_err(|_| "probe-policy-create-denied")?;
            file.write_all(&policy)
                .and_then(|_| file.sync_all())
                .map_err(|_| "probe-policy-create-denied")?;
            fixture.pins = std::sync::Arc::new(pins);
            fixture.revalidate()?;
            Ok(fixture)
        }

        pub(crate) fn revalidate(&self) -> Result<(), &'static str> {
            for pin in self.pins.iter() {
                pin.revalidate()?;
            }
            Ok(())
        }

        pub(crate) fn permits_request(&self, request: &CoreApiRequest) -> bool {
            if self.revalidate().is_err() {
                return false;
            }
            if request.method == "GET"
                && request.path == "/workflow-profiles/catalog"
                && request.body.is_none()
            {
                return true;
            }
            if request.method != "POST" {
                return false;
            }
            let Some(body) = request
                .body
                .as_deref()
                .and_then(|body| serde_json::from_str::<Value>(body).ok())
            else {
                return false;
            };
            let paths = [body.get("parentDirectory"), body.get("root")];
            if paths.iter().all(Option::is_none) {
                return false;
            }
            paths.into_iter().flatten().all(|path| {
                path.as_str()
                    .is_some_and(|path| directory_picker::fixture_contains(&self.projects, path))
            })
        }

        fn supervisor_config(&self) -> Result<SupervisorConfig, &'static str> {
            self.revalidate()?;
            let repo = repository()?;
            let venv_python = repo.join(".venv/Scripts/python.exe");
            let output = std::process::Command::new(venv_python)
                .args(["-I", "-c", "import sys; print(sys._base_executable)"])
                .creation_flags(0x08000000)
                .output()
                .map_err(|_| "probe-python-unavailable")?;
            if !output.status.success() {
                return Err("probe-python-unavailable");
            }
            let executable =
                String::from_utf8(output.stdout).map_err(|_| "probe-python-unavailable")?;
            let python_path = std::env::join_paths([
                repo.join("tests/service/fixtures"),
                repo.join("services/core-api/src"),
                repo.join(".venv/Lib/site-packages"),
            ])
            .map_err(|_| "probe-python-unavailable")?;
            SupervisorConfig::for_integration_harness(
                PathBuf::from(executable.trim()),
                self.root.clone(),
                vec![
                    "-m".into(),
                    "native_integration_sidecar".into(),
                    "--profile-vault-root".into(),
                    self.vault.as_os_str().to_owned(),
                ],
                vec![
                    ("PYTHONPATH".into(), python_path),
                    ("PYTHONDONTWRITEBYTECODE".into(), "1".into()),
                    ("TEMP".into(), self.temporary.as_os_str().to_owned()),
                    ("TMP".into(), self.temporary.as_os_str().to_owned()),
                ],
            )
        }
    }

    fn observe_pending(app: AppHandle, mode: Mode) {
        std::thread::spawn(move || {
            let picker = app.state::<DirectoryPickerManager>().inner().clone();
            let deadline = Instant::now() + Duration::from_secs(180);
            while !picker.has_pending() {
                if !picker.is_open() || Instant::now() >= deadline {
                    return;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            emit(
                json!({"kind":"tauri-directory-admitted", "mode":mode.name(),
                "coreState":app.state::<RuntimeSupervisor>().status().state}),
            );
            if mode != Mode::Selection {
                std::thread::sleep(Duration::from_secs(10));
                if !picker.has_pending() || !picker.is_open() {
                    emit(json!({"kind":"tauri-directory-trigger-skipped", "mode":mode.name()}));
                    return;
                }
                match mode {
                    Mode::ManualLock => {
                        let result = tauri::async_runtime::block_on(application_lock_now(
                            app.clone(),
                            app.state::<RuntimeSupervisor>(),
                            app.state::<SupportBundleManager>(),
                            app.state::<ApplicationLockManager>(),
                            app.state::<DirectoryPickerManager>(),
                        ));
                        emit(
                            json!({"kind":"tauri-directory-manual-lock", "succeeded":result.is_ok(),
                            "state":app.state::<ApplicationLockManager>().status().state}),
                        );
                    }
                    Mode::MainClose => {
                        let requested = app
                            .get_webview_window("main")
                            .is_some_and(|window| window.close().is_ok());
                        emit(json!({"kind":"tauri-directory-main-close", "requested":requested}));
                    }
                    Mode::Selection => {}
                }
            }
            let deadline = Instant::now() + Duration::from_secs(180);
            while picker.has_pending() && Instant::now() < deadline {
                std::thread::sleep(Duration::from_millis(25));
            }
            emit(
                json!({"kind":"tauri-directory-cleanup", "pending":picker.has_pending(),
                "admissionOpen":picker.is_open(), "mode":mode.name(),
                "coreState":app.state::<RuntimeSupervisor>().status().state}),
            );
        });
    }

    pub fn run(mode: Mode, nonce: &OsStr) -> Result<(), &'static str> {
        validate_environment(std::env::vars_os().map(|(name, _)| name))?;
        let fixture = Fixture::create(nonce.to_str().ok_or("probe-fixture-name-invalid")?)?;
        let config = fixture.supervisor_config()?;
        let mut context = tauri::generate_context!();
        let window_config = context
            .config()
            .app
            .windows
            .iter()
            .find(|window| window.label == "main")
            .cloned()
            .ok_or("probe-main-config-unavailable")?;
        for window in &mut context.config_mut().app.windows {
            window.create = false;
        }
        let retained = fixture.clone();
        let application = application_builder().setup(move |app| {
            app.manage(fixture.clone());
            fixture.revalidate().map_err(std::io::Error::other)?;
            setup_runtime(app, Ok(config), &fixture.application_data, DirectoryPickerManager::for_fixture(fixture.projects.clone()))?;
            // A WindowConfig absolute data_directory is ignored by Tauri;
            // the direct builder API is the actual WebView storage boundary.
            fixture.revalidate().map_err(|error| {
                app.state::<RuntimeSupervisor>().stop();
                std::io::Error::other(error)
            })?;
            let main = tauri::WebviewWindowBuilder::from_config(app, &window_config)
                .and_then(|builder| builder
                .data_directory(fixture.webview.clone())
                .title(format!("Research Observatory — SYNTHETIC T03 {}", mode.name())).build())
                .inspect_err(|_| { app.state::<RuntimeSupervisor>().stop(); })?;
            emit(json!({"kind":"tauri-directory-start", "mode":mode.name(), "fixture":fixture.relative_root(),
                "ownerHwnd":main.hwnd().ok().map(|handle| handle.0 as isize),
                "fixtureSubstitutions":["policy-root", "Core-vault", "WebView-data-directory", "Core-temp", "default-project-parent"],
                "scope":"actual-renderer-tauri-ipc-lock-and-close-with-fixture-storage",
                "credentialsInvoked":false, "productionPackagedQualification":false,
                "projects":format!("{}/projects", fixture.relative_root()), "fixturesRetained":true}));
            observe_pending(app.handle().clone(), mode);
            Ok(())
        }).build(context).map_err(|_| "probe-tauri-build-failed")?;
        // Builder::build has not run setup. Capture native clones only on Ready,
        // and use no Tauri API after run_return performs its runtime cleanup.
        let managed = std::sync::Arc::new(std::sync::Mutex::new(None));
        let ready_managed = std::sync::Arc::clone(&managed);
        let exit_code = application.run_return(move |handle, event| {
            if matches!(event, tauri::RunEvent::Ready)
                && let (Some(supervisor), Some(picker)) = (
                    handle.try_state::<RuntimeSupervisor>(),
                    handle.try_state::<DirectoryPickerManager>(),
                )
            {
                *ready_managed
                    .lock()
                    .unwrap_or_else(|poisoned| poisoned.into_inner()) =
                    Some((supervisor.inner().clone(), picker.inner().clone()));
            }
        });
        let (supervisor, picker) = managed
            .lock()
            .map_err(|_| "probe-tauri-runtime-not-initialized")?
            .take()
            .ok_or("probe-tauri-runtime-not-initialized")?;
        supervisor.stop();
        emit(
            json!({"kind":"tauri-directory-exit", "fixture":retained.relative_root(),
            "pending":picker.has_pending(), "admissionOpen":picker.is_open(), "fixturesRetained":true,
            "exitCode":exit_code}),
        );
        if exit_code == 0 {
            Ok(())
        } else {
            Err("probe-tauri-runtime-failed")
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use crate::application_sign_in_policy::secure_random_hex;

        fn nonce() -> String {
            format!("unit-{}", secure_random_hex::<16>().unwrap())
        }

        #[test]
        fn harness_runs_setup_before_reading_managed_state() {
            let source = include_str!("lib.rs");
            let run = source
                .split_once("pub fn run(mode: Mode, nonce: &OsStr)")
                .unwrap()
                .1
                .split_once("#[cfg(test)]")
                .unwrap()
                .0;
            let (before_run, after_run) = run.split_once("application.run_return(").unwrap();
            let after_build = before_run
                .rsplit_once("probe-tauri-build-failed")
                .unwrap()
                .1;
            assert!(
                !after_build.contains(".state::<"),
                "Builder::build has not executed setup"
            );
            assert!(
                !after_build.contains(".try_state::<"),
                "managed state belongs after setup"
            );
            assert!(after_build.contains("Arc::clone(&managed)"));
            assert!(after_run.contains("tauri::RunEvent::Ready"));
            assert!(after_run.contains(".try_state::<RuntimeSupervisor>()"));
            assert!(after_run.contains(".try_state::<DirectoryPickerManager>()"));
            let shutdown = after_run
                .split_once("let (supervisor, picker) = managed")
                .unwrap()
                .1;
            assert!(!shutdown.contains(".state::<"));
            assert!(!shutdown.contains(".try_state::<"));
            assert!(after_run.contains("supervisor.stop()"));
            assert!(after_run.contains("retained.relative_root()"));
        }

        #[test]
        fn fixture_creation_denies_path_input_and_occupied_root_without_reuse() {
            for invalid in [
                "",
                ".",
                "..",
                "../outside",
                "C:\\outside",
                "\\\\server\\share",
                "nested/name",
                "name with space",
                "name\n",
            ] {
                assert!(matches!(
                    Fixture::create(invalid),
                    Err("probe-fixture-name-invalid")
                ));
            }
            assert!(!valid_nonce(&"a".repeat(97)));
            let name = nonce();
            let fixture = Fixture::create(&name).unwrap();
            let policy_path = fixture.application_data.join("security").join(POLICY_FILE);
            let before = std::fs::read(&policy_path).unwrap();
            assert!(matches!(
                Fixture::create(&name),
                Err("probe-fixture-create-denied")
            ));
            assert_eq!(std::fs::read(&policy_path).unwrap(), before);
            assert_eq!(
                fixture.root.parent(),
                Some(repository().unwrap().join("artifacts/tmp").as_path())
            );
            assert!(fixture.webview.starts_with(&fixture.root));
            assert!(fixture.vault.starts_with(&fixture.root));
            assert!(fixture.application_data.starts_with(&fixture.root));
            assert!(fixture.projects.starts_with(&fixture.root));
            // Retained disposable fixture, never a current-user profile.
        }

        #[test]
        fn occupied_junction_fixture_is_denied_without_target_changes() {
            let target = Fixture::create(&nonce()).unwrap();
            let name = nonce();
            let link = repository()
                .unwrap()
                .join("artifacts/tmp")
                .join(format!("directory-dialog-{name}"));
            let policy_path = target.application_data.join("security").join(POLICY_FILE);
            let before = std::fs::read(&policy_path).unwrap();
            let powershell = PathBuf::from(std::env::var_os("SystemRoot").unwrap())
                .join("System32/WindowsPowerShell/v1.0/powershell.exe");
            let result = std::process::Command::new(powershell).args([
                "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
                "$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path $env:RO_T03_FIXTURE_LINK -Target $env:RO_T03_FIXTURE_TARGET | Out-Null",
            ]).env("RO_T03_FIXTURE_LINK", &link).env("RO_T03_FIXTURE_TARGET", &target.root)
                .creation_flags(0x08000000).output().unwrap();
            assert!(result.status.success());
            assert_eq!(validate_directory(&link), Err("probe-fixture-invalid"));
            assert!(matches!(
                Fixture::create(&name),
                Err("probe-fixture-create-denied")
            ));
            assert_eq!(std::fs::read(policy_path).unwrap(), before);
            std::fs::remove_dir(&link).unwrap();
            assert!(target.root.is_dir());
        }

        #[test]
        fn fixture_core_boundary_denies_outside_and_substituted_roots() {
            let fixture = Fixture::create(&nonce()).unwrap();
            let request = |body: Value| CoreApiRequest {
                method: "POST".into(),
                path: "/projects/open".into(),
                body: Some(body.to_string()),
                if_match: None,
                idempotency_key: None,
            };
            assert!(
                fixture
                    .permits_request(&request(json!({"root":fixture.projects.join("synthetic")})))
            );
            for body in [
                json!({}),
                json!({"root":"C:\\outside"}),
                json!({"root":fixture.root}),
                json!({"root":fixture.projects.join("../vault")}),
                json!({"root":null}),
                json!({"parentDirectory":fixture.projects,"root":"C:\\outside"}),
            ] {
                assert!(!fixture.permits_request(&request(body)));
            }
        }

        #[test]
        fn webview_environment_overrides_are_denied_without_environment_mutation() {
            assert!(
                validate_environment([OsString::from("SystemRoot"), OsString::from("PATH")])
                    .is_ok()
            );
            for name in [
                "WEBVIEW2_USER_DATA_FOLDER",
                "WEBVIEW2_BROWSER_EXECUTABLE_FOLDER",
                "webview2_additional_browser_arguments",
                "WEBVIEW2_OTHER",
            ] {
                assert_eq!(
                    validate_environment([OsString::from(name)]),
                    Err("probe-webview-environment-override-denied")
                );
            }
        }

        #[test]
        fn created_fixture_pins_block_directory_substitution_through_consumer_lifetime() {
            let fixture = Fixture::create(&nonce()).unwrap();
            for path in [
                &fixture.application_data,
                &fixture.application_data.join("security"),
                &fixture.webview,
                &fixture.vault,
                &fixture.projects,
                &fixture.temporary,
            ] {
                let replacement = path.with_file_name(format!(
                    "{}-substituted",
                    path.file_name().unwrap().to_string_lossy()
                ));
                assert!(
                    std::fs::rename(path, replacement).is_err(),
                    "pinned directory cannot be renamed"
                );
                fixture.revalidate().unwrap();
            }
            // Holding the fixture through consumer shutdown keeps the same
            // identities pinned even if an earlier setup owner is dropped.
            let consumer = fixture.clone();
            drop(fixture);
            assert!(
                std::fs::rename(&consumer.webview, consumer.root.join("late-substitution"))
                    .is_err()
            );
            consumer.revalidate().unwrap();
            let child = consumer.projects.join("synthetic-child");
            std::fs::create_dir(&child).unwrap();
            assert!(
                child.is_dir(),
                "pins still permit ordinary fixture project creation"
            );
        }
    }
}

fn start_lock_monitor(
    app: AppHandle,
    lock: ApplicationLockManager,
    supervisor: RuntimeSupervisor,
    support: SupportBundleManager,
    picker: DirectoryPickerManager,
) {
    std::thread::spawn(move || {
        loop {
            std::thread::sleep(std::time::Duration::from_secs(1));
            if let Some(snapshot) = lock.lock_if_idle() {
                picker.cancel_pending();
                support.clear_pending();
                emit_lock_snapshot(&app, &lock, &snapshot);
                supervisor.stop_for_application_lock();
            }
        }
    });
}

fn emit_lock_snapshot(
    app: &AppHandle,
    lock: &ApplicationLockManager,
    snapshot: &ApplicationLockSnapshot,
) {
    if app.emit("application-lock-changed", snapshot).is_err() {
        lock.record_notification_failure();
    }
}

fn runtime_config<R: Runtime>(app: &App<R>) -> Result<SupervisorConfig, &'static str> {
    let resource_root = app
        .path()
        .resource_dir()
        .map_err(|_| "RO-CORE-NOT-PACKAGED")?;
    if let Ok(config) = SupervisorConfig::from_resource_root(&resource_root) {
        return Ok(config);
    }
    #[cfg(debug_assertions)]
    {
        let development_executable = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../../artifacts/tmp/core-sidecar-package/dist")
            .join("research-observatory-core-x86_64-pc-windows-msvc")
            .join("research-observatory-core-x86_64-pc-windows-msvc.exe");
        let canonical =
            dunce::canonicalize(development_executable).map_err(|_| "RO-CORE-NOT-PACKAGED")?;
        SupervisorConfig::new(canonical)
    }
    #[cfg(not(debug_assertions))]
    Err("RO-CORE-NOT-PACKAGED")
}

#[cfg(test)]
mod tests {
    use super::{PRODUCT_NAME, directory_origin_allowed};
    use tauri::ipc::Origin;

    #[test]
    fn product_identity_is_stable() {
        assert_eq!(PRODUCT_NAME, "Research Observatory");
    }

    #[test]
    fn production_entrypoint_has_no_fixture_switch_or_fixture_ipc() {
        let source = include_str!("lib.rs");
        let production = source
            .split_once("pub fn run() {")
            .unwrap()
            .1
            .split_once("fn application_builder()")
            .unwrap()
            .0;
        assert!(production.contains("runtime_config(app)"));
        assert!(production.contains("app_local_data_dir()"));
        assert!(production.contains("DirectoryPickerManager::default()"));
        for forbidden in [
            "fixture",
            "args_os",
            "var_os",
            "directory_integration_harness",
        ] {
            assert!(!production.contains(forbidden));
        }
        let prefix = source
            .split_once("pub mod directory_integration_harness {")
            .unwrap()
            .0;
        assert!(
            prefix
                .trim_end()
                .ends_with("#[cfg(all(feature = \"integration-harness\", windows))]")
        );
        let handlers = source
            .split_once("tauri::generate_handler![")
            .unwrap()
            .1
            .split_once("];")
            .unwrap()
            .0;
        assert!(!handlers.contains("fixture"));
        assert!(!handlers.contains("integration"));
    }

    #[test]
    fn directory_commands_admit_only_the_local_main_window_origin() {
        for url in [
            "tauri://localhost/index.html",
            "http://tauri.localhost",
            "https://tauri.localhost/index.html",
        ] {
            let url = tauri::Url::parse(url).unwrap();
            assert!(directory_origin_allowed("main", &url));
            assert!(!directory_origin_allowed("secondary", &url));
        }
        for url in [
            "https://example.invalid",
            "https://tauri.localhost.example.invalid",
            "http://localhost:1420",
            "file:///C:/index.html",
            "http://tauri.localhost:1234",
            "https://user@tauri.localhost",
        ] {
            assert!(!directory_origin_allowed(
                "main",
                &tauri::Url::parse(url).unwrap()
            ));
        }
    }

    #[test]
    fn main_window_event_capability_is_receive_only() {
        let mut context: tauri::Context<tauri::Wry> = tauri::generate_context!();
        let authority = context.runtime_authority_mut();
        let local = Origin::Local;
        let remote = Origin::Remote {
            url: "https://example.invalid".parse().expect("valid remote URL"),
        };

        for command in [
            "plugin:webview|internal_toggle_devtools",
            "plugin:event|listen",
            "plugin:event|unlisten",
        ] {
            assert!(
                authority
                    .resolve_access(command, "main", "main", &local)
                    .is_some(),
                "{command} must be allowed for the local main window"
            );
            assert!(
                authority
                    .resolve_access(command, "secondary", "secondary", &local)
                    .is_none(),
                "{command} must be denied outside the main window"
            );
            assert!(
                authority
                    .resolve_access(command, "main", "main", &remote)
                    .is_none(),
                "{command} must be denied to remote origins"
            );
        }
        for command in ["plugin:event|emit", "plugin:event|emit_to"] {
            assert!(
                authority
                    .resolve_access(command, "main", "main", &local)
                    .is_none(),
                "{command} must remain denied for the local main window"
            );
        }
    }
}
