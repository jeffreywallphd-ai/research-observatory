pub mod application_lock;
pub mod application_lock_verification;
mod application_sign_in_policy;
pub mod supervisor;
pub mod support_bundle;

use application_lock::{
    ApplicationLockAuditEvent, ApplicationLockManager, ApplicationLockReason,
    ApplicationLockSnapshot, ApplicationUnlockAttempt, PolicyTransitionResult, SignInMode,
};
use application_lock_verification::{
    VerificationAvailabilitySnapshot, VerificationOutcome, windows_hello_availability_snapshot,
};
use supervisor::{
    CoreApiRequest, CoreApiResponse, RuntimeDiagnostic, RuntimeSnapshot, RuntimeSupervisor,
    SupervisorConfig,
};
use support_bundle::{SupportBundleExport, SupportBundleManager, SupportBundlePreview};
use tauri::{App, AppHandle, Emitter, Manager, Runtime, State};

pub const PRODUCT_NAME: &str = "Research Observatory";

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
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    request: CoreApiRequest,
) -> Result<CoreApiResponse, &'static str> {
    let ticket = lock.begin_protected_action()?;
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
) -> Result<ApplicationLockSnapshot, &'static str> {
    let (snapshot, changed) = lock.lock(ApplicationLockReason::Manual);
    if changed {
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
    lock: State<'_, ApplicationLockManager>,
    handle: String,
    confirmed: bool,
) -> Result<PolicyTransitionResult, &'static str> {
    let manager = lock.inner().clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        manager.commit_policy_transition(&handle, confirmed)
    })
    .await
    .map_err(|_| "RO-SIGN-IN-TRANSITION-FAILED")?;
    if result.outcome == application_lock::PolicyTransitionOutcome::Committed {
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
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
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
        ])
        .setup(|app| {
            let supervisor = RuntimeSupervisor::new(runtime_config(app));
            let application_data = app
                .path()
                .app_local_data_dir()
                .map_err(|_| std::io::Error::other("application data unavailable"))?;
            let lock = ApplicationLockManager::acquire(&application_data)
                .map_err(std::io::Error::other)?;
            let support = SupportBundleManager::default();
            app.manage(supervisor.clone());
            app.manage(lock.clone());
            app.manage(support.clone());
            if lock.is_unlocked() {
                let startup = supervisor.clone();
                tauri::async_runtime::spawn_blocking(move || startup.start());
            }
            start_lock_monitor(app.handle().clone(), lock, supervisor, support);
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                let supervisor = window.state::<RuntimeSupervisor>().inner().clone();
                tauri::async_runtime::spawn_blocking(move || supervisor.stop());
            }
        })
        .run(tauri::generate_context!())
        .expect("Research Observatory desktop runtime failed");
}

fn start_lock_monitor(
    app: AppHandle,
    lock: ApplicationLockManager,
    supervisor: RuntimeSupervisor,
    support: SupportBundleManager,
) {
    std::thread::spawn(move || {
        loop {
            std::thread::sleep(std::time::Duration::from_secs(1));
            if let Some(snapshot) = lock.lock_if_idle() {
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
    use super::PRODUCT_NAME;

    #[test]
    fn product_identity_is_stable() {
        assert_eq!(PRODUCT_NAME, "Research Observatory");
    }
}
