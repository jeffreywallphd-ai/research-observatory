pub mod application_lock;
pub mod application_lock_verification;
mod application_sign_in_policy;
mod connector_configuration;
#[cfg(windows)]
mod connector_configuration_dialog;
pub mod directory_picker;
#[cfg(windows)]
mod document_attachment;
#[cfg(windows)]
mod document_drop;
#[cfg(windows)]
mod document_reader;
#[cfg(windows)]
mod document_runtime;
#[cfg(windows)]
mod import_report;
mod import_runtime;
#[cfg(windows)]
mod import_source;
mod plugin_intake;
mod reconciliation_admission;
pub mod supervisor;
pub mod support_bundle;
mod workflow_session;

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

/// Opens only the four fixed public policy pages, never a caller-supplied URL,
/// research query, file path or command. The UI labels the external browser action.
#[tauri::command]
async fn open_scholarly_source_terms(
    window: tauri::WebviewWindow,
    lock: State<'_, ApplicationLockManager>,
    provider_id: connector_configuration::Provider,
) -> Result<(), ()> {
    let owner = directory_window_handle(&window).ok_or(())?;
    let ticket = lock.begin_protected_action().map_err(|_| ())?;
    let security = lock.inner().clone();
    #[cfg(windows)]
    return tauri::async_runtime::spawn_blocking(move || {
        security.finish_protected_action(ticket).map_err(|_| ())?;
        let address: Vec<u16> = connector_configuration::terms_url(provider_id)
            .encode_utf16()
            .chain([0])
            .collect();
        let verb: Vec<u16> = "open".encode_utf16().chain([0]).collect();
        let result = unsafe {
            windows_sys::Win32::UI::Shell::ShellExecuteW(
                owner as _,
                verb.as_ptr(),
                address.as_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL,
            )
        };
        if result as isize > 32 {
            Ok(())
        } else {
            Err(())
        }
    })
    .await
    .map_err(|_| ())?;
    #[cfg(not(windows))]
    {
        let _ = (owner, security, ticket, provider_id);
        Err(())
    }
}

#[tauri::command]
async fn configure_scholarly_source(
    window: tauri::WebviewWindow,
    manager: State<'_, connector_configuration::ConfigurationManager>,
    picker: State<'_, DirectoryPickerManager>,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    message: tauri::ipc::Request<'_>,
) -> Result<connector_configuration::ConfigurationOutcome, ()> {
    use connector_configuration::ConfigurationOutcome;
    let tauri::ipc::InvokeBody::Json(payload) = message.body() else {
        return Ok(ConfigurationOutcome::Unavailable);
    };
    let Some(request) = connector_configuration::decode_request(payload) else {
        return Ok(ConfigurationOutcome::Unavailable);
    };
    let Some(owner) = directory_window_handle(&window) else {
        return Ok(ConfigurationOutcome::Unavailable);
    };
    #[cfg(all(feature = "integration-harness", windows))]
    if window
        .try_state::<directory_integration_harness::Fixture>()
        .is_some_and(|fixture| {
            fixture.revalidate().is_err()
                || !directory_picker::fixture_contains(&fixture.projects, &request.root)
        })
    {
        return Ok(ConfigurationOutcome::Unavailable);
    }
    let Ok(ticket) = lock.begin_protected_action() else {
        return Ok(ConfigurationOutcome::Cancelled);
    };
    #[cfg(windows)]
    {
        let (manager, picker, supervisor, security) = (
            manager.inner().clone(),
            picker.inner().clone(),
            supervisor.inner().clone(),
            lock.inner().clone(),
        );
        let result = tauri::async_runtime::spawn_blocking(move || {
            connector_configuration::configure(
                manager, picker, supervisor, security, ticket, owner, request,
            )
        })
        .await
        .unwrap_or(ConfigurationOutcome::SaveUnconfirmed);
        // No protected result is delivered to an old window/session. Once the
        // worker could have submitted, uncertainty is never called cancellation.
        if directory_window_handle(&window) != Some(owner)
            || lock.finish_protected_action(ticket).is_err()
        {
            Ok(ConfigurationOutcome::SaveUnconfirmed)
        } else {
            Ok(result)
        }
    }
    #[cfg(not(windows))]
    {
        let _ = (request, owner, manager, picker, supervisor, ticket);
        Ok(ConfigurationOutcome::Unavailable)
    }
}

#[tauri::command]
fn cancel_scholarly_source_configuration(
    window: tauri::WebviewWindow,
    manager: State<'_, connector_configuration::ConfigurationManager>,
    operation_id: String,
) -> Result<(), ()> {
    if directory_window_handle(&window).is_none() {
        return Err(());
    }
    manager.cancel(&operation_id);
    Ok(())
}

#[tauri::command]
async fn import_selected_file(
    window: tauri::WebviewWindow,
    manager: State<'_, import_runtime::ImportManager>,
    picker: State<'_, DirectoryPickerManager>,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    message: tauri::ipc::Request<'_>,
) -> Result<import_runtime::ImportOutcome, ()> {
    use import_runtime::ImportOutcome;
    let tauri::ipc::InvokeBody::Json(payload) = message.body() else {
        return Ok(ImportOutcome::Failed);
    };
    let Some(request) = import_runtime::decode_request(payload) else {
        return Ok(ImportOutcome::Failed);
    };
    let Some(owner) = directory_window_handle(&window) else {
        return Ok(ImportOutcome::Unavailable);
    };
    #[cfg(all(feature = "integration-harness", windows))]
    if window
        .try_state::<directory_integration_harness::Fixture>()
        .is_some_and(|fixture| {
            fixture.revalidate().is_err()
                || !directory_picker::fixture_contains(&fixture.projects, &request.root)
        })
    {
        return Ok(ImportOutcome::Unavailable);
    }
    let Ok(ticket) = lock.begin_protected_action() else {
        return Ok(ImportOutcome::Cancelled);
    };
    #[cfg(windows)]
    {
        let (manager, picker, supervisor, security) = (
            manager.inner().clone(),
            picker.inner().clone(),
            supervisor.inner().clone(),
            lock.inner().clone(),
        );
        let result = tauri::async_runtime::spawn_blocking(move || {
            import_runtime::prepare(
                manager, picker, supervisor, security, ticket, owner, request,
            )
        })
        .await;
        match result {
            Ok(Ok(mut prepared)) => {
                let owner_valid = directory_window_handle(&window) == Some(owner);
                let security = lock.inner().clone();
                // Rejected-result cleanup can perform a bounded cancellation RPC;
                // it must run off the UI thread and outside the security mutex.
                Ok(tauri::async_runtime::spawn_blocking(move || {
                    let accepted = owner_valid
                        && security
                            .commit_protected_action(ticket, || Ok(prepared.accept()))
                            .unwrap_or(false);
                    if accepted {
                        prepared.into_outcome()
                    } else {
                        ImportOutcome::Cancelled
                    }
                })
                .await
                .unwrap_or(ImportOutcome::Failed))
            }
            Ok(Err(error)) => Ok(import_runtime::failure(error)),
            Err(_) => Ok(ImportOutcome::Failed),
        }
    }
    #[cfg(not(windows))]
    {
        let _ = (manager, picker, supervisor, request, owner, ticket);
        Ok(ImportOutcome::Unavailable)
    }
}

#[tauri::command]
async fn select_connector_package(
    window: tauri::WebviewWindow,
    manager: State<'_, plugin_intake::PluginIntakeManager>,
    picker: State<'_, DirectoryPickerManager>,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    message: tauri::ipc::Request<'_>,
) -> Result<plugin_intake::PluginIntakeOutcome, ()> {
    use plugin_intake::PluginIntakeOutcome;
    let tauri::ipc::InvokeBody::Json(payload) = message.body() else {
        return Ok(PluginIntakeOutcome::Failed);
    };
    let Some(request) = plugin_intake::decode_request(payload) else {
        return Ok(PluginIntakeOutcome::Failed);
    };
    let Some(owner) = directory_window_handle(&window) else {
        return Ok(PluginIntakeOutcome::Unavailable);
    };
    let Ok(ticket) = lock.begin_protected_action() else {
        return Ok(PluginIntakeOutcome::Cancelled);
    };
    #[cfg(windows)]
    {
        let (manager, picker, supervisor, security) = (
            manager.inner().clone(),
            picker.inner().clone(),
            supervisor.inner().clone(),
            lock.inner().clone(),
        );
        let prepared = tauri::async_runtime::spawn_blocking(move || {
            plugin_intake::prepare(
                manager, picker, supervisor, security, ticket, owner, request,
            )
        })
        .await;
        match prepared {
            Ok(Ok(mut prepared)) => {
                let same_window = directory_window_handle(&window) == Some(owner);
                let security = lock.inner().clone();
                Ok(tauri::async_runtime::spawn_blocking(move || {
                    if same_window
                        && security
                            .commit_protected_action(ticket, || Ok(prepared.accept()))
                            .unwrap_or(false)
                    {
                        prepared.into_outcome()
                    } else {
                        PluginIntakeOutcome::Cancelled
                    }
                })
                .await
                .unwrap_or(PluginIntakeOutcome::Failed))
            }
            Ok(Err(error)) => Ok(plugin_intake::failure(error)),
            Err(_) => Ok(PluginIntakeOutcome::Failed),
        }
    }
    #[cfg(not(windows))]
    {
        let _ = (request, manager, picker, supervisor, ticket);
        Ok(PluginIntakeOutcome::Unavailable)
    }
}

#[tauri::command]
fn cancel_connector_package_selection(
    window: tauri::WebviewWindow,
    manager: State<'_, plugin_intake::PluginIntakeManager>,
    picker: State<'_, DirectoryPickerManager>,
    operation_id: String,
) -> Result<(), ()> {
    if directory_window_handle(&window).is_none() {
        return Err(());
    }
    manager.cancel(&operation_id, &picker);
    Ok(())
}

#[tauri::command]
async fn connector_plugin_action(
    window: tauri::WebviewWindow,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    message: tauri::ipc::Request<'_>,
) -> Result<plugin_intake::PluginActionOutcome, ()> {
    use plugin_intake::PluginActionOutcome;
    let tauri::ipc::InvokeBody::Json(payload) = message.body() else {
        return Ok(PluginActionOutcome::Failed);
    };
    let Some(request) = plugin_intake::decode_action(payload) else {
        return Ok(PluginActionOutcome::Failed);
    };
    let Some(owner) = directory_window_handle(&window) else {
        return Ok(PluginActionOutcome::Unavailable);
    };
    let Ok(ticket) = lock.begin_protected_action() else {
        return Ok(PluginActionOutcome::Cancelled);
    };
    let (supervisor, security) = (supervisor.inner().clone(), lock.inner().clone());
    let outcome = tauri::async_runtime::spawn_blocking(move || {
        plugin_intake::perform_action(supervisor, security, ticket, owner, request)
    })
    .await
    .unwrap_or(PluginActionOutcome::Failed);
    if directory_window_handle(&window) != Some(owner) {
        // The Core mutation may have committed before this window ended.
        Ok(PluginActionOutcome::Failed)
    } else {
        Ok(outcome)
    }
}

#[tauri::command]
async fn trust_connector_publisher(
    window: tauri::WebviewWindow,
    manager: State<'_, plugin_intake::PluginIntakeManager>,
    picker: State<'_, DirectoryPickerManager>,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    message: tauri::ipc::Request<'_>,
) -> Result<plugin_intake::PluginActionOutcome, ()> {
    use plugin_intake::PluginActionOutcome;
    let tauri::ipc::InvokeBody::Json(payload) = message.body() else {
        return Ok(PluginActionOutcome::Failed);
    };
    let Some(request) = plugin_intake::decode_trust_request(payload) else {
        return Ok(PluginActionOutcome::Failed);
    };
    let Some(owner) = directory_window_handle(&window) else {
        return Ok(PluginActionOutcome::Unavailable);
    };
    let Ok(ticket) = lock.begin_protected_action() else {
        return Ok(PluginActionOutcome::Cancelled);
    };
    #[cfg(windows)]
    {
        let (manager, picker, supervisor, security) = (
            manager.inner().clone(),
            picker.inner().clone(),
            supervisor.inner().clone(),
            lock.inner().clone(),
        );
        let result = tauri::async_runtime::spawn_blocking(move || {
            plugin_intake::trust_publisher(
                manager, picker, supervisor, security, ticket, owner, request,
            )
        })
        .await
        .unwrap_or(PluginActionOutcome::Failed);
        if directory_window_handle(&window) == Some(owner) {
            Ok(result)
        } else {
            // The mutation may have committed before the window changed.
            Ok(PluginActionOutcome::Failed)
        }
    }
    #[cfg(not(windows))]
    {
        let _ = (request, manager, picker, supervisor, ticket);
        Ok(PluginActionOutcome::Unavailable)
    }
}

#[tauri::command]
fn cancel_import_file(
    window: tauri::WebviewWindow,
    manager: State<'_, import_runtime::ImportManager>,
    picker: State<'_, DirectoryPickerManager>,
    operation_id: String,
) -> Result<(), ()> {
    if directory_window_handle(&window).is_none() {
        return Err(());
    }
    manager.cancel(&operation_id, &picker);
    Ok(())
}

#[tauri::command]
async fn save_import_report(
    window: tauri::WebviewWindow,
    manager: State<'_, import_runtime::ImportManager>,
    picker: State<'_, DirectoryPickerManager>,
    supervisor: State<'_, RuntimeSupervisor>,
    lock: State<'_, ApplicationLockManager>,
    message: tauri::ipc::Request<'_>,
) -> Result<import_runtime::ReportOutcome, ()> {
    use import_runtime::ReportOutcome;
    let tauri::ipc::InvokeBody::Json(payload) = message.body() else {
        return Ok(ReportOutcome::Failed);
    };
    let Some(request) = import_runtime::decode_report_request(payload) else {
        return Ok(ReportOutcome::Failed);
    };
    let Some(owner) = directory_window_handle(&window) else {
        return Ok(ReportOutcome::Unavailable);
    };
    #[cfg(all(feature = "integration-harness", windows))]
    if window
        .try_state::<directory_integration_harness::Fixture>()
        .is_some_and(|fixture| {
            fixture.revalidate().is_err()
                || !directory_picker::fixture_contains(&fixture.projects, &request.root)
        })
    {
        return Ok(ReportOutcome::Unavailable);
    }
    let Ok(ticket) = lock.begin_protected_action() else {
        return Ok(ReportOutcome::Cancelled);
    };
    #[cfg(windows)]
    {
        let (manager, picker, supervisor, lock) = (
            manager.inner().clone(),
            picker.inner().clone(),
            supervisor.inner().clone(),
            lock.inner().clone(),
        );
        Ok(tauri::async_runtime::spawn_blocking(move || {
            import_runtime::save_report(manager, picker, supervisor, lock, ticket, owner, request)
        })
        .await
        .unwrap_or(ReportOutcome::Failed))
    }
    #[cfg(not(windows))]
    {
        let _ = (manager, picker, supervisor, request, owner, ticket);
        Ok(ReportOutcome::Unavailable)
    }
}

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
    #[cfg(all(feature = "integration-harness", windows))]
    if let Some(fixture) = window.try_state::<directory_integration_harness::Fixture>()
        && fixture.document_drop_mode()
        && request.purpose == directory_picker::DirectoryPurpose::OpenProject
    {
        let result = fixture
            .document_drop_project()
            .and_then(|path| {
                (lock.finish_protected_action(ticket).is_ok()
                    && directory_window_handle(&window) == Some(owner))
                .then_some(DirectoryOutcome::Selected { path })
                .ok_or("probe-attachment-project-selection-denied")
            })
            .unwrap_or(DirectoryOutcome::Unavailable);
        directory_integration_harness::observe_result(&result);
        return Ok(result);
    }
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
fn application_lock_status(
    _app: AppHandle,
    lock: State<'_, ApplicationLockManager>,
) -> ApplicationLockSnapshot {
    #[cfg(all(feature = "integration-harness", windows))]
    let _trace = _app
        .try_state::<directory_integration_harness::Fixture>()
        .and_then(|fixture| fixture.status_trace("body"));
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
            let window_config = app
                .config()
                .app
                .windows
                .iter()
                .find(|window| window.label == "main")
                .cloned()
                .ok_or_else(|| std::io::Error::other("RO-MAIN-WINDOW-CONFIG-UNAVAILABLE"))?;
            #[cfg(windows)]
            let main = tauri::WebviewWindowBuilder::from_config(app, &window_config)?
                .visible(false)
                .drag_and_drop(false)
                .disable_drag_drop_handler()
                .build()?;
            #[cfg(not(windows))]
            let main = tauri::WebviewWindowBuilder::from_config(app, &window_config)?
                .visible(false)
                .build()?;
            #[cfg(windows)]
            main_menu::install(&main).map_err(std::io::Error::other)?;
            let application_data = app
                .path()
                .app_local_data_dir()
                .map_err(|_| std::io::Error::other("application data unavailable"))?;
            setup_runtime(
                app,
                runtime_config(app),
                &application_data,
                DirectoryPickerManager::default(),
            )?;
            #[cfg(windows)]
            {
                let manager = app
                    .state::<document_attachment::DocumentAttachmentManager>()
                    .inner()
                    .clone();
                document_drop::install(&main, &manager).map_err(std::io::Error::other)?;
                manager.set_installed(true);
                main.show()?;
            }
            #[cfg(not(windows))]
            main.show()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Research Observatory desktop runtime failed");
}

fn application_builder() -> tauri::Builder<tauri::Wry> {
    #[cfg(windows)]
    let handler: fn(tauri::ipc::Invoke<tauri::Wry>) -> bool = tauri::generate_handler![
        configure_scholarly_source,
        open_scholarly_source_terms,
        cancel_scholarly_source_configuration,
        import_selected_file,
        select_connector_package,
        cancel_connector_package_selection,
        connector_plugin_action,
        trust_connector_publisher,
        cancel_import_file,
        save_import_report,
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
        application_sign_in_transition_commit,
        document_attachment::document_attachment_capabilities,
        document_attachment::document_attachment_begin,
        document_attachment::document_attachment_cancel,
        document_attachment::document_attachment_commit,
        document_attachment::document_attachment_status,
        document_attachment::document_acquisition_copies,
        document_attachment::document_acquisition_review,
        document_attachment::document_acquisition_clear_review,
        document_attachment::document_acquisition_download,
        document_attachment::document_acquisition_access_need,
        document_attachment::document_acquisition_recover,
        document_reader::document_reader_revisions,
        document_reader::document_reader_outline,
        document_reader::document_reader_anchor_create,
        document_reader::document_reader_anchor_read,
        document_reader::document_reader_anchor_list,
        document_reader::document_reader_anchor_resolve,
        document_reader::document_reader_citation_links
    ];
    #[cfg(not(windows))]
    let handler: fn(tauri::ipc::Invoke<tauri::Wry>) -> bool = tauri::generate_handler![
        configure_scholarly_source,
        open_scholarly_source_terms,
        cancel_scholarly_source_configuration,
        import_selected_file,
        select_connector_package,
        cancel_connector_package_selection,
        connector_plugin_action,
        trust_connector_publisher,
        cancel_import_file,
        save_import_report,
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
            if invoke
                .message
                .webview()
                .try_state::<ApplicationLockManager>()
                .is_some_and(|lock| lock.is_terminal())
            {
                invoke.resolver.reject("RO-APPLICATION-CLOSING");
                return true;
            }
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
            #[cfg(all(feature = "integration-harness", windows))]
            let _trace = (invoke.message.command() == "application_lock_status")
                .then(|| {
                    invoke
                        .message
                        .webview()
                        .try_state::<directory_integration_harness::Fixture>()
                        .and_then(|fixture| fixture.status_trace("router"))
                })
                .flatten();
            handler(invoke)
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event
                && window.label() == "main"
            {
                #[cfg(windows)]
                {
                    window
                        .state::<document_attachment::DocumentAttachmentManager>()
                        .set_installed(false);
                    document_drop::uninstall();
                }
                let picker = window.state::<DirectoryPickerManager>().inner().clone();
                api.prevent_close();
                if matches!(picker.begin_close(), CloseDisposition::AlreadyClosing) {
                    return;
                }
                let imports = window
                    .state::<import_runtime::ImportManager>()
                    .inner()
                    .clone();
                imports.begin_close();
                let security = window
                    .state::<ApplicationLockManager>()
                    .begin_terminal_exit();
                let supervisor = window.state::<RuntimeSupervisor>().inner().clone();
                supervisor.begin_native_exit();
                let closing_window = window.clone();
                tauri::async_runtime::spawn_blocking(move || {
                    supervisor.stop_for_native_exit(security);
                    picker.wait_for_cleanup();
                    imports.wait_for_cleanup();
                    // Keep UI dispatch alive until native work has drained and
                    // the session is sealed; never join its STA on the UI thread.
                    let _ = closing_window.destroy();
                });
            }
        })
}

fn setup_runtime(
    app: &mut App,
    config: Result<SupervisorConfig, &'static str>,
    application_data: &std::path::Path,
    picker: DirectoryPickerManager,
) -> Result<(), Box<dyn std::error::Error>> {
    let lock = ApplicationLockManager::acquire(application_data).map_err(std::io::Error::other)?;
    let session = std::sync::Arc::new(workflow_session::WorkflowSessionAuthority::new(
        application_data,
    ));
    lock.bind_security_latch(session.security_latch());
    let supervisor = RuntimeSupervisor::with_session(config, session);
    let support = SupportBundleManager::default();
    app.manage(supervisor.clone());
    app.manage(lock.clone());
    app.manage(support.clone());
    app.manage(picker.clone());
    app.manage(import_runtime::ImportManager::default());
    app.manage(plugin_intake::PluginIntakeManager::default());
    app.manage(connector_configuration::ConfigurationManager::default());
    #[cfg(windows)]
    app.manage(document_attachment::DocumentAttachmentManager::default());
    if lock.is_unlocked() {
        let startup = supervisor.clone();
        tauri::async_runtime::spawn_blocking(move || startup.start());
    }
    start_lock_monitor(app.handle().clone(), lock, supervisor, support, picker);
    Ok(())
}

#[cfg(windows)]
mod main_menu {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        ISMEX_REPLIED, ISMEX_SEND, SC_KEYMENU, WM_APP, WM_NCDESTROY, WM_SYSCOMMAND,
    };

    // This scalar alias only represents the existing standard Alt+Space menu
    // action. It is not authenticated input or a new protected IPC command.
    // Avoid directory-picker WM_APP + 91/92/93 and pinned Tao/Wry message IDs.
    pub(super) const REPLAY_MESSAGE: u32 = WM_APP + 94;
    type Message = (u32, usize, isize);

    pub(super) fn valid_payload(wparam: usize, lparam: isize) -> bool {
        wparam & !0xf == SC_KEYMENU as usize && lparam == 32
    }

    fn dispatch(
        original: Message,
        send_state: u32,
        remove: impl FnOnce(),
        post: impl FnOnce(Message) -> bool,
        forward: impl FnOnce(Message) -> isize,
    ) -> isize {
        let (message, wparam, lparam) = original;
        if message == WM_NCDESTROY {
            remove();
            return forward(original);
        }
        if message == REPLAY_MESSAGE {
            return if valid_payload(wparam, lparam) {
                // Direct forwarding, never re-admission under nested send flags.
                forward((WM_SYSCOMMAND, wparam, lparam))
            } else {
                0
            };
        }
        if message == WM_SYSCOMMAND
            && valid_payload(wparam, lparam)
            && send_state & (ISMEX_REPLIED | ISMEX_SEND) == ISMEX_SEND
            && post((REPLAY_MESSAGE, wparam, lparam))
        {
            return 0;
        }
        // Post failure preserves the native command; no retry, coalescing,
        // application queue, or busy fallback for overlapping successful posts.
        forward(original)
    }

    pub(super) fn owner_matches(
        thread: u32,
        process: u32,
        current_thread: u32,
        current_process: u32,
    ) -> bool {
        thread != 0 && process != 0 && thread == current_thread && process == current_process
    }

    unsafe extern "system" fn menu_proc(
        hwnd: windows_sys::Win32::Foundation::HWND,
        message: u32,
        wparam: usize,
        lparam: isize,
        subclass_id: usize,
        data: usize,
    ) -> isize {
        use windows_sys::Win32::UI::{
            Shell::{DefSubclassProc, RemoveWindowSubclass},
            WindowsAndMessaging::{InSendMessageEx, PostMessageW},
        };
        if data != 0 || subclass_id != menu_proc as *const () as usize {
            return unsafe { DefSubclassProc(hwnd, message, wparam, lparam) };
        }
        // No allocated registration/payload state or retained native pointers.
        dispatch(
            (message, wparam, lparam),
            unsafe { InSendMessageEx(std::ptr::null()) },
            || {
                let _ = unsafe { RemoveWindowSubclass(hwnd, Some(menu_proc), subclass_id) };
            },
            |(message, wparam, lparam)| unsafe { PostMessageW(hwnd, message, wparam, lparam) } != 0,
            |(message, wparam, lparam)| unsafe { DefSubclassProc(hwnd, message, wparam, lparam) },
        )
    }

    pub(super) fn install(window: &tauri::WebviewWindow) -> Result<(), &'static str> {
        use windows_sys::Win32::{
            System::Threading::{GetCurrentProcessId, GetCurrentThreadId},
            UI::{
                Shell::{GetWindowSubclass, SetWindowSubclass},
                WindowsAndMessaging::GetWindowThreadProcessId,
            },
        };
        if window.label() != "main" {
            return Err("RO-MENU-WINDOW-INVALID");
        }
        let hwnd = window.hwnd().map_err(|_| "RO-MENU-HWND-UNAVAILABLE")?.0;
        let mut process = 0;
        let thread = unsafe { GetWindowThreadProcessId(hwnd, &mut process) };
        if !owner_matches(thread, process, unsafe { GetCurrentThreadId() }, unsafe {
            GetCurrentProcessId()
        }) {
            return Err("RO-MENU-OWNER-INVALID");
        }
        let id = menu_proc as *const () as usize;
        let mut previous = 0;
        if unsafe { GetWindowSubclass(hwnd, Some(menu_proc), id, &mut previous) } != 0 {
            return Err("RO-MENU-ALREADY-INSTALLED");
        }
        if unsafe { SetWindowSubclass(hwnd, Some(menu_proc), id, 0) } == 0 {
            return Err("RO-MENU-INSTALL-FAILED");
        }
        Ok(())
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use std::cell::RefCell;
        use windows_sys::Win32::UI::WindowsAndMessaging::*;

        fn original() -> Message {
            (WM_SYSCOMMAND, SC_KEYMENU as usize | 7, 32)
        }

        fn route(
            command: Message,
            flags: u32,
            post: impl FnOnce(Message) -> bool,
            forward: impl FnOnce(Message) -> isize,
        ) -> isize {
            dispatch(
                command,
                flags,
                || panic!("unexpected removal"),
                post,
                forward,
            )
        }

        #[test]
        fn main_menu_shared_payload_checks_every_bit_and_preserves_original_scalars() {
            for low_flags in 0..16 {
                assert!(valid_payload(SC_KEYMENU as usize | low_flags, 32));
            }
            for wparam in [
                SC_CLOSE as usize,
                SC_MOVE as usize,
                SC_SIZE as usize,
                SC_KEYMENU as usize | 0x10000,
                usize::MAX,
            ] {
                assert!(!valid_payload(wparam, 32));
            }
            for lparam in [0, 31, 33, -1, isize::MAX] {
                assert!(!valid_payload(SC_KEYMENU as usize, lparam));
            }
            let mut posted = Vec::new();
            assert_eq!(
                route(
                    original(),
                    ISMEX_SEND,
                    |message| {
                        posted.push(message);
                        true
                    },
                    |_| panic!("deferred original")
                ),
                0
            );
            assert_eq!(posted, [(REPLAY_MESSAGE, original().1, original().2)]);
        }

        #[test]
        fn main_menu_shared_nontarget_and_nonblocked_messages_forward_unchanged_once() {
            for command in [
                (WM_SYSCOMMAND, SC_CLOSE as usize, 32),
                (WM_SYSCOMMAND, SC_MOVE as usize, 32),
                (WM_SYSCOMMAND, SC_SIZE as usize, 32),
                (WM_SYSCOMMAND, SC_KEYMENU as usize | 0x10000, 32),
                (WM_SYSCOMMAND, SC_KEYMENU as usize, 65),
                (WM_SYSKEYDOWN, 32, 0),
                (WM_KEYDOWN, 27, 0),
            ] {
                let mut count = 0;
                assert_eq!(
                    route(
                        command,
                        ISMEX_SEND,
                        |_| panic!("nontarget post"),
                        |actual| {
                            assert_eq!(actual, command);
                            count += 1;
                            -73
                        }
                    ),
                    -73
                );
                assert_eq!(count, 1);
            }
            for flags in [
                0,
                ISMEX_NOTIFY,
                ISMEX_CALLBACK,
                ISMEX_REPLIED,
                ISMEX_SEND | ISMEX_REPLIED,
            ] {
                assert_eq!(
                    route(
                        original(),
                        flags,
                        |_| panic!("no blocked sender"),
                        |actual| {
                            assert_eq!(actual, original());
                            17
                        }
                    ),
                    17
                );
            }
        }

        #[test]
        fn main_menu_shared_private_alias_has_no_provenance_or_arbitrary_command_authority() {
            // A valid unsolicited alias requests only the same public menu
            // action. This deliberately does not claim C's retired token proof.
            for flags in [0, ISMEX_SEND, ISMEX_SEND | ISMEX_REPLIED] {
                let mut forwarded = Vec::new();
                assert_eq!(
                    route(
                        (REPLAY_MESSAGE, original().1, 32),
                        flags,
                        |_| panic!("replay cannot requeue"),
                        |actual| {
                            forwarded.push(actual);
                            -81
                        }
                    ),
                    -81
                );
                assert_eq!(forwarded, [original()]);
            }
            for command in [
                (REPLAY_MESSAGE, SC_CLOSE as usize, 32),
                (REPLAY_MESSAGE, SC_KEYMENU as usize | 0x10000, 32),
                (REPLAY_MESSAGE, SC_KEYMENU as usize, 0),
                (REPLAY_MESSAGE, 1, 0),
            ] {
                assert_eq!(
                    route(
                        command,
                        ISMEX_SEND,
                        |_| panic!("invalid post"),
                        |_| panic!("invalid alias action")
                    ),
                    0
                );
            }
        }

        #[test]
        fn main_menu_shared_overlapping_and_nested_inputs_each_forward_once_without_busy_state() {
            let originals = [original(), (WM_SYSCOMMAND, SC_KEYMENU as usize | 10, 32)];
            let mut posted = Vec::new();
            for command in originals {
                assert_eq!(
                    route(
                        command,
                        ISMEX_SEND,
                        |actual| {
                            posted.push(actual);
                            true
                        },
                        |_| panic!("no busy fallback")
                    ),
                    0
                );
            }
            assert_eq!(posted.len(), 2);
            let forwarded = RefCell::new(Vec::new());
            assert_eq!(
                route(
                    posted[0],
                    ISMEX_SEND,
                    |_| panic!("nested replay requeued"),
                    |actual| {
                        forwarded.borrow_mut().push(actual);
                        assert_eq!(
                            route(
                                posted[1],
                                ISMEX_SEND,
                                |_| panic!("nested replay requeued"),
                                |nested| {
                                    forwarded.borrow_mut().push(nested);
                                    18
                                }
                            ),
                            18
                        );
                        19
                    }
                ),
                19
            );
            assert_eq!(*forwarded.borrow(), originals);
        }

        #[test]
        fn main_menu_shared_post_failure_preserves_original_result_without_retry() {
            let mut posts = 0;
            let mut forwards = 0;
            assert_eq!(
                route(
                    original(),
                    ISMEX_SEND,
                    |posted| {
                        assert_eq!(posted, (REPLAY_MESSAGE, original().1, 32));
                        posts += 1;
                        false
                    },
                    |actual| {
                        assert_eq!(actual, original());
                        forwards += 1;
                        -9
                    }
                ),
                -9
            );
            assert_eq!((posts, forwards), (1, 1));
        }

        #[test]
        fn main_menu_shared_teardown_removes_before_forwarding_and_ownership_is_exact() {
            let order = RefCell::new(Vec::new());
            let command = (WM_NCDESTROY, 123, 456);
            assert_eq!(
                dispatch(
                    command,
                    ISMEX_SEND,
                    || order.borrow_mut().push(0),
                    |_| panic!("destroy post"),
                    |actual| {
                        assert_eq!(actual, command);
                        order.borrow_mut().push(1);
                        31
                    }
                ),
                31
            );
            assert_eq!(*order.borrow(), [0, 1]);
            assert!(owner_matches(11, 22, 11, 22));
            assert!(!owner_matches(12, 22, 11, 22));
            assert!(!owner_matches(11, 23, 11, 22));
            assert!(!owner_matches(0, 22, 0, 22));
            assert!(!owner_matches(11, 0, 11, 0));
            assert!((WM_APP..0xc000).contains(&REPLAY_MESSAGE));
            for used in [WM_APP + 91, WM_APP + 92, WM_APP + 93] {
                assert_ne!(REPLAY_MESSAGE, used);
            }
        }
    }
}

/// Disposable composition only: no command, environment switch, or production
/// startup path can activate this entry point.
#[cfg(all(feature = "integration-harness", windows))]
pub mod directory_integration_harness {
    use super::*;
    use crate::application_sign_in_policy::{POLICY_FILE, SignInPolicy};
    use serde_json::{Value, json};
    use std::ffi::{OsStr, OsString};
    use std::io::{Read, Write};
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
        Lifecycle,
        LifecycleResume,
        DocumentDrop,
        DocumentDropFive,
        DocumentDropResume,
    }

    #[derive(Clone, serde::Deserialize, serde::Serialize)]
    #[serde(rename_all = "camelCase", deny_unknown_fields)]
    struct DocumentDropSeed {
        schema_version: String,
        project_id: String,
        work_id: String,
        work_revision_id: String,
        version_id: String,
        version_revision_id: String,
        source_assertion_revision_id: String,
        synthetic_source_sha256: String,
        protected_database: bool,
    }

    const DOCUMENT_DROP_SEED_RECEIPT: &str = "t01-document-seed.json";
    const DOCUMENT_DROP_COMMIT_RECEIPT: &str = "t01-document-commit.json";

    #[derive(Clone, serde::Deserialize, serde::Serialize, Eq, PartialEq)]
    #[serde(rename_all = "camelCase", deny_unknown_fields)]
    struct DocumentDropSelection {
        project_id: String,
        work_id: String,
        work_revision_id: String,
        version_id: String,
        version_revision_id: String,
        source_assertion_revision_id: String,
    }

    impl From<&DocumentDropSeed> for DocumentDropSelection {
        fn from(seed: &DocumentDropSeed) -> Self {
            Self {
                project_id: seed.project_id.clone(),
                work_id: seed.work_id.clone(),
                work_revision_id: seed.work_revision_id.clone(),
                version_id: seed.version_id.clone(),
                version_revision_id: seed.version_revision_id.clone(),
                source_assertion_revision_id: seed.source_assertion_revision_id.clone(),
            }
        }
    }

    #[derive(Clone, serde::Deserialize, serde::Serialize)]
    #[serde(rename_all = "camelCase", deny_unknown_fields)]
    struct DocumentDropCommitReceipt {
        schema_version: String,
        selection: DocumentDropSelection,
        operation_id: String,
        command_id: String,
        candidate_id: String,
        attachment_id: String,
        document_revision_id: String,
    }

    impl DocumentDropCommitReceipt {
        fn valid_for(&self, seed: &DocumentDropSeed) -> bool {
            self.schema_version == "1.0"
                && self.selection == DocumentDropSelection::from(seed)
                && [
                    &self.operation_id,
                    &self.command_id,
                    &self.candidate_id,
                    &self.attachment_id,
                    &self.document_revision_id,
                ]
                .into_iter()
                .all(|id| crate::supervisor::canonical_uuid_v7(id))
        }
    }

    fn validate_document_drop_seed(
        fixture: &Fixture,
        seed: &DocumentDropSeed,
    ) -> Result<(), &'static str> {
        if seed.schema_version != "1.0"
            || !seed.protected_database
            || !super::supervisor::canonical_project_id(&seed.project_id)
            || [
                &seed.work_id,
                &seed.work_revision_id,
                &seed.version_id,
                &seed.version_revision_id,
                &seed.source_assertion_revision_id,
            ]
            .into_iter()
            .any(|id| !super::supervisor::canonical_uuid_v7(id))
            || seed.synthetic_source_sha256.len() != 64
            || !seed
                .synthetic_source_sha256
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit())
            || fixture.document_drop_project().is_err()
        {
            return Err("probe-attachment-seed-invalid");
        }
        Ok(())
    }

    fn write_document_receipt<T: serde::Serialize>(
        fixture: &Fixture,
        name: &str,
        receipt: &T,
    ) -> Result<(), &'static str> {
        fixture.revalidate()?;
        let bytes = serde_json::to_vec(receipt).map_err(|_| "probe-attachment-receipt-invalid")?;
        if bytes.len() > 4096 {
            return Err("probe-attachment-receipt-invalid");
        }
        let mut file = std::fs::File::create_new(fixture.root.join(name))
            .map_err(|_| "probe-attachment-receipt-create-denied")?;
        file.write_all(&bytes)
            .and_then(|_| file.sync_all())
            .map_err(|_| "probe-attachment-receipt-create-denied")?;
        Ok(())
    }

    fn read_document_receipt<T: serde::de::DeserializeOwned>(
        fixture: &Fixture,
        name: &str,
    ) -> Result<T, &'static str> {
        fixture.revalidate()?;
        let file = std::fs::OpenOptions::new()
            .read(true)
            .share_mode(0x1)
            .custom_flags(0x00200000)
            .open(fixture.root.join(name))
            .map_err(|_| "probe-attachment-receipt-unavailable")?;
        let mut information = BY_HANDLE_FILE_INFORMATION::default();
        if unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut information) } == 0
            || information.dwFileAttributes & (0x10 | 0x400) != 0
            || information.nNumberOfLinks != 1
            || information.nFileSizeHigh != 0
            || information.nFileSizeLow > 4096
        {
            return Err("probe-attachment-receipt-invalid");
        }
        let mut bytes = Vec::new();
        (&file)
            .take(4097)
            .read_to_end(&mut bytes)
            .map_err(|_| "probe-attachment-receipt-unavailable")?;
        serde_json::from_slice(&bytes).map_err(|_| "probe-attachment-receipt-invalid")
    }

    fn seed_document_drop(fixture: &Fixture) -> Result<DocumentDropSeed, &'static str> {
        if !fixture.document_drop {
            return Err("probe-attachment-mode-unavailable");
        }
        fixture.revalidate()?;
        let repo = repository()?;
        let result = std::process::Command::new(repo.join(".venv/Scripts/python.exe"))
            .arg("-I")
            .arg(repo.join("tests/desktop/tools/seed_document_drop_fixture.py"))
            .arg("--fixture-root")
            .arg(&fixture.root)
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .creation_flags(0x08000000)
            .output()
            .map_err(|_| "probe-attachment-seed-unavailable")?;
        if !result.status.success() || result.stdout.len() > 4096 {
            return Err("probe-attachment-seed-failed");
        }
        let seed: DocumentDropSeed =
            serde_json::from_slice(&result.stdout).map_err(|_| "probe-attachment-seed-invalid")?;
        validate_document_drop_seed(fixture, &seed)?;
        Ok(seed)
    }

    impl Mode {
        pub fn parse(value: &str) -> Option<Self> {
            match value {
                "selection" => Some(Self::Selection),
                "manual-lock" => Some(Self::ManualLock),
                "main-close" => Some(Self::MainClose),
                "lifecycle" => Some(Self::Lifecycle),
                "lifecycle-resume" => Some(Self::LifecycleResume),
                "document-drop" => Some(Self::DocumentDrop),
                "document-drop-five" => Some(Self::DocumentDropFive),
                "document-drop-resume" => Some(Self::DocumentDropResume),
                _ => None,
            }
        }
        fn name(self) -> &'static str {
            match self {
                Self::Selection => "selection",
                Self::ManualLock => "manual-lock",
                Self::MainClose => "main-close",
                Self::Lifecycle => "lifecycle",
                Self::LifecycleResume => "lifecycle-resume",
                Self::DocumentDrop => "document-drop",
                Self::DocumentDropFive => "document-drop-five",
                Self::DocumentDropResume => "document-drop-resume",
            }
        }

        fn is_lifecycle(self) -> bool {
            matches!(self, Self::Lifecycle | Self::LifecycleResume)
        }

        fn is_document_attachment(self) -> bool {
            matches!(
                self,
                Self::DocumentDrop | Self::DocumentDropFive | Self::DocumentDropResume
            )
        }
    }

    const LIFECYCLE_RECEIPT: &str = "t04-lifecycle-fixture.json";

    // Tauri installs its non-writable invoke function before user initialization
    // scripts. Observe only its exact Windows custom-protocol fetch instead.
    // This cannot observe postMessage fallback, decoded invoke settlement, or
    // establish a shared clock/request identity with the native trace below.
    const LOCK_STATUS_DIAGNOSTIC_SCRIPT: &str = r#"
(() => {
  const statusUrl = window.__TAURI_INTERNALS__.convertFileSrc('application_lock_status', 'ipc');
  const originalFetch = window.fetch;
  const rows = [];
  let sequence = 0, issued = 0, fulfilled = 0, rejected = 0, omitted = 0, locked = -1;
  let output;
  function render() {
    if (output) output.textContent = JSON.stringify({
      issued, fulfilled, rejected, omitted, locked, rows,
      // Rows: event ordinal, renderer monotonic ms, fetch ordinal (or lock boolean), phase.
      // Phases: 0 fetch start, 1 fetch fulfilled, 2 fetch rejected, 3 locked DOM marker.
    });
  }
  function record(id, phase) {
    try {
      if (phase === 1) fulfilled++;
      if (phase === 2) rejected++;
      rows.push([++sequence, performance.now(), id, phase]);
      if (rows.length > 96) rows.shift();
      render();
    } catch (_) { /* Diagnostic failure must not affect the application. */ }
  }
  window.fetch = function (...args) {
    let id = 0;
    if (args[0] === statusUrl) {
      if (issued < 512) { id = ++issued; record(id, 0); }
      else {
        omitted = Math.min(omitted + 1, Number.MAX_SAFE_INTEGER);
        try { render(); } catch (_) { /* Observation remains optional. */ }
      }
    }
    let pending;
    try { pending = Reflect.apply(originalFetch, this, args); }
    catch (error) { if (id) record(id, 2); throw error; }
    if (id) {
      try { void pending.then(() => record(id, 1), () => record(id, 2)); }
      catch (_) { /* Preserve the original return even if observation fails. */ }
    }
    // Neither the request nor the response is read or replaced.
    return pending;
  };
  function mount() {
    try {
      const section = document.createElement('details');
      section.setAttribute('data-fixture-lock-status-diagnostic', 'true');
      const summary = document.createElement('summary');
      summary.textContent = 'Synthetic fixture diagnostics (fetch only; not invoke success)';
      output = document.createElement('pre');
      section.append(summary, output);
      document.body.append(section);
      function observeLock() {
        const current = Number(document.querySelector('[data-application-locked="true"]') !== null);
        if (current !== locked) { locked = current; record(current, 3); }
      }
      const observer = new MutationObserver(observeLock);
      observer.observe(document.body, {
        subtree: true, childList: true, attributes: true,
        attributeFilter: ['data-application-locked'],
      });
      window.addEventListener('pagehide', () => observer.disconnect(), { once: true });
      observeLock();
    } catch (_) { /* No product UI, state, or recovery depends on this view. */ }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else { mount(); }
})();
"#;

    fn document_drop_ui_script(seed: &DocumentDropSeed, require_five: bool) -> String {
        let five_ready = !require_five;
        let project = serde_json::to_string(&seed.project_id).expect("fixture project ID");
        let work = serde_json::to_string(&seed.work_id).expect("fixture Work ID");
        let source =
            serde_json::to_string(&seed.source_assertion_revision_id).expect("fixture source ID");
        format!(
            r#"
(() => {{
  const projectId = {project}, workId = {work}, sourceId = {source};
  const data = {{ fiveInstallReady: {five_ready}, phase: 0, ready: false, error: null, sourceId, html5: {{ dragEnter: 0, dragOver: 0, drop: 0,
    exposedFiles: 0, exposedFileItems: 0 }} }};
  Object.defineProperty(window, '__RO_DROP_PROBE', {{ value: data, configurable: false }});
  for (const [name, field] of [['dragenter', 'dragEnter'], ['dragover', 'dragOver'], ['drop', 'drop']]) {{
    window.addEventListener(name, (event) => {{
      data.html5[field]++;
      try {{ data.html5.exposedFiles += event.dataTransfer?.files?.length ?? 0;
        data.html5.exposedFileItems += Array.from(event.dataTransfer?.items ?? []).filter((item) => item.kind === 'file').length;
      }} catch (_) {{ data.error = 'drag-observation-unavailable'; }}
    }}, true);
  }}
  const button = (label) => Array.from(document.querySelectorAll('button')).find((item) =>
    item.textContent?.trim() === label && !item.disabled);
  const begin = performance.now();
  const timer = setInterval(() => {{
    try {{
      if (data.ready || data.error) {{ clearInterval(timer); return; }}
      if (!data.fiveInstallReady) return;
      if (performance.now() - begin > 90000) {{ data.error = 'ui-sequence-timeout'; clearInterval(timer); return; }}
      if (data.phase === 0) {{
        const tools = document.querySelector('details[data-all-tools]'); if (tools) tools.open = true;
        const projects = document.querySelector('button[aria-label="Local projects"]');
        if (projects && !projects.disabled) {{ projects.click(); data.phase = 1; }}
      }} else if (data.phase === 1) {{
        const choose = document.querySelector('#project-root-choose');
        if (choose && !choose.disabled) {{ choose.click(); data.phase = 2; }}
      }} else if (data.phase === 2) {{
        const form = document.querySelector('#project-root')?.closest('form');
        const open = form?.querySelector('button[type="submit"]');
        if (open && !open.disabled) {{ open.click(); data.phase = 3; }}
      }} else if (data.phase === 3) {{
        if (document.querySelector(`[data-current-project="${{projectId}}"]`)) {{
          const imports = document.querySelector('button[aria-label="Ingestion & Reconciliation"]');
          if (imports && !imports.disabled) {{ imports.click(); data.phase = 4; }}
        }}
      }} else if (data.phase === 4) {{
        const versions = button('Open Work versions');
        if (versions) {{ versions.click(); data.phase = 5; }}
      }} else if (data.phase === 5) {{
        const label = Array.from(document.querySelectorAll('label')).find((item) =>
          item.textContent?.includes(`Select Work ${{workId}}`));
        const box = label?.querySelector('input[type="checkbox"]');
        if (box && !box.checked) box.click();
        const review = button('Review selected Work versions');
        if (box?.checked && review) {{ review.click(); data.phase = 6; }}
      }} else if (data.phase === 6) {{
        const attach = button('Attach full text to this version');
        if (attach) {{ attach.click(); data.phase = 7; }}
      }} else if (data.phase === 7) {{
        const select = document.querySelector('#attachment-source');
        if (select && Array.from(select.options).some((item) => item.value === sourceId)) {{
          select.value = sourceId;
          select.dispatchEvent(new Event('change', {{ bubbles: true }}));
          data.phase = 8;
        }}
      }} else if (data.phase === 8) {{
        const zone = document.querySelector('[data-document-native-drop-target="true"]');
        if (zone) {{
          const rect = zone.getBoundingClientRect();
          const x = Math.max(4, Math.min(innerWidth - 4, rect.left + rect.width / 2));
          const y = Math.max(4, Math.min(innerHeight - 4, rect.top + Math.min(12, rect.height / 4)));
          if (rect.width > 0 && rect.height > 0 &&
              document.elementFromPoint(x, y)?.closest('[data-document-native-drop-target="true"]') === zone) {{
            data.ready = true; clearInterval(timer);
          }}
        }}
      }}
    }} catch (_) {{ data.error = 'ui-sequence-error'; clearInterval(timer); }}
  }}, 100);
}})();
"#
        )
    }

    fn document_picker_action_script(seed: &DocumentDropSeed) -> String {
        let source = serde_json::to_string(&seed.source_assertion_revision_id)
            .expect("fixture source assertion ID");
        format!(
            r#"
(() => {{
  const sourceId = {source};
  const probe = window.__RO_DROP_PROBE;
  if (!probe) return 'observer-unavailable';
  const pane = () => document.querySelector('section[aria-label="Selected-version attachment"]');
  const exactButton = (root, text) => {{
    const matches = Array.from(root?.querySelectorAll('button') ?? []).filter((item) =>
      item.textContent?.trim() === text);
    return matches.length === 1 && !matches[0].disabled ? matches[0] : null;
  }};
  const clickPicker = () => {{
    const mounted = pane();
    if (mounted?.querySelector('#attachment-source')?.value !== sourceId) return false;
    const control = exactButton(mounted, 'Choose local full-text file…');
    if (!control) return false;
    control.click(); probe.pickerAction = 'clicked'; return true;
  }};
  if (clickPicker()) return 'clicked';
  if (pane()) return 'control-unavailable';
  const reopen = exactButton(document, 'Attach full text to this version');
  if (!reopen) return 'reopen-unavailable';
  reopen.click(); probe.pickerAction = 'reopening';
  const deadline = performance.now() + 10000;
  const timer = setInterval(() => {{
    if (performance.now() >= deadline) {{ probe.pickerAction = 'reopen-timeout'; clearInterval(timer); return; }}
    const mounted = pane();
    const select = mounted?.querySelector('#attachment-source');
    if (!select) return;
    if (select.value !== sourceId) {{
      if (!Array.from(select.options).some((option) => option.value === sourceId)) {{
        probe.pickerAction = 'source-unavailable'; clearInterval(timer); return;
      }}
      select.value = sourceId;
      select.dispatchEvent(new Event('change', {{ bubbles: true }}));
      return;
    }}
    if (clickPicker()) clearInterval(timer);
  }}, 75);
  return 'reopening';
}})()
"#
        )
    }

    const DOCUMENT_COMMIT_ACTION_SCRIPT: &str = r#"
(() => {
  const probe = window.__RO_DROP_PROBE;
  if (!probe) return 'observer-unavailable';
  const pane = document.querySelector('section[aria-label="Selected-version attachment"]');
  if (!pane?.querySelector('section[aria-label="Pending document candidate"]')) return 'candidate-unavailable';
  probe.commitAction = 'reviewing';
  const deadline = performance.now() + 10000;
  const timer = setInterval(() => {
    if (performance.now() >= deadline) { probe.commitAction = 'control-timeout'; clearInterval(timer); return; }
    const candidate = document.querySelector('section[aria-label="Selected-version attachment"] section[aria-label="Pending document candidate"]');
    if (!candidate) { probe.commitAction = 'candidate-lost'; clearInterval(timer); return; }
    const label = Array.from(candidate.querySelectorAll('label')).find((item) =>
      item.textContent?.trim() === 'I confirm this file belongs to the selected Work and version shown above.');
    const check = label?.querySelector('input[type="checkbox"]');
    if (!check || check.disabled) return;
    if (!check.checked) { check.click(); return; }
    const rights = candidate.querySelector('#attachment-rights');
    if (!rights || rights.disabled || !Array.from(rights.options).some((item) => item.value === 'project-only')) return;
    if (rights.value !== 'project-only') {
      rights.value = 'project-only'; rights.dispatchEvent(new Event('change', { bubbles: true })); return;
    }
    const buttons = Array.from(candidate.querySelectorAll('button')).filter((item) =>
      item.textContent?.trim() === 'Attach to selected version' && !item.disabled);
    if (buttons.length !== 1) return;
    buttons[0].click(); probe.commitAction = 'clicked'; clearInterval(timer);
  }, 75);
  return 'reviewing';
})()
"#;

    const DOCUMENT_ACTION_READOUT_SCRIPT: &str = r#"
(() => {
  const probe = window.__RO_DROP_PROBE;
  const allowed = (value, values) => values.includes(value) ? value : null;
  const pane = document.querySelector('section[aria-label="Selected-version attachment"]');
  const pickerControls = Array.from(pane?.querySelectorAll('button') ?? []).filter((item) =>
    item.textContent?.trim() === 'Choose local full-text file…');
  return { pickerAction: allowed(probe?.pickerAction,
    ['clicked','reopening','reopen-timeout','source-unavailable']),
    commitAction: allowed(probe?.commitAction,
    ['reviewing','clicked','control-timeout','candidate-lost']),
    candidateVisible: !!document.querySelector('section[aria-label="Selected-version attachment"] section[aria-label="Pending document candidate"]'),
    paneVisible: !!pane,
    sourceSelected: typeof probe?.sourceId === 'string' && !!probe.sourceId &&
      pane?.querySelector('#attachment-source')?.value === probe.sourceId,
    pickerControlCount: pickerControls.length,
    pickerControlEnabled: pickerControls.length === 1 && !pickerControls[0].disabled };
})()
"#;

    const DROP_READOUT_SCRIPT: &str = r#"
(() => {
  const probe = window.__RO_DROP_PROBE;
  if (!probe) return { ready: false, phase: -1, error: 'observer-missing', html5: null, geometry: null };
  const zone = document.querySelector('[data-document-native-drop-target="true"]');
  let geometry = null;
  if (probe.ready && zone) {
    const rect = zone.getBoundingClientRect();
    const inside = [Math.max(4, Math.min(innerWidth - 4, rect.left + rect.width / 2)),
      Math.max(4, Math.min(innerHeight - 4, rect.top + Math.min(12, rect.height / 4)))];
    const insideHit = document.elementFromPoint(inside[0], inside[1]);
    const corners = [[4, 4], [innerWidth - 4, 4], [4, innerHeight - 4], [innerWidth - 4, innerHeight - 4]];
    const outside = corners.find(([x, y]) => {
      const hit = document.elementFromPoint(x, y);
      return hit && !hit.closest('[data-document-native-drop-target="true"]');
    });
    if (outside && rect.width > 0 && rect.height > 0 &&
        insideHit?.closest('[data-document-native-drop-target="true"]') === zone)
      geometry = { inside, outside, dpr: window.devicePixelRatio };
  }
  return { ready: probe.ready, phase: probe.phase, error: probe.error,
    html5: { ...probe.html5 }, geometry,
    controls: {
      localProjects: !!document.querySelector('button[aria-label="Local projects"]'),
      projectChoose: !!document.querySelector('#project-root-choose'),
      projectChooseEnabled: document.querySelector('#project-root-choose')?.disabled === false,
      projectOpen: !!document.querySelector('#project-root')?.closest('form')?.querySelector('button[type="submit"]'),
      projectOpenEnabled: document.querySelector('#project-root')?.closest('form')?.querySelector('button[type="submit"]')?.disabled === false,
      projectRootHasValue: !!document.querySelector('#project-root')?.value,
      boundaryState: (() => { const value = document.querySelector('[data-local-service-boundary]')?.getAttribute('data-boundary-state');
        return typeof value === 'string' && /^[a-z-]{1,32}$/.test(value) ? value : null; })(),
      currentProject: !!document.querySelector('[data-current-project]'),
      imports: !!document.querySelector('button[aria-label="Ingestion & Reconciliation"]'),
      workVersions: Array.from(document.querySelectorAll('button')).some((button) => button.textContent?.trim() === 'Open Work versions'),
      workSelect: !!document.querySelector('label input[type="checkbox"]'),
      attach: Array.from(document.querySelectorAll('button')).some((button) => button.textContent?.trim() === 'Attach full text to this version'),
      source: !!document.querySelector('#attachment-source'),
      zone: !!zone
    } };
})()
"#;

    #[derive(Default)]
    struct TauriDragCounts {
        enter: std::sync::atomic::AtomicU64,
        over: std::sync::atomic::AtomicU64,
        drop: std::sync::atomic::AtomicU64,
        leave: std::sync::atomic::AtomicU64,
    }

    impl TauriDragCounts {
        fn snapshot(&self) -> Value {
            use std::sync::atomic::Ordering::Relaxed;
            json!({"enter":self.enter.load(Relaxed), "over":self.over.load(Relaxed),
                "drop":self.drop.load(Relaxed), "leave":self.leave.load(Relaxed)})
        }
    }

    fn listen_for_tauri_drag(window: &tauri::WebviewWindow) -> std::sync::Arc<TauriDragCounts> {
        use std::sync::{Arc, atomic::Ordering::Relaxed};
        use tauri::Listener;
        let counts = Arc::new(TauriDragCounts::default());
        for (name, counter) in [
            ("tauri://drag-enter", &counts.enter),
            ("tauri://drag-over", &counts.over),
            ("tauri://drag-drop", &counts.drop),
            ("tauri://drag-leave", &counts.leave),
        ] {
            let counts = Arc::clone(&counts);
            let which = name;
            let _ = counter;
            window.listen(which, move |_| {
                let selected = match which {
                    "tauri://drag-enter" => &counts.enter,
                    "tauri://drag-over" => &counts.over,
                    "tauri://drag-drop" => &counts.drop,
                    _ => &counts.leave,
                };
                selected.fetch_add(1, Relaxed);
            });
        }
        counts
    }

    fn safe_document_stage_probe_event(payload: &str) -> Option<Value> {
        let value: Value = serde_json::from_str(payload).ok()?;
        let status = value.get("status")?.as_str()?;
        if !matches!(status, "candidate" | "rejected" | "cancelled") {
            return None;
        }
        let operation = value.get("operationId")?.as_str()?;
        if !crate::supervisor::canonical_uuid_v7(operation) {
            return None;
        }
        let candidate = value
            .get("candidate")
            .and_then(|item| item.get("candidateId"))
            .and_then(Value::as_str)
            .filter(|id| crate::supervisor::canonical_uuid_v7(id));
        if status == "candidate" && candidate.is_none() {
            return None;
        }
        let code = value.get("code").and_then(Value::as_str).filter(|code| {
            (1..=40).contains(&code.len())
                && code
                    .bytes()
                    .all(|byte| byte.is_ascii_lowercase() || byte == b'-')
        });
        Some(
            json!({"kind":"document-drop-probe-stage-result","status":status,
            "code":code,"operationId":operation,"candidateId":candidate}),
        )
    }

    fn listen_for_document_stage(
        window: &tauri::WebviewWindow,
        picker_pending: std::sync::Arc<std::sync::atomic::AtomicBool>,
    ) {
        use tauri::Listener;
        window.listen("document_attachment_result", move |event| {
            if let Some(safe) = safe_document_stage_probe_event(event.payload()) {
                if picker_pending.swap(false, std::sync::atomic::Ordering::AcqRel) {
                    let status = match safe["status"].as_str() {
                        Some("candidate") => "selected",
                        Some("cancelled") => "cancelled",
                        _ => "rejected",
                    };
                    emit(json!({"kind":"document-attachment-probe-picker-result",
                        "status":status,"operationId":safe["operationId"],
                        "candidateId":safe["candidateId"],"code":safe["code"]}));
                }
                emit(safe);
            }
        });
    }

    fn commit_receipt_from_native(
        fixture: &Fixture,
        request: &Value,
        result: &Value,
    ) -> Result<DocumentDropCommitReceipt, &'static str> {
        if !fixture.document_drop_mode() {
            return Err("mode");
        }
        if request["schemaVersion"] != "1.0" {
            return Err("request-schema");
        }
        if request["matchConfirmed"] != true {
            return Err("match-confirmation");
        }
        if request["permittedUse"] != "project-only" {
            return Err("permitted-use");
        }
        if result["schemaVersion"] != "1.0" {
            return Err("result-schema");
        }
        if result["status"] != "attached" {
            return Err("result-status");
        }
        if request["operationId"] != result["operationId"] {
            return Err("operation-binding");
        }
        if request["sessionId"] != result["sessionId"] {
            return Err("session-binding");
        }
        if request["candidateId"] != result["candidateId"] {
            return Err("candidate-binding");
        }
        if request["selection"] != result["selection"] {
            return Err("selection-binding");
        }
        let seed: DocumentDropSeed =
            read_document_receipt(fixture, DOCUMENT_DROP_SEED_RECEIPT).map_err(|_| "seed-read")?;
        validate_document_drop_seed(fixture, &seed).map_err(|_| "seed-validation")?;
        let selection: DocumentDropSelection =
            serde_json::from_value(request["selection"].clone()).map_err(|_| "selection-decode")?;
        let field = |value: &Value, name: &str, check| -> Result<String, &'static str> {
            value[name].as_str().map(str::to_owned).ok_or(check)
        };
        let receipt = DocumentDropCommitReceipt {
            schema_version: "1.0".into(),
            selection,
            operation_id: field(request, "operationId", "operation-field")?,
            command_id: field(request, "commandId", "command-field")?,
            candidate_id: field(request, "candidateId", "candidate-field")?,
            attachment_id: field(result, "attachmentId", "attachment-field")?,
            document_revision_id: field(result, "documentRevisionId", "revision-field")?,
        };
        let session = field(request, "sessionId", "session-field")?;
        let confirmation = field(request, "confirmationSha256", "confirmation-field")?;
        if receipt.selection != DocumentDropSelection::from(&seed) {
            return Err("seed-selection-binding");
        }
        if !receipt.valid_for(&seed) {
            return Err("receipt-id-format");
        }
        if !lower_hex_exact(&session, 32) {
            return Err("session-format");
        }
        if !lower_hex_exact(&confirmation, 64) {
            return Err("confirmation-format");
        }
        Ok(receipt)
    }

    fn lower_hex_exact(value: &str, length: usize) -> bool {
        value.len() == length
            && value
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    }

    pub(crate) fn observe_document_commit(
        window: &tauri::WebviewWindow,
        request: &Value,
        result: &Value,
    ) {
        let Some(fixture) = window.try_state::<Fixture>() else {
            emit(json!({"kind":"document-attachment-probe-commit",
                "status":"unverified","code":"fixture-unavailable"}));
            return;
        };
        let receipt = match commit_receipt_from_native(&fixture, request, result) {
            Ok(receipt) => receipt,
            Err(check) => {
                // The closed check name is diagnostic only; the public probe
                // event stays generic and carries no authority-bearing data.
                eprintln!("RO-DOCUMENT-COMMIT-PROBE check={check}");
                emit(json!({"kind":"document-attachment-probe-commit",
                    "status":"unverified","code":"identity-invalid"}));
                return;
            }
        };
        if write_document_receipt(&fixture, DOCUMENT_DROP_COMMIT_RECEIPT, &receipt).is_err() {
            emit(json!({"kind":"document-attachment-probe-commit",
                "status":"unverified","code":"receipt-unavailable"}));
            return;
        }
        emit(
            json!({"kind":"document-attachment-probe-commit", "status":"attached",
            "receiptSaved":true,"selectionIds":receipt.selection,
            "operationId":receipt.operation_id,"commandId":receipt.command_id,
            "candidateId":receipt.candidate_id,"attachmentId":receipt.attachment_id,
            "documentRevisionId":receipt.document_revision_id}),
        );
    }

    fn safe_document_stage_finish(
        operation_id: &str,
        status: &str,
        code: Option<&str>,
        candidate_id: Option<&str>,
        protected_closure_entered: bool,
        event_emit_succeeded: bool,
        delivery_error: Option<&str>,
    ) -> Option<Value> {
        if !crate::supervisor::canonical_uuid_v7(operation_id) {
            return None;
        }
        let status = if matches!(status, "candidate" | "rejected" | "cancelled") {
            status
        } else {
            "unavailable"
        };
        let code = code.filter(|code| {
            (1..=40).contains(&code.len())
                && code
                    .bytes()
                    .all(|byte| byte.is_ascii_lowercase() || byte == b'-')
        });
        let candidate_id = candidate_id.filter(|id| crate::supervisor::canonical_uuid_v7(id));
        let delivery_code = match delivery_error {
            None => None,
            Some("RO-APPLICATION-LOCKED") => Some("lock-denied"),
            Some("RO-DOCUMENT-SESSION-UNAVAILABLE") => Some("session-denied"),
            Some("RO-DOCUMENT-OPERATION-UNAVAILABLE") => Some("operation-denied"),
            Some("RO-DOCUMENT-EVENT-UNAVAILABLE") => Some("event-failed"),
            Some("RO-DOCUMENT-STATE-UNAVAILABLE") => Some("state-unavailable"),
            Some(_) => Some("other-denied"),
        };
        Some(json!({"kind":"document-drop-probe-stage-finish",
            "operationId":operation_id,"status":status,"code":code,"candidateId":candidate_id,
            "protectedClosureEntered":protected_closure_entered,
            "protectedCommitSucceeded":delivery_error.is_none(),
            "eventEmitSucceeded":event_emit_succeeded,"deliveryCode":delivery_code}))
    }

    pub(crate) fn observe_document_stage_finish(
        operation_id: &str,
        status: &str,
        code: Option<&str>,
        candidate_id: Option<&str>,
        protected_closure_entered: bool,
        event_emit_succeeded: bool,
        delivery_error: Option<&str>,
    ) {
        if let Some(safe) = safe_document_stage_finish(
            operation_id,
            status,
            code,
            candidate_id,
            protected_closure_entered,
            event_emit_succeeded,
            delivery_error,
        ) {
            emit(safe);
        }
    }

    fn safe_document_transport_phase(phase: &str, code: Option<&str>) -> Option<Value> {
        if !matches!(
            phase,
            "spawn-scheduled"
                | "body-start"
                | "header-sent"
                | "source-transfer-complete"
                | "response-accepted"
                | "response-rejected"
                | "transport-error"
                | "finish-invoked"
                | "response-read-end"
                | "response-read-error"
                | "response-parse-error"
                | "response-http-class"
        ) {
            return None;
        }
        let error = match phase {
            "transport-error" => Some(match code {
                Some("RO-CORE-API-CANCELLED") => "cancelled",
                Some("RO-DOCUMENT-STAGE-INVALID") => "invalid",
                Some("RO-DOCUMENT-STAGE-EARLY-RESPONSE") => "early-response",
                Some("RO-DOCUMENT-STAGE-RESPONSE-INVALID") => "response-invalid",
                Some("RO-DOCUMENT-STAGE-UNAVAILABLE") => "unavailable",
                Some("RO-DOCUMENT-STAGE-TIMEOUT") => "timeout",
                Some("RO-CORE-API-RESPONSE-INVALID") => "http-invalid",
                Some("RO-IMPORT-SOURCE-CANCELLED") => "source-cancelled",
                Some(_) | None => "other",
            }),
            "response-read-end" => match code {
                Some("eof-empty" | "eof-with-data" | "io-after-data") => code,
                _ => return None,
            },
            "response-read-error" => match code {
                Some("cancelled" | "timeout" | "io-empty" | "oversize") => code,
                _ => return None,
            },
            "response-parse-error" => match code {
                Some(
                    "head-incomplete" | "head-decode" | "status-invalid" | "trace-missing"
                    | "trace-mismatch" | "framing-invalid" | "body-decode" | "other-invalid",
                ) => code,
                _ => return None,
            },
            "response-http-class" => match code {
                Some("2xx" | "3xx" | "4xx" | "5xx" | "invalid") => code,
                _ => return None,
            },
            _ => None,
        };
        Some(json!({"kind":"document-drop-probe-transport","phase":phase,"code":error}))
    }

    pub(crate) fn observe_document_transport_phase(
        phase: &'static str,
        code: Option<&'static str>,
    ) {
        if let Some(safe) = safe_document_transport_phase(phase, code) {
            emit(safe);
        }
    }

    fn safe_document_drop_decision(
        reason: &str,
        cache_age: &str,
        probe_pending: bool,
    ) -> Option<Value> {
        if !matches!(
            reason,
            "accepted"
                | "not-armed"
                | "point-unavailable"
                | "cache-lock"
                | "cache-operation"
                | "cache-point"
                | "cache-unknown"
                | "cache-negative"
                | "cache-expired"
                | "source-format"
                | "source-open"
                | "stage-admission"
        ) || !matches!(
            cache_age,
            "none" | "fresh" | "aging" | "expired-short" | "expired-long"
        ) {
            return None;
        }
        Some(
            json!({"kind":"document-drop-probe-native-decision", "reason":reason,
            "cacheAge":cache_age,"probePending":probe_pending}),
        )
    }

    pub(crate) fn observe_document_drop_decision(
        reason: &'static str,
        cache_age: &'static str,
        probe_pending: bool,
    ) {
        if let Some(safe) = safe_document_drop_decision(reason, cache_age, probe_pending) {
            emit(safe);
        }
    }

    fn drop_geometry(window: &tauri::WebviewWindow, readout: &Value) -> Option<(Value, Value)> {
        let geometry = readout.get("geometry")?;
        let dpr = geometry.get("dpr")?.as_f64()?;
        let point = |key: &str| -> Option<(f64, f64)> {
            let values = geometry.get(key)?.as_array()?;
            if values.len() != 2 {
                return None;
            }
            Some((values[0].as_f64()?, values[1].as_f64()?))
        };
        let inside = crate::document_drop::screen_point(window, point("inside")?, dpr)?;
        let outside = crate::document_drop::screen_point(window, point("outside")?, dpr)?;
        Some((
            json!({"x":inside.0,"y":inside.1}),
            json!({"x":outside.0,"y":outside.1}),
        ))
    }

    // Explicit fixture mode only. No arm/picker/stdin dispatcher is created until
    // the hidden actual-five installation and expected-identity rollback pass.
    fn observe_five_node_install(
        app: AppHandle,
        fixture: Fixture,
        seed: DocumentDropSeed,
        tauri_drag: std::sync::Arc<TauriDragCounts>,
        picker_pending: std::sync::Arc<std::sync::atomic::AtomicBool>,
    ) {
        use std::sync::{
            Arc,
            atomic::{AtomicBool, Ordering},
        };
        let finished = Arc::new(AtomicBool::new(false));
        let inflight = Arc::new(AtomicBool::new(false));
        std::thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(15);
            while Instant::now() < deadline && !finished.load(Ordering::Acquire) {
                if inflight
                    .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
                    .is_ok()
                {
                    let (
                        callback_app,
                        callback_fixture,
                        callback_seed,
                        callback_drag,
                        callback_picker,
                        callback_finished,
                        callback_inflight,
                    ) = (
                        app.clone(),
                        fixture.clone(),
                        seed.clone(),
                        Arc::clone(&tauri_drag),
                        Arc::clone(&picker_pending),
                        Arc::clone(&finished),
                        Arc::clone(&inflight),
                    );
                    if app
                        .run_on_main_thread(move || {
                            if callback_finished.load(Ordering::Acquire) {
                                callback_inflight.store(false, Ordering::Release);
                                return;
                            }
                            let result = (|| {
                                callback_fixture.revalidate()?;
                                let window = callback_app
                                    .get_webview_window("main")
                                    .ok_or("probe-five-window-unavailable")?;
                                if !crate::document_drop::five_node_ready(&window)? {
                                    return Ok(None);
                                }
                                let manager = callback_app
                                    .state::<document_attachment::DocumentAttachmentManager>(
                                );
                                if callback_picker.load(Ordering::Acquire)
                                    || callback_drag.snapshot().as_object().is_none_or(|values| {
                                        values.values().any(|value| value.as_u64() != Some(0))
                                    })
                                {
                                    return Err("probe-five-warmup-admission-observed");
                                }
                                let observed = crate::document_drop::exercise_five_node_install(
                                    &window, &manager,
                                )?;
                                // Only these exact guarded fixture calls restore availability.
                                manager.set_installed(true);
                                window.show().map_err(|_| "probe-five-window-show-failed")?;
                                window
                                    .eval("window.__RO_DROP_PROBE.fiveInstallReady = true;")
                                    .map_err(|_| "probe-five-ui-dispatch-unavailable")?;
                                Ok(Some(observed))
                            })();
                            match result {
                                Ok(Some(observed)) => {
                                    callback_finished.store(true, Ordering::Release);
                                    emit(observed);
                                    observe_document_drop(
                                        callback_app,
                                        callback_seed,
                                        callback_drag,
                                        callback_picker,
                                    );
                                }
                                Ok(None) => {}
                                Err(error) => {
                                    callback_finished.store(true, Ordering::Release);
                                    callback_app
                                        .state::<document_attachment::DocumentAttachmentManager>()
                                        .set_installed(false);
                                    if let Some(window) = callback_app.get_webview_window("main") {
                                        let _ = window.hide();
                                    }
                                    crate::document_drop::uninstall();
                                    emit(json!({"kind":"document-drop-probe-failure","code":error,
                                    "phase":"actual-five-node-hidden-reinstallation"}));
                                    callback_app.exit(1);
                                }
                            }
                            callback_inflight.store(false, Ordering::Release);
                        })
                        .is_err()
                    {
                        finished.store(true, Ordering::Release);
                        emit(
                            json!({"kind":"document-drop-probe-failure","code":"probe-five-dispatch-unavailable"}),
                        );
                        app.exit(1);
                    }
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            if !finished.load(Ordering::Acquire) {
                let callback_app = app.clone();
                let _ = app.run_on_main_thread(move || {
                    if finished.swap(true, Ordering::AcqRel) { return; }
                    callback_app.state::<document_attachment::DocumentAttachmentManager>().set_installed(false);
                    if let Some(window) = callback_app.get_webview_window("main") { let _ = window.hide(); }
                    crate::document_drop::uninstall();
                    emit(json!({"kind":"document-drop-probe-failure","code":"probe-five-natural-leaf-timeout"}));
                    callback_app.exit(1);
                });
            }
        });
    }

    fn observe_document_drop(
        app: AppHandle,
        seed: DocumentDropSeed,
        tauri_drag: std::sync::Arc<TauriDragCounts>,
        picker_pending: std::sync::Arc<std::sync::atomic::AtomicBool>,
    ) {
        use std::sync::{
            Arc,
            atomic::{AtomicBool, Ordering},
        };
        let ready_sent = Arc::new(AtomicBool::new(false));
        let armed_sent = Arc::new(AtomicBool::new(false));
        let poll_app = app.clone();
        let poll_ready = Arc::clone(&ready_sent);
        let poll_armed = Arc::clone(&armed_sent);
        let poll_drag = Arc::clone(&tauri_drag);
        let poll_seed = seed.clone();
        let progress = Arc::new(std::sync::Mutex::new((None, Instant::now())));
        std::thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(150);
            while Instant::now() < deadline {
                let Some(window) = poll_app.get_webview_window("main") else {
                    break;
                };
                if !poll_ready.load(Ordering::Acquire) {
                    let (
                        callback_window,
                        callback_ready,
                        callback_drag,
                        callback_app,
                        callback_seed,
                        callback_progress,
                    ) = (
                        window.clone(),
                        Arc::clone(&poll_ready),
                        Arc::clone(&poll_drag),
                        poll_app.clone(),
                        poll_seed.clone(),
                        Arc::clone(&progress),
                    );
                    let _ = window.eval_with_callback(DROP_READOUT_SCRIPT, move |raw| {
                        let Ok(readout) = serde_json::from_str::<Value>(&raw) else { return; };
                        if let Some(phase) = readout["phase"].as_u64()
                            && let Ok(mut progress) = callback_progress.lock()
                            && (progress.0 != Some(phase) || progress.1.elapsed() >= Duration::from_secs(5))
                        {
                            progress.0 = Some(phase);
                            progress.1 = Instant::now();
                            let supervisor = callback_app.state::<RuntimeSupervisor>();
                            let core = supervisor.status();
                            let recent_codes: Vec<&str> = supervisor.diagnostics().iter().rev()
                                .take(8).map(|item| item.code).collect();
                            emit(json!({"kind":"document-drop-probe-progress", "phase":phase,
                                "ready":readout["ready"], "error":readout["error"],
                                "controls":readout["controls"],
                                "coreState":core.state,"coreDiagnostic":core.diagnostic_reference,
                                "coreRecentCodes":recent_codes}));
                        }
                        if readout["error"].is_string() && readout["error"] != Value::Null {
                            if !callback_ready.swap(true, Ordering::AcqRel) {
                                emit(json!({"kind":"document-drop-probe-failure","phase":readout["phase"],
                                    "code":readout["error"]}));
                            }
                            return;
                        }
                        if readout["ready"] != true { return; }
                        let Some((inside, outside)) = drop_geometry(&callback_window, &readout) else { return; };
                        if callback_ready.swap(true, Ordering::AcqRel) { return; }
                        emit(json!({"kind":"document-drop-probe-ready",
                            "ownerHwnd":callback_window.hwnd().ok().map(|hwnd| hwnd.0 as isize),
                            "insideScreen":inside,"outsideScreen":outside,
                            "targetClasses":crate::document_drop::target_classes(),
                            "observationInstalled":true,"armed":false,
                            "native":crate::document_drop::counts(),"tauri":callback_drag.snapshot(),
                            "html5":readout["html5"],
                            "selectionIds":{"projectId":callback_seed.project_id,
                                "workId":callback_seed.work_id,"workRevisionId":callback_seed.work_revision_id,
                                "versionId":callback_seed.version_id,"versionRevisionId":callback_seed.version_revision_id,
                                "sourceAssertionRevisionId":callback_seed.source_assertion_revision_id},
                            "coreState":callback_app.state::<RuntimeSupervisor>().status().state}));
                    });
                }
                if poll_ready.load(Ordering::Acquire)
                    && !poll_armed.load(Ordering::Acquire)
                    && poll_app
                        .state::<document_attachment::DocumentAttachmentManager>()
                        .armed_drop()
                        .is_some()
                {
                    poll_armed.store(true, Ordering::Release);
                    emit(json!({"kind":"document-drop-probe-armed","armed":true,
                        "native":crate::document_drop::counts(),"tauri":poll_drag.snapshot()}));
                }
                std::thread::sleep(Duration::from_millis(100));
            }
            if !poll_ready.load(Ordering::Acquire) {
                emit(json!({"kind":"document-drop-probe-failure","code":"readiness-timeout"}));
            }
        });

        std::thread::spawn(move || {
            use std::io::BufRead;
            for line in std::io::stdin().lock().lines() {
                let Ok(line) = line else {
                    break;
                };
                if line.len() > 256 {
                    continue;
                }
                let Ok(command) = serde_json::from_str::<Value>(&line) else {
                    continue;
                };
                let Some(window) = app.get_webview_window("main") else {
                    break;
                };
                match command["action"].as_str() {
                    Some("arm") => {
                        let _ = window.eval("(() => { const zone = document.querySelector('[data-document-native-drop-target=\"true\"]'); const button = Array.from(zone?.querySelectorAll('button') ?? []).find((item) => item.textContent?.trim() === 'Arm native file drop' && !item.disabled); button?.click(); })()");
                    }
                    Some("observe") => {
                        let Some(attempt) = command["attempt"].as_str().filter(|value| {
                            matches!(
                                *value,
                                "outside-disarmed" | "inside-disarmed" | "outside-armed" | "inside"
                            )
                        }) else {
                            continue;
                        };
                        let (attempt, counts, check_app) =
                            (attempt.to_owned(), Arc::clone(&tauri_drag), app.clone());
                        let _ = window.eval_with_callback(DROP_READOUT_SCRIPT, move |raw| {
                            let readout = serde_json::from_str::<Value>(&raw).unwrap_or(Value::Null);
                            emit(json!({"kind":"document-drop-probe-observation","attempt":attempt,
                                "armed":check_app.state::<document_attachment::DocumentAttachmentManager>().armed_drop().is_some(),
                                "native":crate::document_drop::counts(),"tauri":counts.snapshot(),
                                "html5":readout["html5"],"uiPhase":readout["phase"],"uiError":readout["error"]}));
                        });
                        let _ = window.eval_with_callback(DOCUMENT_ACTION_READOUT_SCRIPT, |raw| {
                            if let Ok(value) = serde_json::from_str::<Value>(&raw) {
                                emit(json!({"kind":"document-attachment-probe-action-state",
                                    "pickerAction":value["pickerAction"],
                                    "commitAction":value["commitAction"],
                                    "candidateVisible":value["candidateVisible"],
                                    "paneVisible":value["paneVisible"],
                                    "sourceSelected":value["sourceSelected"],
                                    "pickerControlCount":value["pickerControlCount"],
                                    "pickerControlEnabled":value["pickerControlEnabled"]}));
                            }
                        });
                    }
                    Some("choose") => {
                        picker_pending.store(true, Ordering::Release);
                        let flag = Arc::clone(&picker_pending);
                        let script = document_picker_action_script(&seed);
                        let _ = window.eval_with_callback(&script, move |raw| {
                            let status = serde_json::from_str::<String>(&raw)
                                .ok()
                                .filter(|status| {
                                    matches!(
                                        status.as_str(),
                                        "clicked"
                                            | "reopening"
                                            | "control-unavailable"
                                            | "reopen-unavailable"
                                            | "observer-unavailable"
                                    )
                                })
                                .unwrap_or_else(|| "eval-unavailable".into());
                            if !matches!(status.as_str(), "clicked" | "reopening") {
                                flag.store(false, Ordering::Release);
                            }
                            emit(json!({"kind":"document-attachment-probe-picker-action",
                                "status":status}));
                        });
                    }
                    Some("commit-project-only") => {
                        let _ = window.eval_with_callback(DOCUMENT_COMMIT_ACTION_SCRIPT, |raw| {
                            let status = serde_json::from_str::<String>(&raw)
                                .ok()
                                .filter(|status| {
                                    matches!(
                                        status.as_str(),
                                        "reviewing"
                                            | "candidate-unavailable"
                                            | "observer-unavailable"
                                    )
                                })
                                .unwrap_or_else(|| "eval-unavailable".into());
                            emit(json!({"kind":"document-attachment-probe-commit-action",
                                "status":status}));
                        });
                    }
                    Some("close") => {
                        let _ = window.close();
                        break;
                    }
                    _ => {}
                }
            }
        });
    }

    fn observe_document_resume(app: AppHandle, fixture: Fixture, seed: DocumentDropSeed) {
        use std::sync::{
            Arc,
            atomic::{AtomicBool, Ordering},
        };
        let ready = Arc::new(AtomicBool::new(false));
        let poll_app = app.clone();
        let poll_ready = Arc::clone(&ready);
        std::thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(150);
            while Instant::now() < deadline && !poll_ready.load(Ordering::Acquire) {
                let Some(window) = poll_app.get_webview_window("main") else {
                    break;
                };
                let (callback_window, callback_fixture, callback_seed, callback_ready) = (
                    window.clone(),
                    fixture.clone(),
                    seed.clone(),
                    Arc::clone(&poll_ready),
                );
                let _ = window.eval_with_callback(DROP_READOUT_SCRIPT, move |raw| {
                    let Ok(readout) = serde_json::from_str::<Value>(&raw) else {
                        return;
                    };
                    if readout["error"].is_string() && readout["error"] != Value::Null {
                        if !callback_ready.swap(true, Ordering::AcqRel) {
                            emit(json!({"kind":"document-attachment-probe-resume-failure",
                                "code":"ui-unavailable","phase":readout["phase"]}));
                        }
                        return;
                    }
                    if readout["ready"] != true || callback_ready.swap(true, Ordering::AcqRel) {
                        return;
                    }
                    emit(json!({"kind":"document-attachment-probe-resume-ready",
                        "selectionIds":DocumentDropSelection::from(&callback_seed),
                        "resumedOriginalFixture":true,"reseeding":false}));
                    let (status_window, status_fixture, status_seed) = (
                        callback_window.clone(),
                        callback_fixture.clone(),
                        callback_seed.clone(),
                    );
                    std::thread::spawn(move || {
                        let receipt: DocumentDropCommitReceipt =
                            match read_document_receipt::<DocumentDropCommitReceipt>(
                                &status_fixture,
                                DOCUMENT_DROP_COMMIT_RECEIPT,
                            ) {
                                Ok(receipt) if receipt.valid_for(&status_seed) => receipt,
                                _ => {
                                    emit(json!({"kind":"document-attachment-probe-resume-failure",
                                    "code":"receipt-invalid"}));
                                    return;
                                }
                            };
                        let request = json!({"schemaVersion":"1.0",
                            "selection":receipt.selection,"operationId":receipt.operation_id,
                            "commandId":receipt.command_id});
                        let Ok(request) = serde_json::from_value::<
                            crate::document_attachment::StatusRequest,
                        >(request) else {
                            emit(json!({"kind":"document-attachment-probe-resume-failure",
                                "code":"request-invalid"}));
                            return;
                        };
                        let result = tauri::async_runtime::block_on(
                            crate::document_attachment::document_attachment_status(
                                status_window.clone(),
                                status_window
                                    .state::<crate::document_attachment::DocumentAttachmentManager>(
                                    ),
                                status_window.state::<RuntimeSupervisor>(),
                                status_window.state::<ApplicationLockManager>(),
                                request,
                            ),
                        );
                        let received = result.ok().flatten().unwrap_or(Value::Null);
                        let status = received["status"]
                            .as_str()
                            .filter(|value| {
                                matches!(
                                    *value,
                                    "processing"
                                        | "available"
                                        | "metadata-only"
                                        | "unavailable"
                                        | "candidate"
                                        | "cancelled"
                                        | "unconfirmed"
                                        | "denied"
                                        | "failed"
                                )
                            })
                            .unwrap_or("unavailable");
                        let exact = matches!(status, "processing" | "available")
                            && received["schemaVersion"] == "1.0"
                            && received["selection"]
                                == serde_json::to_value(&receipt.selection).unwrap_or(Value::Null)
                            && received["operationId"] == receipt.operation_id
                            && received["commandId"] == receipt.command_id
                            && received["attachmentId"] == receipt.attachment_id
                            && received["documentRevisionId"] == receipt.document_revision_id;
                        emit(json!({"kind":"document-attachment-probe-resume-status",
                            "status":status,"exact":exact,"selectionIds":receipt.selection,
                            "operationId":receipt.operation_id,"commandId":receipt.command_id,
                            "candidateId":receipt.candidate_id,"attachmentId":receipt.attachment_id,
                            "documentRevisionId":receipt.document_revision_id}));
                    });
                });
                std::thread::sleep(Duration::from_millis(100));
            }
            if !poll_ready.load(Ordering::Acquire) {
                emit(json!({"kind":"document-attachment-probe-resume-failure",
                    "code":"readiness-timeout"}));
            }
        });
        std::thread::spawn(move || {
            use std::io::BufRead;
            for line in std::io::stdin().lock().lines() {
                let Ok(line) = line else {
                    break;
                };
                if line.len() > 256 {
                    continue;
                }
                let Ok(command) = serde_json::from_str::<Value>(&line) else {
                    continue;
                };
                if command["action"] == "close" {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.close();
                    }
                    break;
                }
            }
        });
    }

    // At most 512 spans (two records each); no worker, timer, or policy data.
    // Router return is not response delivery. Body timing encloses status() but
    // emits only before/after its internal mutex is held. Logging can perturb
    // timing, so these are diagnostic observations, never latency qualification.
    struct StatusDiagnostics {
        origin: Instant,
        spans: std::sync::atomic::AtomicUsize,
    }

    impl StatusDiagnostics {
        fn new() -> Self {
            Self {
                origin: Instant::now(),
                spans: std::sync::atomic::AtomicUsize::new(0),
            }
        }

        fn reserve(&self) -> Option<usize> {
            use std::sync::atomic::Ordering;
            self.spans
                .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |count| {
                    (count < 512).then_some(count + 1)
                })
                .ok()
                .map(|previous| previous + 1)
        }
    }

    pub(crate) struct StatusTrace {
        diagnostics: std::sync::Arc<StatusDiagnostics>,
        span: usize,
        phase: &'static str,
        entered: Instant,
    }

    impl Drop for StatusTrace {
        fn drop(&mut self) {
            emit(
                json!({"kind":"fixture-lock-status-timing", "span":self.span,
                "phase":self.phase, "boundary":"returned",
                "nativeElapsedMs":self.diagnostics.origin.elapsed().as_secs_f64() * 1000.0,
                "spanElapsedMs":self.entered.elapsed().as_secs_f64() * 1000.0}),
            );
        }
    }

    // Fixture-only passive timing above the same shared main_menu callback
    // used in production. This observer never changes/posts a message. Private
    // alias spans enclose native replay; the clock is shared with status spans.
    // Logging may perturb timing and proves neither sender identity nor decoded
    // IPC delivery. C's pending/token experiment is retired, not relabeled.
    struct MenuDiagnostics {
        clock: std::sync::Arc<StatusDiagnostics>,
        spans: std::sync::atomic::AtomicUsize,
    }

    impl MenuDiagnostics {
        fn new(clock: std::sync::Arc<StatusDiagnostics>) -> Self {
            Self {
                clock,
                spans: std::sync::atomic::AtomicUsize::new(0),
            }
        }

        fn observe(
            &self,
            message: Option<[u32; 2]>,
            mut send_state: impl FnMut() -> u32,
            forward: impl FnOnce() -> isize,
            mut record: impl FnMut(Value),
        ) -> isize {
            use std::sync::atomic::Ordering;
            let Some([event, detail]) = message else {
                return forward();
            };
            let Ok(previous) =
                self.spans
                    .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |count| {
                        (count < 128).then_some(count + 1)
                    })
            else {
                return forward();
            };
            let span = previous + 1;
            let entered = Instant::now();
            record(json!({"kind":"fixture-menu-timing", "span":span,
                "event":event, "detail":detail, "phase":0, "sendState":send_state(),
                "spanLimit":128, "lastAdmittedSpan":span == 128,
                "nativeElapsedMs":self.clock.origin.elapsed().as_secs_f64() * 1000.0}));
            let result = forward();
            record(json!({"kind":"fixture-menu-timing", "span":span,
                "event":event, "detail":detail, "phase":1, "sendState":send_state(),
                "nativeElapsedMs":self.clock.origin.elapsed().as_secs_f64() * 1000.0,
                "spanElapsedMs":entered.elapsed().as_secs_f64() * 1000.0}));
            result
        }
    }

    fn menu_message(message: u32, wparam: usize, lparam: isize) -> Option<[u32; 2]> {
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            SC_KEYMENU, WM_ENTERMENULOOP, WM_EXITMENULOOP, WM_SYSCOMMAND,
        };
        match message {
            // Do not retain the character code: detail is only "space" or not.
            WM_SYSCOMMAND if wparam & 0xfff0 == SC_KEYMENU as usize => {
                Some([message, u32::from(lparam == 32)])
            }
            main_menu::REPLAY_MESSAGE if main_menu::valid_payload(wparam, lparam) => {
                Some([message, 1])
            }
            // Here detail is only the documented popup-menu boolean.
            WM_ENTERMENULOOP | WM_EXITMENULOOP => Some([message, u32::from(wparam != 0)]),
            _ => None,
        }
    }

    fn menu_owner_matches(
        thread: u32,
        process: u32,
        current_thread: u32,
        current_process: u32,
    ) -> bool {
        main_menu::owner_matches(thread, process, current_thread, current_process)
    }

    unsafe extern "system" fn menu_diagnostic_proc(
        hwnd: windows_sys::Win32::Foundation::HWND,
        message: u32,
        wparam: usize,
        lparam: isize,
        subclass_id: usize,
        data: usize,
    ) -> isize {
        use windows_sys::Win32::UI::{
            Shell::{DefSubclassProc, RemoveWindowSubclass},
            WindowsAndMessaging::{InSendMessageEx, WM_NCDESTROY},
        };
        if data == 0 || subclass_id != menu_diagnostic_proc as *const () as usize {
            return unsafe { DefSubclassProc(hwnd, message, wparam, lparam) };
        }
        // Only install_menu_diagnostics creates this box, on the owning thread.
        // Clone before forwarding: DefSubclassProc may destroy the window
        // reentrantly and remove/free its boxed registration before returning.
        let diagnostics = unsafe { &*(data as *const std::sync::Arc<MenuDiagnostics>) }.clone();
        if message == WM_NCDESTROY {
            let removed =
                unsafe { RemoveWindowSubclass(hwnd, Some(menu_diagnostic_proc), subclass_id) } != 0;
            if removed {
                drop(unsafe { Box::from_raw(data as *mut std::sync::Arc<MenuDiagnostics>) });
            }
            // On removal failure retain the one allocation rather than leave a
            // registered dangling pointer. The explicit failed row is adverse
            // diagnostic evidence; process teardown reclaims the allocation.
            emit(json!({"kind":"fixture-menu-subclass", "phase":1, "succeeded":removed}));
        }
        diagnostics.observe(
            menu_message(message, wparam, lparam),
            || unsafe { InSendMessageEx(std::ptr::null()) },
            || unsafe { DefSubclassProc(hwnd, message, wparam, lparam) },
            emit,
        )
    }

    fn install_menu_diagnostics(
        window: &tauri::WebviewWindow,
        fixture: &Fixture,
    ) -> Result<(), &'static str> {
        use windows_sys::Win32::{
            System::Threading::{GetCurrentProcessId, GetCurrentThreadId},
            UI::{
                Shell::{GetWindowSubclass, SetWindowSubclass},
                WindowsAndMessaging::GetWindowThreadProcessId,
            },
        };
        if window.label() != "main"
            || window.try_state::<Fixture>().is_none_or(|owned| {
                !std::sync::Arc::ptr_eq(&owned.status_diagnostics, &fixture.status_diagnostics)
            })
        {
            return Err("probe-menu-owner-invalid");
        }
        let hwnd = window
            .hwnd()
            .map_err(|_| "probe-menu-window-unavailable")?
            .0;
        let mut process = 0;
        let thread = unsafe { GetWindowThreadProcessId(hwnd, &mut process) };
        if !menu_owner_matches(thread, process, unsafe { GetCurrentThreadId() }, unsafe {
            GetCurrentProcessId()
        }) {
            return Err("probe-menu-thread-or-process-invalid");
        }
        let id = menu_diagnostic_proc as *const () as usize;
        let mut previous = 0;
        if unsafe { GetWindowSubclass(hwnd, Some(menu_diagnostic_proc), id, &mut previous) } != 0 {
            return Err("probe-menu-observer-already-installed");
        }
        let diagnostics = Box::new(std::sync::Arc::new(MenuDiagnostics::new(
            fixture.status_diagnostics.clone(),
        )));
        let data = Box::into_raw(diagnostics);
        if unsafe { SetWindowSubclass(hwnd, Some(menu_diagnostic_proc), id, data as usize) } == 0 {
            drop(unsafe { Box::from_raw(data) });
            return Err("probe-menu-observer-install-failed");
        }
        emit(json!({"kind":"fixture-menu-subclass", "phase":0, "succeeded":true}));
        Ok(())
    }

    const FIXTURE_DIRECTORIES: [&str; 6] = [
        "application-data",
        "projects",
        "vault",
        "webview",
        "temporary",
        "application-data/security",
    ];

    // This is fixture provenance, not a capability or a production controller.
    // Resume accepts only the original directory identities in our fixed test
    // namespace. Hostile same-account modification is not an isolation claim.
    #[derive(serde::Deserialize, serde::Serialize)]
    #[serde(rename_all = "camelCase", deny_unknown_fields)]
    struct LifecycleReceipt {
        version: String,
        nonce: String,
        directories: std::collections::BTreeMap<String, (u64, u64)>,
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
        status_diagnostics: std::sync::Arc<StatusDiagnostics>,
        document_drop: bool,
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
        // List-directory + read attributes; allow reads/writes so Core can
        // publish staged children, but deny delete-sharing to prevent parent
        // rename. Revalidate both held and named objects. These pins do not
        // prevent hostile same-account in-place reparse mutation or guarantee
        // race-free confinement; observed drift must stop fixture consumers.
        std::fs::OpenOptions::new()
            .access_mode(0x81)
            .share_mode(0x3)
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

    fn fixture_python_path(repo: &Path) -> Result<OsString, &'static str> {
        // The disposable sidecar imports both the Core package and its
        // repository-owned document inspector. Production packaging has
        // its own sealed module layout; this path applies only here.
        std::env::join_paths([
            repo.join("tests/service/fixtures"),
            repo.join("services/core-api/src"),
            repo.to_owned(),
            repo.join(".venv/Lib/site-packages"),
        ])
        .map_err(|_| "probe-python-unavailable")
    }

    fn signed_document_probe_environment(
        lookup: impl Fn(&str) -> Option<OsString>,
    ) -> Result<Vec<(OsString, OsString)>, &'static str> {
        let mut selected = Vec::with_capacity(3);
        for name in [
            "RO_W2_SIGNED_WORKER_BUILD",
            "RO_W2_CORE_SIDECAR_GUARDIAN",
            "RO_W2_CORE_SIDECAR_GUARDIAN_SHA256",
        ] {
            let value = lookup(name)
                .filter(|value| !value.is_empty())
                .ok_or("probe-signed-document-input-unavailable")?;
            selected.push((OsString::from(name), value));
        }
        Ok(selected)
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
        pub(crate) fn document_drop_mode(&self) -> bool {
            self.document_drop
        }

        pub(crate) fn document_drop_project(&self) -> Result<String, &'static str> {
            if !self.document_drop {
                return Err("probe-attachment-mode-unavailable");
            }
            self.revalidate()?;
            let project = self.projects.join("document-drop-project");
            validate_directory(&project)?;
            project
                .to_str()
                .map(str::to_owned)
                .ok_or("probe-attachment-project-unavailable")
        }

        fn create_document_drop(nonce: &str) -> Result<Self, &'static str> {
            let mut fixture = Self::create_lifecycle(nonce)?;
            fixture.document_drop = true;
            Ok(fixture)
        }

        fn resume_document_drop(nonce: &str) -> Result<Self, &'static str> {
            let mut fixture = Self::resume_lifecycle(nonce)?;
            fixture.document_drop = true;
            validate_directory(&fixture.projects.join("document-drop-project"))?;
            Ok(fixture)
        }

        pub(crate) fn status_trace(&self, phase: &'static str) -> Option<StatusTrace> {
            let span = self.status_diagnostics.reserve()?;
            let entered = Instant::now();
            emit(json!({"kind":"fixture-lock-status-timing", "span":span,
                "phase":phase, "boundary":"entered", "spanLimit":512,
                "lastAdmittedSpan":span == 512,
                "nativeElapsedMs":self.status_diagnostics.origin.elapsed().as_secs_f64() * 1000.0}));
            Some(StatusTrace {
                diagnostics: self.status_diagnostics.clone(),
                span,
                phase,
                entered,
            })
        }

        fn relative_root(&self) -> String {
            format!(
                "artifacts/tmp/{}",
                self.root.file_name().unwrap().to_string_lossy()
            )
        }

        fn create(nonce: &str) -> Result<Self, &'static str> {
            Self::create_with_policy(nonce, true)
        }

        fn create_lifecycle(nonce: &str) -> Result<Self, &'static str> {
            Self::create_with_policy(nonce, false)
        }

        fn layout(root: PathBuf) -> Self {
            Self {
                application_data: root.join("application-data"),
                projects: root.join("projects"),
                vault: root.join("vault"),
                webview: root.join("webview"),
                temporary: root.join("temporary"),
                root,
                pins: std::sync::Arc::new(Vec::new()),
                status_diagnostics: std::sync::Arc::new(StatusDiagnostics::new()),
                document_drop: false,
            }
        }

        fn directory_identities(&self) -> std::collections::BTreeMap<String, (u64, u64)> {
            self.pins
                .iter()
                .filter_map(|pin| {
                    pin.path.strip_prefix(&self.root).ok().map(|relative| {
                        (relative.to_string_lossy().replace('\\', "/"), pin.identity)
                    })
                })
                .collect()
        }

        fn create_with_policy(nonce: &str, protected: bool) -> Result<Self, &'static str> {
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
            let mut fixture = Self::layout(root);
            for relative in FIXTURE_DIRECTORIES {
                let path = fixture.root.join(relative);
                std::fs::create_dir(&path).map_err(|_| "probe-fixture-create-denied")?;
                pins.push(PinnedDirectory::acquire(path.clone())?);
                validate_directory(&path)?;
            }
            if protected {
                let policy =
                    SignInPolicy::normalized_target(1, SignInMode::WindowsPassword, None, 0)
                        .and_then(|policy| policy.canonical_bytes())?;
                let mut file = std::fs::File::create_new(
                    fixture.application_data.join("security").join(POLICY_FILE),
                )
                .map_err(|_| "probe-policy-create-denied")?;
                file.write_all(&policy)
                    .and_then(|_| file.sync_all())
                    .map_err(|_| "probe-policy-create-denied")?;
            }
            fixture.pins = std::sync::Arc::new(pins);
            fixture.revalidate()?;
            if !protected {
                let receipt = LifecycleReceipt {
                    version: "t04-directory-lifecycle-v1".into(),
                    nonce: nonce.into(),
                    directories: fixture.directory_identities(),
                };
                let bytes = serde_json::to_vec(&receipt).map_err(|_| "probe-receipt-invalid")?;
                let mut file = std::fs::File::create_new(fixture.root.join(LIFECYCLE_RECEIPT))
                    .map_err(|_| "probe-receipt-create-denied")?;
                file.write_all(&bytes)
                    .and_then(|_| file.sync_all())
                    .map_err(|_| "probe-receipt-create-denied")?;
                fixture.revalidate()?;
            }
            Ok(fixture)
        }

        fn resume_lifecycle(nonce: &str) -> Result<Self, &'static str> {
            if !valid_nonce(nonce) {
                return Err("probe-fixture-name-invalid");
            }
            let root = repository()?
                .join("artifacts/tmp")
                .join(format!("directory-dialog-{nonce}"));
            validate_directory(&root)?;
            let mut pins = pin_ancestors(&root)?;
            for relative in FIXTURE_DIRECTORIES {
                let path = root.join(relative);
                validate_directory(&path)?;
                pins.push(PinnedDirectory::acquire(path)?);
            }
            let mut fixture = Self::layout(root);
            fixture.pins = std::sync::Arc::new(pins);
            let file = std::fs::OpenOptions::new()
                .read(true)
                .share_mode(0x1)
                .custom_flags(0x00200000)
                .open(fixture.root.join(LIFECYCLE_RECEIPT))
                .map_err(|_| "probe-receipt-unavailable")?;
            let mut information = BY_HANDLE_FILE_INFORMATION::default();
            if unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut information) } == 0
                || information.dwFileAttributes & (0x10 | 0x400) != 0
                || information.nNumberOfLinks != 1
                || information.nFileSizeHigh != 0
                || information.nFileSizeLow > 4096
            {
                return Err("probe-receipt-invalid");
            }
            let mut bytes = Vec::new();
            (&file)
                .take(4097)
                .read_to_end(&mut bytes)
                .map_err(|_| "probe-receipt-unavailable")?;
            let receipt: LifecycleReceipt =
                serde_json::from_slice(&bytes).map_err(|_| "probe-receipt-invalid")?;
            if receipt.version != "t04-directory-lifecycle-v1"
                || receipt.nonce != nonce
                || receipt.directories != fixture.directory_identities()
            {
                return Err("probe-receipt-identity-mismatch");
            }
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
                && matches!(
                    request.path.as_str(),
                    "/workflow-profiles/catalog" | "/projects/connectors/capabilities"
                )
                && request.body.is_none()
                && request.if_match.is_none()
                && request.idempotency_key.is_none()
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
            let python_path = fixture_python_path(&repo)?;
            let mut environment = vec![
                ("PYTHONPATH".into(), python_path),
                ("PYTHONDONTWRITEBYTECODE".into(), "1".into()),
                ("TEMP".into(), self.temporary.as_os_str().to_owned()),
                ("TMP".into(), self.temporary.as_os_str().to_owned()),
            ];
            if self.document_drop {
                environment.extend(signed_document_probe_environment(|name| {
                    std::env::var_os(name)
                })?);
            }
            SupervisorConfig::for_integration_harness(
                PathBuf::from(executable.trim()),
                self.root.clone(),
                vec![
                    "-m".into(),
                    "native_integration_sidecar".into(),
                    "--profile-vault-root".into(),
                    self.vault.as_os_str().to_owned(),
                ],
                environment,
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
                    Mode::Selection
                    | Mode::Lifecycle
                    | Mode::LifecycleResume
                    | Mode::DocumentDrop
                    | Mode::DocumentDropFive
                    | Mode::DocumentDropResume => {}
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

    /// Read-only packaging observation: no normal setup, policy, vault, Core,
    /// WebView, or renderer is started. Release runtime_config has no fallback.
    pub fn observe_tauri_resource_root() -> Result<Value, &'static str> {
        let mut context = tauri::generate_context!();
        for window in &mut context.config_mut().app.windows {
            window.create = false;
        }
        let app = tauri::Builder::default()
            .build(context)
            .map_err(|_| "probe-resource-context-unavailable")?;
        let resource_root = app
            .path()
            .resource_dir()
            .map_err(|_| "probe-resource-directory-unavailable")?;
        let executable = std::env::current_exe().map_err(|_| "probe-executable-unavailable")?;
        let at_executable = executable.parent().is_some_and(|parent| {
            matches!(
                (dunce::canonicalize(parent), dunce::canonicalize(&resource_root)),
                (Ok(parent), Ok(resource)) if parent == resource
            )
        });
        let resource_config = SupervisorConfig::from_resource_root(&resource_root);
        let runtime = runtime_config(&app);
        Ok(json!({
            "kind":"actual-tauri-resource-resolution", "debugAssertions":cfg!(debug_assertions),
            "resourceDirectoryMatchesExecutableParent":at_executable,
            "resourceRootConstructorAccepted":resource_config.is_ok(),
            "runtimeConfigAccepted":runtime.is_ok(), "runtimeConfigError":runtime.err(),
            "normalSetupInvoked":false, "coreStarted":false, "readOnly":true,
            "scope":"actual-tauri-resource-resolution-not-production-runtime-qualification"
        }))
    }

    pub fn run(mode: Mode, nonce: &OsStr) -> Result<(), &'static str> {
        validate_environment(std::env::vars_os().map(|(name, _)| name))?;
        let nonce = nonce.to_str().ok_or("probe-fixture-name-invalid")?;
        let fixture = match mode {
            Mode::Lifecycle => Fixture::create_lifecycle(nonce)?,
            Mode::LifecycleResume => Fixture::resume_lifecycle(nonce)?,
            Mode::DocumentDrop | Mode::DocumentDropFive => Fixture::create_document_drop(nonce)?,
            Mode::DocumentDropResume => Fixture::resume_document_drop(nonce)?,
            _ => Fixture::create(nonce)?,
        };
        let drop_seed = match mode {
            Mode::DocumentDrop | Mode::DocumentDropFive => {
                let seed = seed_document_drop(&fixture)?;
                write_document_receipt(&fixture, DOCUMENT_DROP_SEED_RECEIPT, &seed)?;
                Some(seed)
            }
            Mode::DocumentDropResume => {
                let seed: DocumentDropSeed =
                    read_document_receipt(&fixture, DOCUMENT_DROP_SEED_RECEIPT)?;
                validate_document_drop_seed(&fixture, &seed)?;
                let commit: DocumentDropCommitReceipt =
                    read_document_receipt(&fixture, DOCUMENT_DROP_COMMIT_RECEIPT)?;
                if !commit.valid_for(&seed) {
                    return Err("probe-attachment-receipt-invalid");
                }
                Some(seed)
            }
            _ => None,
        };
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
            eprintln!("RO-DOCUMENT-SETUP phase=runtime-start");
            setup_runtime(app, Ok(config), &fixture.application_data, DirectoryPickerManager::for_fixture(fixture.projects.clone()))?;
            eprintln!("RO-DOCUMENT-SETUP phase=runtime-ready");
            // A WindowConfig absolute data_directory is ignored by Tauri;
            // the direct builder API is the actual WebView storage boundary.
            fixture.revalidate().map_err(|error| {
                app.state::<RuntimeSupervisor>().stop();
                std::io::Error::other(error)
            })?;
            eprintln!("RO-DOCUMENT-SETUP phase=webview-start");
            let main = tauri::WebviewWindowBuilder::from_config(app, &window_config)
                .and_then(|builder| {
                    let builder = builder.data_directory(fixture.webview.clone())
                        .initialization_script(LOCK_STATUS_DIAGNOSTIC_SCRIPT)
                        .visible(false).drag_and_drop(false).disable_drag_drop_handler();
                    let builder = if let Some(seed) = &drop_seed {
                        builder.initialization_script(document_drop_ui_script(seed, mode == Mode::DocumentDropFive))
                    } else { builder };
                    builder.title(format!("Research Observatory — SYNTHETIC {} {}",
                        if mode.is_lifecycle() { "T04" } else if mode.is_document_attachment() { "T01" } else { "T03" },
                        if mode == Mode::DocumentDropFive { "document-drop" } else { mode.name() })).build()
                })
                .inspect_err(|_| { app.state::<RuntimeSupervisor>().stop(); })?;
            eprintln!("RO-DOCUMENT-SETUP phase=webview-ready");
            main_menu::install(&main).and_then(|()| install_menu_diagnostics(&main, &fixture)).map_err(|error| {
                app.state::<RuntimeSupervisor>().stop();
                std::io::Error::other(error)
            })?;
            eprintln!("RO-DOCUMENT-SETUP phase=drop-install-start");
            let attachments = app.state::<document_attachment::DocumentAttachmentManager>().inner().clone();
            document_drop::install(&main, &attachments).map_err(std::io::Error::other)?;
            eprintln!("RO-DOCUMENT-SETUP phase=drop-install-ready");
            // Explicit warm-up fixture exposes no attachment admission before
            // its guarded hidden five-node reinstallation.
            attachments.set_installed(mode != Mode::DocumentDropFive);
            let drop_event_counts = mode.is_document_attachment().then(|| listen_for_tauri_drag(&main));
            let picker_pending = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
            if mode.is_document_attachment() {
                listen_for_document_stage(&main, std::sync::Arc::clone(&picker_pending));
            }
            main.show()?;
            emit(json!({"kind":"tauri-directory-start", "mode":mode.name(), "fixture":fixture.relative_root(),
                "ownerHwnd":main.hwnd().ok().map(|handle| handle.0 as isize),
                "fixtureSubstitutions":["policy-root", "Core-vault", "WebView-data-directory", "Core-temp", "default-project-parent"],
                "scope":"actual-renderer-tauri-ipc-lock-and-close-with-fixture-storage",
                "credentialsInvoked":false, "productionPackagedQualification":false,
                "projects":format!("{}/projects", fixture.relative_root()), "fixturesRetained":true}));
            if mode == Mode::DocumentDropFive {
                observe_five_node_install(app.handle().clone(), fixture.clone(), drop_seed.clone().expect("drop seed"),
                    drop_event_counts.expect("drop event counters"), picker_pending);
            } else if mode == Mode::DocumentDrop {
                observe_document_drop(app.handle().clone(), drop_seed.clone().expect("drop seed"),
                    drop_event_counts.expect("drop event counters"), picker_pending);
            } else if mode == Mode::DocumentDropResume {
                observe_document_resume(app.handle().clone(), fixture.clone(),
                    drop_seed.clone().expect("drop seed"));
            } else if mode.is_lifecycle() {
                emit(json!({"kind":"tauri-lifecycle-ready", "mode":mode.name(),
                    "signInMode":app.state::<ApplicationLockManager>().status().sign_in_mode,
                    "resumedOriginalFixture":mode == Mode::LifecycleResume,
                    "scope":"actual-runtime-with-fixture-storage-no-ordinary-profile-access"}));
            } else {
                observe_pending(app.handle().clone(), mode);
            }
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
        if mode.is_document_attachment() {
            emit(
                json!({"kind":"document-drop-probe-end","exitCode":exit_code,
                "native":crate::document_drop::counts(),"fixturesRetained":true}),
            );
        }
        if exit_code == 0 {
            Ok(())
        } else {
            Err("probe-tauri-runtime-failed")
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use crate::application_lock::ApplicationLockState;
        use crate::application_sign_in_policy::secure_random_hex;

        fn nonce() -> String {
            format!("unit-{}", secure_random_hex::<16>().unwrap())
        }

        #[test]
        fn document_resume_receipt_requires_exact_seed_and_committed_ids() {
            let seed = DocumentDropSeed {
                schema_version: "1.0".into(),
                project_id: "01900000-0000-7000-8000-000000000001".into(),
                work_id: "01900000-0000-7000-8000-000000000002".into(),
                work_revision_id: "01900000-0000-7000-8000-000000000003".into(),
                version_id: "01900000-0000-7000-8000-000000000004".into(),
                version_revision_id: "01900000-0000-7000-8000-000000000005".into(),
                source_assertion_revision_id: "01900000-0000-7000-8000-000000000006".into(),
                synthetic_source_sha256: "a".repeat(64),
                protected_database: true,
            };
            let receipt = DocumentDropCommitReceipt {
                schema_version: "1.0".into(),
                selection: DocumentDropSelection::from(&seed),
                operation_id: "01900000-0000-7000-8000-000000000007".into(),
                command_id: "01900000-0000-7000-8000-000000000008".into(),
                candidate_id: "01900000-0000-7000-8000-000000000009".into(),
                attachment_id: "01900000-0000-7000-8000-000000000010".into(),
                document_revision_id: "01900000-0000-7000-8000-000000000011".into(),
            };
            assert!(receipt.valid_for(&seed));
            let mut changed = receipt.clone();
            changed.selection.version_revision_id = "01900000-0000-7000-8000-000000000012".into();
            assert!(!changed.valid_for(&seed));
            let mut invalid = receipt;
            invalid.command_id = "not-a-command-id".into();
            assert!(!invalid.valid_for(&seed));
        }

        #[test]
        fn document_commit_probe_binds_native_reply_to_v4_project_seed() {
            let fixture = Fixture::create_document_drop(&nonce()).unwrap();
            std::fs::create_dir(fixture.projects.join("document-drop-project")).unwrap();
            let seed = DocumentDropSeed {
                schema_version: "1.0".into(),
                project_id: "20df2f61-0d04-4439-8a66-b7b6afb36ee5".into(),
                work_id: "01900000-0000-7000-8000-000000000002".into(),
                work_revision_id: "01900000-0000-7000-8000-000000000003".into(),
                version_id: "01900000-0000-7000-8000-000000000004".into(),
                version_revision_id: "01900000-0000-7000-8000-000000000005".into(),
                source_assertion_revision_id: "01900000-0000-7000-8000-000000000006".into(),
                synthetic_source_sha256: "a".repeat(64),
                protected_database: true,
            };
            write_document_receipt(&fixture, DOCUMENT_DROP_SEED_RECEIPT, &seed).unwrap();
            let selection = serde_json::to_value(DocumentDropSelection::from(&seed)).unwrap();
            let request = json!({"schemaVersion":"1.0",
                "operationId":"01900000-0000-7000-8000-000000000007",
                "sessionId":"a".repeat(32),
                "candidateId":"01900000-0000-7000-8000-000000000008",
                "confirmationSha256":"b".repeat(64),
                "commandId":"01900000-0000-7000-8000-000000000009",
                "selection":selection,"matchConfirmed":true,"permittedUse":"project-only"});
            let request = serde_json::to_value(
                serde_json::from_value::<crate::document_attachment::CommitRequest>(request)
                    .unwrap(),
            )
            .unwrap();
            let mut result = json!({"schemaVersion":"1.0","status":"attached",
                "operationId":request["operationId"],"sessionId":request["sessionId"],
                "candidateId":request["candidateId"],"selection":request["selection"],
                "attachmentId":"01900000-0000-7000-8000-000000000010",
                "documentRevisionId":"01900000-0000-7000-8000-000000000011"});
            let receipt = commit_receipt_from_native(&fixture, &request, &result).unwrap();
            assert!(receipt.valid_for(&seed));
            result["selection"]["workId"] = "01900000-0000-7000-8000-000000000012".into();
            assert_eq!(
                commit_receipt_from_native(&fixture, &request, &result).err(),
                Some("selection-binding")
            );
            result["selection"] = request["selection"].clone();
            result["attachmentId"] = "not-a-uuid".into();
            assert_eq!(
                commit_receipt_from_native(&fixture, &request, &result).err(),
                Some("receipt-id-format")
            );
        }

        #[test]
        fn disposable_sidecar_can_import_core_document_worker_from_fixture_root() {
            let fixture = Fixture::create(&nonce()).unwrap();
            let repo = repository().unwrap();
            let base = std::process::Command::new(repo.join(".venv/Scripts/python.exe"))
                .args(["-I", "-c", "import sys; print(sys._base_executable)"])
                .creation_flags(0x08000000)
                .output()
                .unwrap();
            assert!(base.status.success(), "fixture Python base unavailable");
            let executable = String::from_utf8(base.stdout).unwrap();
            let imported = std::process::Command::new(executable.trim())
                .args([
                    "-c",
                    "import native_integration_sidecar; import research_observatory_core.document_attachment_api; import workers.document.inspection",
                ])
                .current_dir(&fixture.root)
                .env("PYTHONPATH", fixture_python_path(&repo).unwrap())
                .env("PYTHONDONTWRITEBYTECODE", "1")
                .creation_flags(0x08000000)
                .output()
                .unwrap();
            assert!(
                imported.status.success(),
                "disposable Core document import failed"
            );
        }

        #[test]
        fn document_probe_forwards_only_complete_explicit_signed_inputs() {
            assert_eq!(
                signed_document_probe_environment(|_| None).unwrap_err(),
                "probe-signed-document-input-unavailable"
            );
            let selected = signed_document_probe_environment(|name| match name {
                "RO_W2_SIGNED_WORKER_BUILD" => Some(OsString::from("worker")),
                "RO_W2_CORE_SIDECAR_GUARDIAN" => Some(OsString::from("guardian")),
                "RO_W2_CORE_SIDECAR_GUARDIAN_SHA256" => Some(OsString::from("digest")),
                _ => None,
            })
            .unwrap();
            assert_eq!(selected.len(), 3);
            assert_eq!(selected[0].0, "RO_W2_SIGNED_WORKER_BUILD");
            assert_eq!(selected[1].0, "RO_W2_CORE_SIDECAR_GUARDIAN");
            assert_eq!(selected[2].0, "RO_W2_CORE_SIDECAR_GUARDIAN_SHA256");
        }

        #[test]
        fn document_stage_diagnostics_emit_only_fixed_status_and_opaque_ids() {
            let operation = "01900000-0000-7000-8000-000000000008";
            let candidate = "01900000-0000-7000-8000-000000000009";
            let raw = json!({"status":"candidate","operationId":operation,
                "candidate":{"candidateId":candidate,"sourceName":"private-file-name.txt",
                    "byteLength":123,"confirmationSha256":"a".repeat(64)},
                "selection":{"root":"C:/private/project"}})
            .to_string();
            let safe = safe_document_stage_probe_event(&raw).unwrap();
            assert_eq!(safe["operationId"], operation);
            assert_eq!(safe["candidateId"], candidate);
            assert!(!safe.to_string().contains("private"));
            assert!(safe_document_stage_probe_event("{\"status\":\"candidate\"}").is_none());

            let finish = safe_document_stage_finish(
                operation,
                "rejected",
                Some("worker-unavailable"),
                None,
                true,
                false,
                Some("RO-DOCUMENT-SESSION-UNAVAILABLE"),
            )
            .unwrap();
            assert_eq!(finish["deliveryCode"], "session-denied");
            assert_eq!(finish["eventEmitSucceeded"], false);
            assert_eq!(finish["code"], "worker-unavailable");
            assert!(!finish.to_string().contains("private"));
        }

        #[test]
        fn document_transport_milestones_reject_arbitrary_content() {
            let normal = safe_document_transport_phase("header-sent", None).unwrap();
            assert_eq!(normal["phase"], "header-sent");
            assert!(normal["code"].is_null());
            assert!(safe_document_transport_phase("C:/private/file.txt", None).is_none());
            let denied =
                safe_document_transport_phase("transport-error", Some("C:/private/file.txt"))
                    .unwrap();
            assert_eq!(denied["code"], "other");
            assert!(!denied.to_string().contains("private"));
            let parse =
                safe_document_transport_phase("response-parse-error", Some("trace-missing"))
                    .unwrap();
            assert_eq!(parse["code"], "trace-missing");
            assert!(
                safe_document_transport_phase("response-parse-error", Some("C:/private/file.txt"),)
                    .is_none()
            );
            assert_eq!(
                safe_document_transport_phase(
                    "transport-error",
                    Some("RO-CORE-API-RESPONSE-INVALID"),
                )
                .unwrap()["code"],
                "http-invalid"
            );
        }

        #[test]
        fn document_drop_decision_cannot_emit_source_identity_or_arbitrary_reason() {
            let denied =
                safe_document_drop_decision("cache-expired", "expired-short", true).unwrap();
            assert_eq!(denied["reason"], "cache-expired");
            assert_eq!(denied["cacheAge"], "expired-short");
            assert_eq!(denied["probePending"], true);
            assert!(
                safe_document_drop_decision("C:/private/document.txt", "fresh", false).is_none()
            );
            assert!(safe_document_drop_decision("source-open", "C:/private", false).is_none());
        }

        #[test]
        fn status_diagnostic_budget_saturates_without_fixture_io() {
            let diagnostics = StatusDiagnostics::new();
            for expected in 1..=512 {
                assert_eq!(diagnostics.reserve(), Some(expected));
            }
            assert_eq!(diagnostics.reserve(), None);
            assert_eq!(diagnostics.reserve(), None);
            assert_eq!(
                diagnostics.spans.load(std::sync::atomic::Ordering::Relaxed),
                512
            );
        }

        #[test]
        fn menu_diagnostics_select_only_menu_messages_without_recording_key_content() {
            use windows_sys::Win32::UI::WindowsAndMessaging::*;
            assert_eq!(
                menu_message(WM_SYSCOMMAND, SC_KEYMENU as usize, 32),
                Some([WM_SYSCOMMAND, 1])
            );
            assert_eq!(
                menu_message(WM_SYSCOMMAND, (SC_KEYMENU | 15) as usize, 65),
                Some([WM_SYSCOMMAND, 0])
            );
            assert_eq!(
                menu_message(WM_ENTERMENULOOP, 1, 999),
                Some([WM_ENTERMENULOOP, 1])
            );
            assert_eq!(
                menu_message(WM_EXITMENULOOP, 0, 999),
                Some([WM_EXITMENULOOP, 0])
            );
            for message in [WM_KEYDOWN, WM_SYSKEYDOWN, WM_CHAR, WM_NCDESTROY, WM_NULL] {
                assert_eq!(menu_message(message, SC_KEYMENU as usize, 32), None);
            }
            assert_eq!(menu_message(WM_SYSCOMMAND, SC_CLOSE as usize, 32), None);
            assert_eq!(
                menu_message(main_menu::REPLAY_MESSAGE, SC_KEYMENU as usize | 15, 32),
                Some([main_menu::REPLAY_MESSAGE, 1])
            );
            assert_eq!(
                menu_message(main_menu::REPLAY_MESSAGE, SC_KEYMENU as usize | 0x10000, 32),
                None
            );
            assert_eq!(menu_message(main_menu::REPLAY_MESSAGE, 1, 0), None);
        }

        #[test]
        fn menu_diagnostics_require_same_nonzero_process_and_thread() {
            assert!(menu_owner_matches(11, 22, 11, 22));
            assert!(!menu_owner_matches(12, 22, 11, 22));
            assert!(!menu_owner_matches(11, 23, 11, 22));
            assert!(!menu_owner_matches(0, 22, 0, 22));
            assert!(!menu_owner_matches(11, 0, 11, 0));
        }

        #[test]
        fn menu_diagnostics_forward_once_and_preserve_result_even_after_budget() {
            use std::cell::Cell;
            let diagnostics = MenuDiagnostics::new(std::sync::Arc::new(StatusDiagnostics::new()));
            let forwarded = Cell::new(0);
            let states = Cell::new(0);
            let mut rows = Vec::new();
            let mut forward = || {
                forwarded.set(forwarded.get() + 1);
                -73
            };
            let mut flags = || {
                states.set(states.get() + 1);
                states.get()
            };
            assert_eq!(
                diagnostics.observe(None, &mut flags, &mut forward, |row| rows.push(row)),
                -73
            );
            assert_eq!(forwarded.get(), 1);
            assert_eq!(states.get(), 0);
            assert!(rows.is_empty());
            for _ in 0..129 {
                assert_eq!(
                    diagnostics.observe(Some([0x112, 1]), &mut flags, &mut forward, |row| rows
                        .push(row)),
                    -73
                );
            }
            assert_eq!(forwarded.get(), 130);
            assert_eq!(states.get(), 256);
            assert_eq!(rows.len(), 256);
            assert_eq!(rows[0]["phase"], 0);
            assert_eq!(rows[1]["phase"], 1);
            assert_eq!(rows[0]["sendState"], 1);
            assert_eq!(rows[1]["sendState"], 2);
            assert_eq!(rows[254]["span"], 128);
            assert_eq!(rows[254]["lastAdmittedSpan"], true);
            assert_eq!(
                diagnostics
                    .clock
                    .spans
                    .load(std::sync::atomic::Ordering::Relaxed),
                0
            );
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
            assert!(
                before_run.find("main_menu::install(&main)").unwrap()
                    < before_run.find("install_menu_diagnostics(&main").unwrap()
            );
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
        fn fixture_allows_only_fixed_read_only_source_capability_route() {
            let fixture = Fixture::create(&nonce()).unwrap();
            let mut request = CoreApiRequest {
                method: "GET".into(),
                path: "/projects/connectors/capabilities".into(),
                body: None,
                if_match: None,
                idempotency_key: None,
            };
            assert!(fixture.permits_request(&request));
            request.path.push_str("?root=C:/outside");
            assert!(!fixture.permits_request(&request));
            request.path = "/projects/connectors/capabilities".into();
            request.body = Some("{}".into());
            assert!(!fixture.permits_request(&request));
            request.body = None;
            request.method = "POST".into();
            assert!(!fixture.permits_request(&request));
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
        fn fixture_pins_allow_core_style_staged_child_publication() {
            let fixture = Fixture::create(&nonce()).unwrap();
            let staging = fixture.projects.join("synthetic-staging");
            let published = fixture.projects.join("synthetic-published");
            std::fs::create_dir(&staging).unwrap();
            std::fs::write(staging.join("marker"), b"synthetic staged payload").unwrap();
            std::fs::rename(&staging, &published)
                .expect("fixture pins must permit Core's staged-child publication");
            fixture.revalidate().unwrap();
            assert_eq!(
                std::fs::read(published.join("marker")).unwrap(),
                b"synthetic staged payload"
            );
            assert!(!staging.exists());
        }

        #[test]
        fn lifecycle_starts_without_policy_and_resumes_only_original_fixture() {
            let name = nonce();
            let fixture = Fixture::create_lifecycle(&name).unwrap();
            let policy = fixture.application_data.join("security").join(POLICY_FILE);
            assert!(
                !policy.exists(),
                "lifecycle must exercise actual default policy"
            );
            let manager = ApplicationLockManager::acquire(&fixture.application_data).unwrap();
            assert_eq!(manager.status().sign_in_mode, SignInMode::None);
            assert_eq!(manager.status().state, ApplicationLockState::Unlocked);
            let identities = fixture.directory_identities();
            let child = fixture.projects.join("synthetic-project");
            std::fs::create_dir(&child).unwrap();
            std::fs::write(child.join("marker"), b"retained synthetic project").unwrap();
            drop(manager);
            drop(fixture);
            assert!(matches!(
                Fixture::create(&name),
                Err("probe-fixture-create-denied")
            ));
            let resumed = Fixture::resume_lifecycle(&name).unwrap();
            assert_eq!(resumed.directory_identities(), identities);
            assert_eq!(
                std::fs::read(child.join("marker")).unwrap(),
                b"retained synthetic project"
            );
            let manager = ApplicationLockManager::acquire(&resumed.application_data).unwrap();
            assert_eq!(manager.status().sign_in_mode, SignInMode::None);
            assert_eq!(manager.status().state, ApplicationLockState::Unlocked);
            resumed.revalidate().unwrap();
        }

        #[test]
        fn lifecycle_resume_denies_unowned_missing_and_path_inputs() {
            for invalid in ["", "..", "../outside", "C:\\outside", "nested/name"] {
                assert!(matches!(
                    Fixture::resume_lifecycle(invalid),
                    Err("probe-fixture-name-invalid")
                ));
            }
            let absent = nonce();
            assert!(Fixture::resume_lifecycle(&absent).is_err());
            assert!(
                !repository()
                    .unwrap()
                    .join("artifacts/tmp")
                    .join(format!("directory-dialog-{absent}"))
                    .exists()
            );
            let name = nonce();
            let protected = Fixture::create(&name).unwrap();
            let policy = protected
                .application_data
                .join("security")
                .join(POLICY_FILE);
            let before = std::fs::read(&policy).unwrap();
            assert!(matches!(
                Fixture::resume_lifecycle(&name),
                Err("probe-receipt-unavailable")
            ));
            assert_eq!(std::fs::read(policy).unwrap(), before);
        }

        #[test]
        fn lifecycle_resume_rejects_receipt_changes_and_directory_replacement() {
            let name = nonce();
            let fixture = Fixture::create_lifecycle(&name).unwrap();
            let receipt_path = fixture.root.join(LIFECYCLE_RECEIPT);
            let original = std::fs::read(&receipt_path).unwrap();
            for field in ["nonce", "version", "unknown"] {
                let mut changed: Value = serde_json::from_slice(&original).unwrap();
                changed[field] = json!("not-the-original-fixture");
                std::fs::write(&receipt_path, serde_json::to_vec(&changed).unwrap()).unwrap();
                assert!(Fixture::resume_lifecycle(&name).is_err());
            }
            std::fs::write(&receipt_path, &original).unwrap();
            let vault = fixture.vault.clone();
            let moved = fixture.root.join("retained-original-vault");
            drop(fixture);
            std::fs::rename(&vault, &moved).unwrap();
            std::fs::create_dir(&vault).unwrap();
            assert!(matches!(
                Fixture::resume_lifecycle(&name),
                Err("probe-receipt-identity-mismatch")
            ));
            assert!(moved.is_dir());
            assert_eq!(std::fs::read(receipt_path).unwrap(), original);
        }

        #[test]
        fn lifecycle_resume_rejects_oversized_and_hardlinked_receipts() {
            let name = nonce();
            let fixture = Fixture::create_lifecycle(&name).unwrap();
            let receipt = fixture.root.join(LIFECYCLE_RECEIPT);
            let original = std::fs::read(&receipt).unwrap();
            std::fs::write(&receipt, vec![b' '; 4097]).unwrap();
            assert!(matches!(
                Fixture::resume_lifecycle(&name),
                Err("probe-receipt-invalid")
            ));
            std::fs::write(&receipt, original).unwrap();
            std::fs::hard_link(&receipt, fixture.root.join("receipt-hardlink")).unwrap();
            assert!(matches!(
                Fixture::resume_lifecycle(&name),
                Err("probe-receipt-invalid")
            ));
        }

        #[test]
        fn fixture_detects_same_account_in_place_reparse_mutation() {
            use std::os::windows::ffi::OsStrExt;
            #[link(name = "kernel32")]
            unsafe extern "system" {
                fn DeviceIoControl(
                    device: *mut std::ffi::c_void,
                    code: u32,
                    input: *const std::ffi::c_void,
                    input_length: u32,
                    output: *mut std::ffi::c_void,
                    output_length: u32,
                    returned: *mut u32,
                    overlapped: *mut std::ffi::c_void,
                ) -> i32;
            }
            let fixture = Fixture::create_lifecycle(&nonce()).unwrap();
            let target = fixture.root.join("synthetic-reparse-target");
            std::fs::create_dir(&target).unwrap();
            let printable: Vec<u16> = target.as_os_str().encode_wide().collect();
            let substitute: Vec<u16> = OsString::from(format!("\\??\\{}", target.display()))
                .encode_wide()
                .collect();
            let mut payload = Vec::new();
            payload.extend(0xA0000003u32.to_le_bytes());
            for value in [
                8 + substitute.len() * 2 + 2 + printable.len() * 2 + 2,
                0,
                0,
                substitute.len() * 2,
                substitute.len() * 2 + 2,
                printable.len() * 2,
            ] {
                payload.extend(u16::try_from(value).unwrap().to_le_bytes());
            }
            for value in substitute
                .into_iter()
                .chain([0])
                .chain(printable)
                .chain([0])
            {
                payload.extend(value.to_le_bytes());
            }
            let handle = std::fs::OpenOptions::new()
                .access_mode(0x40000000)
                .share_mode(0x7)
                .custom_flags(0x02200000)
                .open(&fixture.vault)
                .unwrap();
            let mut returned = 0;
            assert_ne!(
                unsafe {
                    DeviceIoControl(
                        handle.as_raw_handle(),
                        0x000900A4,
                        payload.as_ptr().cast(),
                        payload.len().try_into().unwrap(),
                        std::ptr::null_mut(),
                        0,
                        &mut returned,
                        std::ptr::null_mut(),
                    )
                },
                0,
                "characterize real same-account mutation without claiming isolation"
            );
            assert_eq!(fixture.revalidate(), Err("probe-fixture-identity-invalid"));
            let request = CoreApiRequest {
                method: "GET".into(),
                path: "/workflow-profiles/catalog".into(),
                body: None,
                if_match: None,
                idempotency_key: None,
            };
            assert!(!fixture.permits_request(&request));
            assert!(target.is_dir());
        }

        #[test]
        fn resource_probe_has_no_normal_setup_or_runtime_launch() {
            let source = include_str!("lib.rs");
            let probe = source
                .split_once("pub fn observe_tauri_resource_root()")
                .unwrap()
                .1
                .split_once("pub fn run(mode: Mode")
                .unwrap()
                .0;
            assert!(probe.contains("window.create = false"));
            assert!(probe.contains("runtime_config(&app)"));
            assert!(probe.contains(".resource_dir()"));
            for forbidden in [
                "setup_runtime(",
                "application_builder(",
                "ApplicationLockManager::",
                "RuntimeSupervisor::",
                "run_return(",
                "app_local_data_dir(",
            ] {
                assert!(!probe.contains(forbidden));
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
            if lock.is_terminal() {
                break;
            }
            if let Some(snapshot) = lock.lock_if_idle() {
                #[cfg(windows)]
                app.state::<document_attachment::DocumentAttachmentManager>()
                    .cancel_all();
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
    fn status_diagnostics_are_fixture_only_without_new_ipc_or_workers() {
        let source = include_str!("lib.rs");
        let status = source
            .split_once("fn application_lock_status(")
            .unwrap()
            .1
            .split_once("#[tauri::command]")
            .unwrap()
            .0;
        assert!(status.contains("try_state::<directory_integration_harness::Fixture>()"));
        assert!(status.contains("lock.status()"));
        assert!(status.contains("#[cfg(all(feature = \"integration-harness\", windows))]"));
        assert!(!status.contains("spawn"));
        let harness = source
            .split_once("pub mod directory_integration_harness {")
            .unwrap()
            .1
            .split_once("#[cfg(test)]")
            .unwrap()
            .0;
        assert!(harness.contains(".initialization_script(LOCK_STATUS_DIAGNOSTIC_SCRIPT)"));
        let script = harness
            .split_once("const LOCK_STATUS_DIAGNOSTIC_SCRIPT: &str = r#\"")
            .unwrap()
            .1
            .split_once("\"#;")
            .unwrap()
            .0;
        for forbidden in [
            "setInterval",
            "setTimeout",
            "console.",
            "headers",
            "payload",
            "localStorage",
            "sessionStorage",
            "eval(",
            "__TAURI_INTERNALS__.invoke =",
        ] {
            assert!(
                !script.contains(forbidden),
                "unexpected diagnostic access: {forbidden}"
            );
        }
        assert!(script.contains("return pending;"));
        assert!(script.contains("data-application-locked"));
        assert!(script.contains("rows.length > 96"));
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
        assert!(
            production.find("main_menu::install(").unwrap()
                < production.find("app_local_data_dir()").unwrap()
        );
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
        ] {
            assert!(!directory_origin_allowed(
                "main",
                &tauri::Url::parse(url).unwrap()
            ));
        }
    }

    #[test]
    fn userinfo_alone_denies_the_otherwise_allowed_directory_origin() {
        let mut url = tauri::Url::parse("https://tauri.localhost").unwrap();
        assert!(directory_origin_allowed("main", &url));
        url.set_username("user").unwrap();
        assert_eq!(url.scheme(), "https");
        assert_eq!(url.host_str(), Some("tauri.localhost"));
        assert_eq!(url.port(), None);
        assert_eq!(url.password(), None);
        assert_eq!(url.username(), "user");
        assert!(!directory_origin_allowed("main", &url));
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
