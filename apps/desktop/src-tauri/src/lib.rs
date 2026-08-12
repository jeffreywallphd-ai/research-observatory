pub mod supervisor;
pub mod support_bundle;

use supervisor::{
    CoreApiRequest, CoreApiResponse, RuntimeDiagnostic, RuntimeSnapshot, RuntimeSupervisor,
    SupervisorConfig,
};
use support_bundle::{SupportBundleExport, SupportBundleManager, SupportBundlePreview};
use tauri::{App, AppHandle, Manager, Runtime, State};

pub const PRODUCT_NAME: &str = "Research Observatory";

#[tauri::command]
async fn core_runtime_start(
    supervisor: State<'_, RuntimeSupervisor>,
) -> Result<RuntimeSnapshot, &'static str> {
    dispatch_runtime_start(supervisor.inner().clone()).await
}

#[tauri::command]
fn core_runtime_status(supervisor: State<'_, RuntimeSupervisor>) -> RuntimeSnapshot {
    supervisor.status()
}

#[tauri::command]
async fn core_runtime_retry(
    supervisor: State<'_, RuntimeSupervisor>,
) -> Result<RuntimeSnapshot, &'static str> {
    dispatch_runtime_start(supervisor.inner().clone()).await
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
    request: CoreApiRequest,
) -> Result<CoreApiResponse, &'static str> {
    dispatch_core_api_request(supervisor.inner().clone(), request).await
}

#[tauri::command]
async fn support_bundle_preview(
    app: AppHandle,
    supervisor: State<'_, RuntimeSupervisor>,
    manager: State<'_, SupportBundleManager>,
) -> Result<SupportBundlePreview, &'static str> {
    let application_data = app
        .path()
        .app_local_data_dir()
        .map_err(|_| "RO-SUPPORT-PATH-UNAVAILABLE")?;
    let supervisor = supervisor.inner().clone();
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || manager.preview(&application_data, &supervisor))
        .await
        .map_err(|_| "RO-SUPPORT-COLLECTION-FAILED")?
}

#[tauri::command]
async fn support_bundle_export(
    app: AppHandle,
    manager: State<'_, SupportBundleManager>,
    preview_id: String,
) -> Result<SupportBundleExport, &'static str> {
    let application_data = app
        .path()
        .app_local_data_dir()
        .map_err(|_| "RO-SUPPORT-PATH-UNAVAILABLE")?;
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || manager.export(&application_data, &preview_id))
        .await
        .map_err(|_| "RO-SUPPORT-WRITE-FAILED")?
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
            support_bundle_export
        ])
        .setup(|app| {
            let supervisor = RuntimeSupervisor::new(runtime_config(app));
            app.manage(supervisor.clone());
            app.manage(SupportBundleManager::default());
            let startup = supervisor.clone();
            tauri::async_runtime::spawn_blocking(move || startup.start());
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
