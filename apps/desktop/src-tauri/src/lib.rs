pub mod application_lock;
pub mod application_lock_verification;
pub mod supervisor;
pub mod support_bundle;

use application_lock::{
    ApplicationLockAuditEvent, ApplicationLockManager, ApplicationLockReason,
    ApplicationLockSnapshot, ApplicationUnlockAttempt,
};
use application_lock_verification::VerificationOutcome;
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
fn application_lock_configure(
    app: AppHandle,
    lock: State<'_, ApplicationLockManager>,
    profile_name: Option<String>,
    inactivity_timeout_minutes: u8,
) -> Result<ApplicationLockSnapshot, &'static str> {
    let snapshot = lock.configure(profile_name, inactivity_timeout_minutes)?;
    let _ = app.emit("application-lock-changed", &snapshot);
    Ok(snapshot)
}

#[tauri::command]
async fn application_lock_now(
    app: AppHandle,
    supervisor: State<'_, RuntimeSupervisor>,
    support: State<'_, SupportBundleManager>,
    lock: State<'_, ApplicationLockManager>,
) -> Result<ApplicationLockSnapshot, &'static str> {
    let (snapshot, changed) = lock.lock(ApplicationLockReason::Manual);
    support.clear_pending();
    if changed {
        emit_lock_snapshot(&app, lock.inner(), &snapshot);
    }
    let supervisor = supervisor.inner().clone();
    tauri::async_runtime::spawn_blocking(move || supervisor.stop_for_application_lock())
        .await
        .map_err(|_| "RO-CORE-SUPERVISOR-FAILED")?;
    Ok(snapshot)
}

#[tauri::command]
async fn application_lock_unlock(
    app: AppHandle,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
) -> Result<ApplicationUnlockAttempt, &'static str> {
    let supervisor = supervisor.inner().clone();
    let lock_manager = lock.inner().clone();
    let result =
        tauri::async_runtime::spawn_blocking(move || lock_manager.reauthenticate(&supervisor))
            .await
            .map_err(|_| "RO-LOCK-AUTH-FAILED")?;
    if result.outcome == VerificationOutcome::Succeeded {
        let _ = app.emit("application-lock-changed", &result.snapshot);
    }
    Ok(result)
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
            application_lock_configure,
            application_lock_now,
            application_lock_unlock
        ])
        .setup(|app| {
            let supervisor = RuntimeSupervisor::new(runtime_config(app));
            let application_data = app
                .path()
                .app_local_data_dir()
                .map_err(|_| std::io::Error::other("application data unavailable"))?;
            let lock = ApplicationLockManager::new(&application_data);
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
