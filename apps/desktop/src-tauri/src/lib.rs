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
    }

    impl Mode {
        pub fn parse(value: &str) -> Option<Self> {
            match value {
                "selection" => Some(Self::Selection),
                "manual-lock" => Some(Self::ManualLock),
                "main-close" => Some(Self::MainClose),
                "lifecycle" => Some(Self::Lifecycle),
                "lifecycle-resume" => Some(Self::LifecycleResume),
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
            }
        }

        fn is_lifecycle(self) -> bool {
            matches!(self, Self::Lifecycle | Self::LifecycleResume)
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
                    Mode::Selection | Mode::Lifecycle | Mode::LifecycleResume => {}
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
            _ => Fixture::create(nonce)?,
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
                .initialization_script(LOCK_STATUS_DIAGNOSTIC_SCRIPT)
                .title(format!("Research Observatory — SYNTHETIC {} {}", if mode.is_lifecycle() { "T04" } else { "T03" }, mode.name())).build())
                .inspect_err(|_| { app.state::<RuntimeSupervisor>().stop(); })?;
            emit(json!({"kind":"tauri-directory-start", "mode":mode.name(), "fixture":fixture.relative_root(),
                "ownerHwnd":main.hwnd().ok().map(|handle| handle.0 as isize),
                "fixtureSubstitutions":["policy-root", "Core-vault", "WebView-data-directory", "Core-temp", "default-project-parent"],
                "scope":"actual-renderer-tauri-ipc-lock-and-close-with-fixture-storage",
                "credentialsInvoked":false, "productionPackagedQualification":false,
                "projects":format!("{}/projects", fixture.relative_root()), "fixturesRetained":true}));
            if mode.is_lifecycle() {
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
    fn status_diagnostics_are_fixture_only_without_new_ipc_or_scheduling() {
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
