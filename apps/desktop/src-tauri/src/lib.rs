pub mod supervisor;

use supervisor::{RuntimeDiagnostic, RuntimeSnapshot, RuntimeSupervisor, SupervisorConfig};
use tauri::{App, Manager, Runtime, State};

pub const PRODUCT_NAME: &str = "Research Observatory";

#[tauri::command]
fn core_runtime_start(supervisor: State<'_, RuntimeSupervisor>) -> RuntimeSnapshot {
    supervisor.start()
}

#[tauri::command]
fn core_runtime_status(supervisor: State<'_, RuntimeSupervisor>) -> RuntimeSnapshot {
    supervisor.status()
}

#[tauri::command]
fn core_runtime_retry(supervisor: State<'_, RuntimeSupervisor>) -> RuntimeSnapshot {
    supervisor.start()
}

#[tauri::command]
fn core_runtime_stop(supervisor: State<'_, RuntimeSupervisor>) -> RuntimeSnapshot {
    supervisor.stop()
}

#[tauri::command]
fn core_runtime_diagnostics(supervisor: State<'_, RuntimeSupervisor>) -> Vec<RuntimeDiagnostic> {
    supervisor.diagnostics()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            core_runtime_start,
            core_runtime_status,
            core_runtime_retry,
            core_runtime_stop,
            core_runtime_diagnostics
        ])
        .setup(|app| {
            let supervisor = RuntimeSupervisor::new(runtime_config(app));
            app.manage(supervisor.clone());
            let startup = supervisor.clone();
            tauri::async_runtime::spawn_blocking(move || startup.start());
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                let _ = window.state::<RuntimeSupervisor>().stop();
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
