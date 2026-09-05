//! Purpose-limited Windows folder selection; selection never opens or creates a project.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "kebab-case")]
pub enum DirectoryPurpose {
    CreateParent,
    OpenProject,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct DirectoryRequest {
    pub purpose: DirectoryPurpose,
    #[serde(default, deserialize_with = "present_string")]
    pub previous_location: Option<String>,
}

fn present_string<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> Result<Option<String>, D::Error> {
    String::deserialize(deserializer).map(Some)
}

#[derive(Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "status", rename_all = "kebab-case")]
pub enum DirectoryOutcome {
    Selected { path: String },
    Cancelled,
    Unavailable,
    Failed,
}

#[derive(Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "status", rename_all = "kebab-case")]
pub enum DefaultParentOutcome {
    Available { path: String },
    Unavailable,
    Failed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum PathFailure {
    Invalid,
    Unavailable,
}

fn validate_existing_directory(
    value: &str,
    installation_roots: &[PathBuf],
) -> Result<PathBuf, PathFailure> {
    if !local_path_syntax(value) {
        return Err(PathFailure::Invalid);
    }
    let path = PathBuf::from(value);
    if installation_roots
        .iter()
        .any(|root| path_inside(&path, root))
    {
        return Err(PathFailure::Invalid);
    }
    #[cfg(windows)]
    if !native::local_drive(&value[..3].replace('/', "\\")) {
        return Err(PathFailure::Invalid);
    }
    let mut current = PathBuf::new();
    for component in path.components() {
        current.push(component);
        // A disk prefix is not an absolute directory until its root separator.
        if !current.is_absolute() {
            continue;
        }
        let metadata = std::fs::symlink_metadata(&current).map_err(|_| PathFailure::Unavailable)?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() || is_reparse(&metadata) {
            return Err(PathFailure::Invalid);
        }
    }
    let canonical = dunce::canonicalize(&path).map_err(|_| PathFailure::Unavailable)?;
    if !same_path(&canonical, &path) {
        return Err(PathFailure::Invalid);
    }
    Ok(path)
}

fn default_parent_from_known_folders(
    actual: &Path,
    default: &Path,
    installation_roots: &[PathBuf],
) -> Result<PathBuf, PathFailure> {
    if !same_path(actual, default) {
        return Err(PathFailure::Invalid);
    }
    let product = actual.join("Research Observatory");
    validate_existing_directory(
        product.to_str().ok_or(PathFailure::Invalid)?,
        installation_roots,
    )
}

fn local_path_syntax(value: &str) -> bool {
    let bytes = value.as_bytes();
    if !(bytes.len() >= 3
        && value.encode_utf16().count() <= 4096
        && bytes[0].is_ascii_alphabetic()
        && bytes[1] == b':'
        && matches!(bytes[2], b'\\' | b'/')
        && !value.chars().any(char::is_control)
        && !value[3..].contains([':', '*', '?', '"', '<', '>', '|']))
    {
        return false;
    }
    let normalized = value.replace('/', "\\");
    let last_component = normalized[3..].matches('\\').count();
    value.len() == 3
        || normalized[3..]
            .split('\\')
            .enumerate()
            .all(|(index, part)| {
                (!part.is_empty() || index == last_component)
                    && part != "."
                    && part != ".."
                    && !part.ends_with(['.', ' '])
            })
}

fn same_path(first: &Path, second: &Path) -> bool {
    first
        .as_os_str()
        .to_string_lossy()
        .replace('/', "\\")
        .trim_end_matches('\\')
        .to_lowercase()
        == second
            .as_os_str()
            .to_string_lossy()
            .replace('/', "\\")
            .trim_end_matches('\\')
            .to_lowercase()
}

fn path_inside(path: &Path, root: &Path) -> bool {
    Path::new(&path.as_os_str().to_string_lossy().to_lowercase()).starts_with(Path::new(
        &root.as_os_str().to_string_lossy().to_lowercase(),
    ))
}

#[cfg(feature = "integration-harness")]
pub(crate) fn fixture_contains(root: &Path, value: &str) -> bool {
    local_path_syntax(value) && path_inside(Path::new(value), root)
}

#[cfg(windows)]
fn is_reparse(metadata: &std::fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;
    metadata.file_attributes() & 0x400 != 0
}

#[cfg(not(windows))]
fn is_reparse(_metadata: &std::fs::Metadata) -> bool {
    false
}

type AuthorityCheck = Arc<dyn Fn() -> bool + Send + Sync>;

fn authority_valid(check: &AuthorityCheck) -> bool {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| check())).unwrap_or(false)
}

pub fn decode_request(payload: &serde_json::Value) -> Option<DirectoryRequest> {
    let object = payload.as_object()?;
    if object.len() != 1 {
        return None;
    }
    let request = object.get("request")?.as_object()?;
    if !(1..=2).contains(&request.len())
        || !request
            .keys()
            .all(|key| matches!(key.as_str(), "purpose" | "previousLocation"))
        || request
            .get("previousLocation")
            .is_some_and(|value| !value.as_str().is_some_and(local_path_syntax))
    {
        return None;
    }
    serde_json::from_value(serde_json::Value::Object(request.clone())).ok()
}

pub fn valid_owner(owner: isize) -> bool {
    #[cfg(windows)]
    return native::valid_owner(owner);
    #[cfg(not(windows))]
    {
        let _ = owner;
        false
    }
}

#[derive(Default)]
struct PendingDialog {
    cancelled: AtomicBool,
    wake_window: Mutex<Option<isize>>,
    #[cfg(feature = "integration-harness")]
    trace_enabled: AtomicBool,
    #[cfg(feature = "integration-harness")]
    trace_notified: AtomicBool,
    #[cfg(feature = "integration-harness")]
    trace_handled: AtomicBool,
}

impl PendingDialog {
    fn cancel(&self) {
        self.cancelled.store(true, Ordering::Release);
        // Cross-thread notification is nonblocking. Cleanup clears this slot
        // before destroying the HWND, so a sender cannot target a recycled one.
        if let Ok(window) = self.wake_window.lock()
            && let Some(address) = *window
        {
            #[cfg(windows)]
            {
                // A same-thread notification invokes the callback immediately.
                // That thread alone can destroy its HWND, so release the slot
                // before a potentially reentrant COM lookup on this branch.
                if native::current_thread_owns(address) {
                    drop(window);
                }
                let status = native::notify_cancel(address);
                #[cfg(feature = "integration-harness")]
                if self.trace_enabled.load(Ordering::Acquire)
                    && !self.trace_notified.swap(true, Ordering::AcqRel)
                {
                    native::fixture_trace(true, "cancel-notify-returned", Some(status));
                }
                #[cfg(not(feature = "integration-harness"))]
                let _ = status;
            }
            #[cfg(not(windows))]
            let _ = address;
        }
    }

    fn install_wake_window(&self, window: isize) -> bool {
        let Ok(mut slot) = self.wake_window.lock() else {
            return false;
        };
        *slot = Some(window);
        if self.cancelled.load(Ordering::Acquire) {
            #[cfg(windows)]
            native::post_cancel(window);
        }
        true
    }

    fn clear_wake_window(&self) {
        if let Ok(mut slot) = self.wake_window.lock() {
            *slot = None;
        }
    }
}

#[derive(Default)]
struct Admission {
    closed: bool,
    active: Option<Arc<PendingDialog>>,
}

#[derive(Clone, Default)]
pub struct DirectoryPickerManager {
    shared: Arc<(Mutex<Admission>, Condvar)>,
    #[cfg(feature = "integration-harness")]
    fixture_root: Option<PathBuf>,
}

pub enum CloseDisposition {
    CloseNow,
    WaitForCleanup,
    AlreadyClosing,
}

struct Reservation {
    manager: DirectoryPickerManager,
    pending: Arc<PendingDialog>,
}

impl Drop for Reservation {
    fn drop(&mut self) {
        self.pending.clear_wake_window();
        let (state, completed) = &*self.manager.shared;
        let mut state = state
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if state
            .active
            .as_ref()
            .is_some_and(|active| Arc::ptr_eq(active, &self.pending))
        {
            state.active = None;
        }
        completed.notify_all();
    }
}

impl DirectoryPickerManager {
    #[cfg(feature = "integration-harness")]
    pub(crate) fn for_fixture(root: PathBuf) -> Self {
        Self {
            fixture_root: Some(root),
            ..Self::default()
        }
    }

    #[cfg(feature = "integration-harness")]
    pub(crate) fn has_pending(&self) -> bool {
        self.admission().active.is_some()
    }

    fn admission(&self) -> std::sync::MutexGuard<'_, Admission> {
        self.shared.0.lock().unwrap_or_else(|poisoned| {
            let mut state = poisoned.into_inner();
            // A prior panic can never reopen admission, but cleanup must still
            // cancel the old worker and wake a pending main-close waiter.
            state.closed = true;
            state
        })
    }

    fn reserve(&self) -> Option<Reservation> {
        let mut state = self.admission();
        if state.closed || state.active.is_some() {
            return None;
        }
        let pending = Arc::new(PendingDialog::default());
        state.active = Some(Arc::clone(&pending));
        Some(Reservation {
            manager: self.clone(),
            pending,
        })
    }

    pub fn cancel_pending(&self) {
        let active = self.admission().active.clone();
        if let Some(active) = active {
            active.cancel();
        }
    }

    /// Permanently close admission before main-window destruction. The caller
    /// must wait off the UI thread when this reports an active native worker.
    pub fn begin_close(&self) -> CloseDisposition {
        let (active, already_closed) = {
            let mut state = self.admission();
            let already_closed = state.closed;
            state.closed = true;
            (state.active.clone(), already_closed)
        };
        if let Some(active) = active {
            active.cancel();
            if already_closed {
                CloseDisposition::AlreadyClosing
            } else {
                CloseDisposition::WaitForCleanup
            }
        } else {
            CloseDisposition::CloseNow
        }
    }

    pub fn wait_for_cleanup(&self) {
        let (state, completed) = &*self.shared;
        let mut state = state
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        while state.active.is_some() {
            state = completed
                .wait(state)
                .unwrap_or_else(|poisoned| poisoned.into_inner());
        }
    }

    pub fn is_open(&self) -> bool {
        !self.admission().closed
    }

    /// Called from a blocking waiter, never from the main window thread. The
    /// reservation moves into the dedicated STA, not the cancellable waiter.
    pub fn choose(
        &self,
        owner: isize,
        request: DirectoryRequest,
        authority: impl Fn() -> bool + Send + Sync + 'static,
    ) -> DirectoryOutcome {
        #[cfg(feature = "integration-harness")]
        let fixture_root = self.fixture_root.clone();
        self.run_worker(Arc::new(authority), move |reservation, authority| {
            #[cfg(windows)]
            return native::show(
                owner,
                &request,
                &reservation.pending,
                authority,
                #[cfg(feature = "integration-harness")]
                fixture_root.as_deref(),
            );
            #[cfg(not(windows))]
            {
                let _ = (owner, request, reservation, authority);
                DirectoryOutcome::Unavailable
            }
        })
    }

    fn run_worker(
        &self,
        authority: AuthorityCheck,
        backend: impl FnOnce(&Reservation, &AuthorityCheck) -> DirectoryOutcome + Send + 'static,
    ) -> DirectoryOutcome {
        if !authority_valid(&authority) {
            return DirectoryOutcome::Cancelled;
        }
        let Some(reservation) = self.reserve() else {
            return DirectoryOutcome::Unavailable;
        };
        std::thread::Builder::new()
            .name("project-directory-sta".into())
            .spawn(move || {
                if reservation.pending.cancelled.load(Ordering::Acquire)
                    || !authority_valid(&authority)
                {
                    return DirectoryOutcome::Cancelled;
                }
                let result = backend(&reservation, &authority);
                if reservation.pending.cancelled.load(Ordering::Acquire)
                    || !authority_valid(&authority)
                {
                    DirectoryOutcome::Cancelled
                } else {
                    result
                }
            })
            .map_or(DirectoryOutcome::Failed, |worker| {
                worker.join().unwrap_or(DirectoryOutcome::Failed)
            })
    }
}

pub fn default_project_parent() -> DefaultParentOutcome {
    #[cfg(windows)]
    {
        native::default_parent()
    }
    #[cfg(not(windows))]
    DefaultParentOutcome::Unavailable
}

#[cfg(windows)]
mod native {
    use super::*;
    use std::cell::RefCell;
    use std::ffi::c_void;
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    use std::sync::OnceLock;

    use windows::Win32::Foundation::{ERROR_CANCELLED, HWND};
    use windows::Win32::System::Com::{
        CLSCTX_INPROC_SERVER, COINIT_APARTMENTTHREADED, COINIT_DISABLE_OLE1DDE, CoCreateInstance,
        CoInitializeEx, CoTaskMemFree, CoUninitialize,
    };
    use windows::Win32::System::Ole::IOleWindow;
    use windows::Win32::UI::Shell::{
        FOS_DONTADDTORECENT, FOS_FORCEFILESYSTEM, FOS_NOCHANGEDIR, FOS_NODEREFERENCELINKS,
        FOS_PATHMUSTEXIST, FOS_PICKFOLDERS, FileOpenDialog, IFileDialog, IFileOpenDialog,
        IShellItem, SHCreateItemFromParsingName, SIGDN_FILESYSPATH,
    };
    use windows::core::{HRESULT, Interface, PCWSTR, w};
    use windows_sys::Win32::Foundation::{GetLastError, HWND as RawHwnd, LPARAM, LRESULT, WPARAM};
    use windows_sys::Win32::Storage::FileSystem::GetDriveTypeW;
    use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
    use windows_sys::Win32::System::Threading::{GetCurrentProcessId, GetCurrentThreadId};
    use windows_sys::Win32::UI::Shell::{
        FOLDERID_LocalAppData, FOLDERID_ProgramFiles, FOLDERID_ProgramFilesX86, FOLDERID_Windows,
        KF_FLAG_DEFAULT_PATH, SHGetKnownFolderPath,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        CreateWindowExW, DefWindowProcW, DestroyWindow, GetWindowThreadProcessId, HWND_MESSAGE,
        IsWindow, KillTimer, PostMessageW, RegisterClassW, SendNotifyMessageW, SetTimer, WM_APP,
        WM_CLOSE, WM_TIMER, WNDCLASSW,
    };

    const CANCEL_MESSAGE: u32 = WM_APP + 91;
    const CANCEL_TIMER: usize = 1;
    const CANCEL_POLL_MS: u32 = 50;

    struct Apartment;

    impl Apartment {
        fn initialize() -> Option<Self> {
            // A dedicated thread avoids RPC_E_CHANGED_MODE from a reused pool.
            unsafe { CoInitializeEx(None, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE) }
                .ok()
                .ok()
                .map(|()| Self)
        }
    }

    impl Drop for Apartment {
        fn drop(&mut self) {
            // Declared before all interfaces, and therefore dropped last.
            unsafe { CoUninitialize() };
        }
    }

    struct TaskMemory(*mut u16);

    impl TaskMemory {
        fn path(&self) -> Result<PathBuf, PathFailure> {
            if self.0.is_null() {
                return Err(PathFailure::Unavailable);
            }
            let mut length = 0;
            // Shell owns the allocation contract; bound application path length.
            while length <= 4096 && unsafe { *self.0.add(length) } != 0 {
                length += 1;
            }
            if length == 0 || length > 4096 {
                return Err(PathFailure::Invalid);
            }
            let wide = unsafe { std::slice::from_raw_parts(self.0, length) };
            Ok(PathBuf::from(std::ffi::OsString::from_wide(wide)))
        }
    }

    impl Drop for TaskMemory {
        fn drop(&mut self) {
            unsafe { CoTaskMemFree(Some(self.0.cast::<c_void>())) };
        }
    }

    fn known_folder(
        identity: &windows_sys::core::GUID,
        flags: u32,
    ) -> Result<PathBuf, PathFailure> {
        let mut allocation = TaskMemory(std::ptr::null_mut());
        // The raw pinned binding retains ownership even when HRESULT is an
        // error; Microsoft requires freeing the output on both result paths.
        let status = unsafe {
            SHGetKnownFolderPath(identity, flags, std::ptr::null_mut(), &mut allocation.0)
        };
        if status < 0 {
            return Err(PathFailure::Unavailable);
        }
        allocation.path()
    }

    fn installation_roots() -> Result<Vec<PathBuf>, PathFailure> {
        let executable = std::env::current_exe().map_err(|_| PathFailure::Unavailable)?;
        let executable = dunce::canonicalize(executable).map_err(|_| PathFailure::Unavailable)?;
        Ok(vec![
            known_folder(&FOLDERID_ProgramFiles, 0)?,
            known_folder(&FOLDERID_ProgramFilesX86, 0)?,
            known_folder(&FOLDERID_Windows, 0)?,
            executable
                .parent()
                .ok_or(PathFailure::Unavailable)?
                .to_path_buf(),
        ])
    }

    pub(super) fn local_drive(root: &str) -> bool {
        let value = root.encode_utf16().chain(Some(0)).collect::<Vec<_>>();
        // Removable, fixed, optical and RAM disks are local; mapped network,
        // unknown and missing roots are not. Core still checks actual access.
        matches!(unsafe { GetDriveTypeW(value.as_ptr()) }, 2 | 3 | 5 | 6)
    }

    pub(super) fn valid_owner(owner: isize) -> bool {
        if owner == 0 {
            return false;
        }
        let window = owner as RawHwnd;
        let mut process = 0;
        unsafe {
            IsWindow(window) != 0
                && GetWindowThreadProcessId(window, &mut process) != 0
                && process == GetCurrentProcessId()
        }
    }

    pub(super) fn default_parent() -> DefaultParentOutcome {
        let result = (|| {
            let actual = known_folder(&FOLDERID_LocalAppData, 0)?;
            let default = known_folder(&FOLDERID_LocalAppData, KF_FLAG_DEFAULT_PATH as u32)?;
            default_parent_from_known_folders(&actual, &default, &installation_roots()?)
        })();
        match result {
            Ok(path) => path
                .to_str()
                .map_or(DefaultParentOutcome::Unavailable, |path| {
                    DefaultParentOutcome::Available {
                        path: path.to_owned(),
                    }
                }),
            Err(_) => DefaultParentOutcome::Unavailable,
        }
    }

    #[derive(Clone)]
    struct ActiveDialog {
        dialog: IFileDialog,
        pending: Arc<PendingDialog>,
        authority: AuthorityCheck,
        owner: isize,
    }

    thread_local! {
        // COM references never leave their owning STA. The callback takes a
        // clone and releases the RefCell borrow before querying the dialog HWND.
        static ACTIVE: RefCell<Option<ActiveDialog>> = const { RefCell::new(None) };
    }

    fn dialog_window(dialog: &IFileDialog) -> windows::core::Result<RawHwnd> {
        let window = unsafe { dialog.cast::<IOleWindow>()?.GetWindow()? }.0;
        if valid_owner(window as isize) && current_thread_owns(window as isize) {
            Ok(window)
        } else {
            Err(windows::Win32::Foundation::E_UNEXPECTED.into())
        }
    }

    fn request_dialog_close(window: RawHwnd) -> i32 {
        // Use the documented close request on the exact IOleWindow HWND. The
        // Shell handles dismissal and unwinds Show on its normal dialog path.
        // Calling IFileDialog::Close from this private window callback returned
        // success without dismissal in actual Windows runs; a WM_NULL wake was
        // also insufficient. Do not depend on Shell callback internals, force
        // destruction, send input, or broadcast to other application windows.
        if !valid_owner(window as isize) || !current_thread_owns(window as isize) {
            windows::Win32::Foundation::E_UNEXPECTED.0
        } else if unsafe { PostMessageW(window, WM_CLOSE, 0, 0) } != 0 {
            0
        } else {
            HRESULT::from_win32(unsafe { GetLastError() }).0
        }
    }

    unsafe extern "system" fn cancellation_window_proc(
        window: RawHwnd,
        message: u32,
        wparam: WPARAM,
        lparam: LPARAM,
    ) -> LRESULT {
        if message == CANCEL_MESSAGE || (message == WM_TIMER && wparam == CANCEL_TIMER) {
            // No panic, blocking join, or COM call through a foreign apartment
            // may cross this FFI boundary. A timer also closes missed-post gaps.
            let _ = std::panic::catch_unwind(|| {
                let active =
                    ACTIVE.with(|slot| slot.try_borrow().ok().and_then(|slot| slot.clone()));
                if let Some(active) = active
                    && (active.pending.cancelled.load(Ordering::Acquire)
                        || !authority_valid(&active.authority)
                        || !valid_owner(active.owner))
                {
                    active.pending.cancelled.store(true, Ordering::Release);
                    #[cfg(feature = "integration-harness")]
                    let trace = active.pending.trace_enabled.load(Ordering::Acquire)
                        && !active.pending.trace_handled.swap(true, Ordering::AcqRel);
                    #[cfg(feature = "integration-harness")]
                    fixture_trace(trace, "cancel-handler-entered", None);
                    let window = dialog_window(&active.dialog);
                    #[cfg(feature = "integration-harness")]
                    fixture_trace(
                        trace,
                        "cancel-dialog-window-returned",
                        Some(window.as_ref().err().map_or(0, |error| error.code().0)),
                    );
                    if let Ok(window) = window {
                        let status = request_dialog_close(window);
                        #[cfg(feature = "integration-harness")]
                        fixture_trace(trace, "cancel-window-close-posted", Some(status));
                        #[cfg(not(feature = "integration-harness"))]
                        let _ = status;
                    }
                }
            });
            return 0;
        }
        unsafe { DefWindowProcW(window, message, wparam, lparam) }
    }

    pub(super) fn post_cancel(window: isize) {
        // Registration occurs before Show. Replay the sticky signal without a
        // reentrant COM call while the registration slot is held; show() checks
        // that flag directly and returns before displaying a cancelled dialog.
        let _ = unsafe { PostMessageW(window as RawHwnd, CANCEL_MESSAGE, 0, 0) };
    }

    pub(super) fn current_thread_owns(window: isize) -> bool {
        unsafe {
            GetWindowThreadProcessId(window as RawHwnd, std::ptr::null_mut())
                == GetCurrentThreadId()
        }
    }

    pub(super) fn notify_cancel(window: isize) -> i32 {
        // Unlike posted messages and HWND timers, sent/nonqueued messages are
        // dispatched even when a modal loop filters queued traffic to another
        // HWND. Delivery stays on the owning STA and does not block a foreign
        // sender. No COM interface crosses the thread boundary.
        if unsafe { SendNotifyMessageW(window as RawHwnd, CANCEL_MESSAGE, 0, 0) } != 0 {
            0
        } else {
            HRESULT::from_win32(unsafe { GetLastError() }).0
        }
    }

    struct CancellationWindow {
        window: RawHwnd,
        pending: Arc<PendingDialog>,
    }

    impl CancellationWindow {
        fn create(active: ActiveDialog) -> Option<Self> {
            static CLASS: OnceLock<u16> = OnceLock::new();
            let instance = unsafe { GetModuleHandleW(std::ptr::null()) };
            if instance.is_null() {
                return None;
            }
            let class = *CLASS.get_or_init(|| unsafe {
                RegisterClassW(&WNDCLASSW {
                    lpfnWndProc: Some(cancellation_window_proc),
                    hInstance: instance,
                    lpszClassName: w!("ResearchObservatory.ProjectDirectoryCancellation").as_ptr(),
                    ..Default::default()
                })
            });
            if class == 0 {
                return None;
            }
            let window = unsafe {
                CreateWindowExW(
                    0,
                    w!("ResearchObservatory.ProjectDirectoryCancellation").as_ptr(),
                    w!("").as_ptr(),
                    0,
                    0,
                    0,
                    0,
                    0,
                    HWND_MESSAGE,
                    std::ptr::null_mut(),
                    instance,
                    std::ptr::null(),
                )
            };
            if window.is_null() {
                return None;
            }
            let guard = Self {
                window,
                pending: Arc::clone(&active.pending),
            };
            ACTIVE.with(|slot| *slot.borrow_mut() = Some(active));
            if unsafe { SetTimer(window, CANCEL_TIMER, CANCEL_POLL_MS, None) } == 0
                || !guard.pending.install_wake_window(window as isize)
            {
                return None;
            }
            Some(guard)
        }
    }

    impl Drop for CancellationWindow {
        fn drop(&mut self) {
            self.pending.clear_wake_window();
            unsafe { KillTimer(self.window, CANCEL_TIMER) };
            ACTIVE.with(|slot| *slot.borrow_mut() = None);
            unsafe { DestroyWindow(self.window) };
        }
    }

    fn shell_item_for_directory(path: &Path) -> windows::core::Result<IShellItem> {
        let wide = path
            .as_os_str()
            .encode_wide()
            // The path contract accepts either separator, but Shell parsing
            // rejects mixed separators. Preserve every other UTF-16 unit.
            .map(|unit| {
                if unit == u16::from(b'/') {
                    u16::from(b'\\')
                } else {
                    unit
                }
            })
            .chain(Some(0))
            .collect::<Vec<_>>();
        unsafe { SHCreateItemFromParsingName(PCWSTR(wide.as_ptr()), None) }
    }

    #[cfg(test)]
    pub(super) fn shell_item_roundtrip(path: &Path) -> Result<PathBuf, i32> {
        let _apartment = Apartment::initialize().ok_or(-1)?;
        let item = shell_item_for_directory(path).map_err(|error| error.code().0)?;
        let result =
            unsafe { item.GetDisplayName(SIGDN_FILESYSPATH) }.map_err(|error| error.code().0)?;
        TaskMemory(result.0).path().map_err(|_| -2)
    }

    #[cfg(feature = "integration-harness")]
    pub(super) fn fixture_trace(enabled: bool, stage: &'static str, hresult: Option<i32>) {
        if enabled {
            use std::io::Write;
            // Fixture diagnostics carry only fixed stage names and HRESULTs,
            // never selected paths, Shell text, credentials or user metadata.
            let _ = writeln!(
                std::io::stdout().lock(),
                "{}",
                serde_json::json!({"kind":"tauri-directory-stage", "stage":stage,
                    "hresult":hresult})
            );
        }
    }

    pub(super) fn show(
        owner: isize,
        request: &DirectoryRequest,
        pending: &Arc<PendingDialog>,
        authority: &AuthorityCheck,
        #[cfg(feature = "integration-harness")] fixture_root: Option<&Path>,
    ) -> DirectoryOutcome {
        #[cfg(feature = "integration-harness")]
        pending
            .trace_enabled
            .store(fixture_root.is_some(), Ordering::Release);
        if !valid_owner(owner) {
            return DirectoryOutcome::Unavailable;
        }
        let Some(_apartment) = Apartment::initialize() else {
            return DirectoryOutcome::Unavailable;
        };
        let Ok(roots) = installation_roots() else {
            return DirectoryOutcome::Unavailable;
        };
        #[cfg(feature = "integration-harness")]
        fixture_trace(fixture_root.is_some(), "validate-previous", None);
        #[cfg(feature = "integration-harness")]
        if fixture_root.is_some_and(|root| {
            request
                .previous_location
                .as_deref()
                .is_some_and(|path| !fixture_contains(root, path))
        }) {
            return DirectoryOutcome::Failed;
        }
        let previous = match request.previous_location.as_deref() {
            Some(path) => match validate_existing_directory(path, &roots) {
                Ok(path) => Some(path),
                Err(PathFailure::Invalid) => return DirectoryOutcome::Failed,
                // A disappeared/unavailable previously valid suggestion is not
                // authority to invent a directory; the native default remains.
                Err(PathFailure::Unavailable) => None,
            },
            None => None,
        };
        #[cfg(feature = "integration-harness")]
        let previous = if let Some(root) = fixture_root {
            match previous {
                Some(path) => Some(path),
                None => match root
                    .to_str()
                    .ok_or(PathFailure::Invalid)
                    .and_then(|path| validate_existing_directory(path, &roots))
                {
                    Ok(path) => Some(path),
                    Err(_) => return DirectoryOutcome::Failed,
                },
            }
        } else {
            previous
        };
        let Ok(dialog) = (unsafe {
            CoCreateInstance::<_, IFileOpenDialog>(&FileOpenDialog, None, CLSCTX_INPROC_SERVER)
        }) else {
            return DirectoryOutcome::Unavailable;
        };
        #[cfg(feature = "integration-harness")]
        fixture_trace(fixture_root.is_some(), "configure-options", None);
        let configured = unsafe {
            (|| -> windows::core::Result<()> {
                let options = dialog.GetOptions()?;
                dialog.SetOptions(
                    options
                        | FOS_PICKFOLDERS
                        | FOS_FORCEFILESYSTEM
                        | FOS_PATHMUSTEXIST
                        | FOS_NOCHANGEDIR
                        | FOS_DONTADDTORECENT
                        | FOS_NODEREFERENCELINKS,
                )?;
                #[cfg(feature = "integration-harness")]
                fixture_trace(fixture_root.is_some(), "configure-title", None);
                match request.purpose {
                    DirectoryPurpose::CreateParent => {
                        dialog.SetTitle(w!("Choose a parent folder for the new project"))?
                    }
                    DirectoryPurpose::OpenProject => {
                        dialog.SetTitle(w!("Choose an existing Research Observatory project"))?
                    }
                }
                if let Some(path) = previous {
                    #[cfg(feature = "integration-harness")]
                    fixture_trace(fixture_root.is_some(), "parse-initial-shell-item", None);
                    let item = shell_item_for_directory(&path)?;
                    #[cfg(feature = "integration-harness")]
                    fixture_trace(fixture_root.is_some(), "set-initial-shell-folder", None);
                    // The field's explicit current value takes precedence over
                    // OS MRU state. Failure to suggest it is non-destructive.
                    let suggested = dialog.SetFolder(&item);
                    #[cfg(feature = "integration-harness")]
                    if fixture_root.is_some() {
                        suggested?;
                    }
                    #[cfg(not(feature = "integration-harness"))]
                    let _ = suggested;
                }
                Ok(())
            })()
        };
        if let Err(error) = configured {
            #[cfg(feature = "integration-harness")]
            fixture_trace(
                fixture_root.is_some(),
                "configuration-failed",
                Some(error.code().0),
            );
            #[cfg(not(feature = "integration-harness"))]
            let _ = error;
            return DirectoryOutcome::Failed;
        }
        #[cfg(feature = "integration-harness")]
        fixture_trace(fixture_root.is_some(), "create-cancellation-window", None);
        let Ok(file_dialog) = dialog.cast::<IFileDialog>() else {
            return DirectoryOutcome::Failed;
        };
        let Some(_cancellation) = CancellationWindow::create(ActiveDialog {
            dialog: file_dialog,
            pending: Arc::clone(pending),
            authority: Arc::clone(authority),
            owner,
        }) else {
            return DirectoryOutcome::Failed;
        };
        if pending.cancelled.load(Ordering::Acquire)
            || !authority_valid(authority)
            || !valid_owner(owner)
        {
            return DirectoryOutcome::Cancelled;
        }
        // Sent cancellation is dispatched on this same STA even if the modal
        // loop filters queued traffic away from the private cancellation HWND.
        // No application mutex or thread-local borrow is held across Show.
        #[cfg(feature = "integration-harness")]
        fixture_trace(fixture_root.is_some(), "show", None);
        let shown = unsafe { dialog.Show(Some(HWND(owner as *mut c_void))) };
        #[cfg(feature = "integration-harness")]
        fixture_trace(
            fixture_root.is_some(),
            "show-returned",
            shown.as_ref().err().map(|error| error.code().0),
        );
        if pending.cancelled.load(Ordering::Acquire)
            || !authority_valid(authority)
            || !valid_owner(owner)
        {
            return DirectoryOutcome::Cancelled;
        }
        if let Err(error) = shown {
            return if error.code() == HRESULT::from_win32(ERROR_CANCELLED.0) {
                DirectoryOutcome::Cancelled
            } else {
                DirectoryOutcome::Failed
            };
        }
        let result = unsafe {
            dialog
                .GetResult()
                .and_then(|item| item.GetDisplayName(SIGDN_FILESYSPATH))
        };
        let Ok(result) = result else {
            return DirectoryOutcome::Failed;
        };
        let allocation = TaskMemory(result.0);
        let path = allocation.path().and_then(|path| {
            let value = path.to_str().ok_or(PathFailure::Invalid)?;
            #[cfg(feature = "integration-harness")]
            if fixture_root.is_some_and(|root| !fixture_contains(root, value)) {
                return Err(PathFailure::Invalid);
            }
            validate_existing_directory(value, &roots)
        });
        match path {
            Ok(path) => DirectoryOutcome::Selected {
                path: path.to_string_lossy().into_owned(),
            },
            Err(_) => DirectoryOutcome::Failed,
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use std::sync::atomic::AtomicU32;
        use windows::Win32::Foundation::CO_E_NOTINITIALIZED;
        use windows::Win32::System::Com::{
            APTTYPE, APTTYPE_MAINSTA, APTTYPE_MTA, APTTYPE_STA, APTTYPEQUALIFIER,
            APTTYPEQUALIFIER_IMPLICIT_MTA, COINIT_MULTITHREADED, CoGetApartmentType,
        };
        use windows_sys::Win32::System::Threading::GetCurrentThreadId;
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            DispatchMessageW, GetMessageW, IsWindowVisible, MSG, PM_REMOVE, PeekMessageW,
        };

        fn assert_sta() {
            let mut apartment = APTTYPE::default();
            let mut qualifier = APTTYPEQUALIFIER::default();
            unsafe { CoGetApartmentType(&mut apartment, &mut qualifier) }.unwrap();
            assert!(matches!(apartment, APTTYPE_STA | APTTYPE_MAINSTA));
        }

        fn assert_uninitialized() {
            let mut apartment = APTTYPE::default();
            let mut qualifier = APTTYPEQUALIFIER::default();
            match unsafe { CoGetApartmentType(&mut apartment, &mut qualifier) } {
                Err(error) => assert_eq!(error.code(), CO_E_NOTINITIALIZED),
                // Another test/Shell worker may keep the process MTA alive.
                // This exact qualifier means this thread has no explicit COM
                // initialization; a remaining STA or explicit MTA still fails.
                Ok(()) => assert_eq!(
                    (apartment, qualifier),
                    (APTTYPE_MTA, APTTYPEQUALIFIER_IMPLICIT_MTA)
                ),
            }
        }

        #[test]
        fn real_sta_cleanup_with_process_mta_does_not_retain_explicit_initialization() {
            unsafe { CoInitializeEx(None, COINIT_MULTITHREADED) }
                .ok()
                .unwrap();
            let _mta = Apartment;
            std::thread::spawn(|| {
                let apartment = Apartment::initialize().unwrap();
                assert_sta();
                assert!(
                    std::panic::catch_unwind(assert_uninitialized).is_err(),
                    "cleanup assertion must reject a still-initialized STA"
                );
                drop(apartment);
                let mut observed = APTTYPE::default();
                let mut qualifier = APTTYPEQUALIFIER::default();
                unsafe { CoGetApartmentType(&mut observed, &mut qualifier) }.unwrap();
                assert_eq!(observed, APTTYPE_MTA);
                assert_eq!(qualifier, APTTYPEQUALIFIER_IMPLICIT_MTA);
                assert_uninitialized();
            })
            .join()
            .unwrap();
        }

        // These are real COM and message-window boundary tests. The dialog is
        // never shown; they do not establish visible selection, focus, or
        // dismissal during IFileDialog::Show.
        fn unshown_dialog(
            pending: &Arc<PendingDialog>,
            authority: AuthorityCheck,
        ) -> CancellationWindow {
            let dialog: IFileOpenDialog =
                unsafe { CoCreateInstance(&FileOpenDialog, None, CLSCTX_INPROC_SERVER) }.unwrap();
            CancellationWindow::create(ActiveDialog {
                dialog: dialog.cast().unwrap(),
                pending: Arc::clone(pending),
                authority,
                owner: 0,
            })
            .expect("create the real private cancellation HWND")
        }

        fn assert_cleaned_up(pending: &PendingDialog, window: RawHwnd) {
            assert!(pending.wake_window.lock().unwrap().is_none());
            assert!(ACTIVE.with(|slot| slot.borrow().is_none()));
            assert_eq!(unsafe { IsWindow(window) }, 0);
            // A new cancellation has no stale HWND to post to.
            pending.cancel();
            assert!(pending.wake_window.lock().unwrap().is_none());
        }

        #[test]
        fn real_dialog_interfaces_retain_the_same_com_identity() {
            std::thread::spawn(|| {
                let apartment = Apartment::initialize().unwrap();
                {
                    let dialog: IFileOpenDialog =
                        unsafe { CoCreateInstance(&FileOpenDialog, None, CLSCTX_INPROC_SERVER) }
                            .unwrap();
                    let active = dialog.cast::<IFileDialog>().unwrap().clone();
                    assert_eq!(
                        dialog.cast::<windows::core::IUnknown>().unwrap(),
                        active.cast::<windows::core::IUnknown>().unwrap()
                    );
                    assert!(active.cast::<IOleWindow>().is_ok());
                }
                drop(apartment);
                assert_uninitialized();
            })
            .join()
            .unwrap();
        }

        #[test]
        fn real_unshown_close_success_does_not_prove_dialog_dismissal() {
            std::thread::spawn(|| {
                let apartment = Apartment::initialize().unwrap();
                {
                    let dialog: IFileDialog =
                        unsafe { CoCreateInstance(&FileOpenDialog, None, CLSCTX_INPROC_SERVER) }
                            .unwrap();
                    let exact = unsafe {
                        (Interface::vtable(&dialog).Close)(
                            Interface::as_raw(&dialog),
                            HRESULT::from_win32(ERROR_CANCELLED.0),
                        )
                    };
                    assert_eq!(exact.0, 0);
                    assert!(
                        dialog_window(&dialog).is_err(),
                        "no dialog HWND was shown or dismissed"
                    );
                }
                drop(apartment);
                assert_uninitialized();
            })
            .join()
            .unwrap();
        }

        #[test]
        fn real_owned_modal_close_dispatch_destroys_only_the_target_window() {
            // This exercises real Windows close dispatch and target isolation,
            // not a shown Shell dialog. The watchdog posts only to our hidden
            // window and bounds failure; actual Shell dismissal needs UI proof.
            std::thread::spawn(|| {
                const WATCHDOG: u32 = WM_APP + 92;
                const UNRELATED: u32 = WM_APP + 93;
                thread_local! {
                    static PROBE: RefCell<Option<(RawHwnd, Arc<AtomicBool>)>> =
                        const { RefCell::new(None) };
                }
                unsafe extern "system" fn procedure(
                    window: RawHwnd,
                    message: u32,
                    wparam: WPARAM,
                    lparam: LPARAM,
                ) -> LRESULT {
                    if message == CANCEL_MESSAGE {
                        let active = PROBE.with(|slot| slot.borrow().clone());
                        if let Some((modal, closed)) = active {
                            closed.store(request_dialog_close(modal) == 0, Ordering::Release);
                        }
                        return 0;
                    }
                    unsafe { DefWindowProcW(window, message, wparam, lparam) }
                }
                struct HiddenWindow(RawHwnd);
                impl Drop for HiddenWindow {
                    fn drop(&mut self) {
                        unsafe { DestroyWindow(self.0) };
                    }
                }
                let apartment = Apartment::initialize().unwrap();
                let instance = unsafe { GetModuleHandleW(std::ptr::null()) };
                assert_ne!(
                    unsafe {
                        RegisterClassW(&WNDCLASSW {
                            lpfnWndProc: Some(procedure),
                            hInstance: instance,
                            lpszClassName: w!("ResearchObservatory.TestBlockingModalWait").as_ptr(),
                            ..Default::default()
                        })
                    },
                    0
                );
                let create = || {
                    let window = HiddenWindow(unsafe {
                        CreateWindowExW(
                            0,
                            w!("ResearchObservatory.TestBlockingModalWait").as_ptr(),
                            w!("").as_ptr(),
                            0,
                            0,
                            0,
                            0,
                            0,
                            HWND_MESSAGE,
                            std::ptr::null_mut(),
                            instance,
                            std::ptr::null(),
                        )
                    });
                    assert!(!window.0.is_null());
                    assert_eq!(unsafe { IsWindowVisible(window.0) }, 0);
                    window
                };
                let modal = create();
                let notification = create();
                let closed = Arc::new(AtomicBool::new(false));
                PROBE.with(|slot| *slot.borrow_mut() = Some((modal.0, Arc::clone(&closed))));
                let mut message = MSG::default();
                while unsafe { PeekMessageW(&mut message, modal.0, 0, 0, PM_REMOVE) } != 0 {
                    unsafe { DispatchMessageW(&message) };
                }
                let modal_address = modal.0 as isize;
                let notification_address = notification.0 as isize;
                let (completed, completion) = std::sync::mpsc::channel::<()>();
                let (allow_cancel, cancellation_allowed) = std::sync::mpsc::channel::<()>();
                // Force the previously racy schedule: one unrelated queued
                // message is retrieved before cancellation can be notified.
                assert_ne!(unsafe { PostMessageW(modal.0, UNRELATED, 0, 0) }, 0);
                let sender = std::thread::spawn(move || {
                    cancellation_allowed
                        .recv_timeout(std::time::Duration::from_secs(2))
                        .unwrap();
                    assert_eq!(
                        request_dialog_close(std::ptr::null_mut()),
                        windows::Win32::Foundation::E_UNEXPECTED.0
                    );
                    assert_eq!(
                        request_dialog_close(modal_address as RawHwnd),
                        windows::Win32::Foundation::E_UNEXPECTED.0,
                        "direct close requests must reject a foreign STA's HWND"
                    );
                    assert_eq!(notify_cancel(notification_address), 0);
                    if completion
                        .recv_timeout(std::time::Duration::from_millis(500))
                        .is_err()
                    {
                        assert_ne!(
                            unsafe { PostMessageW(modal_address as RawHwnd, WATCHDOG, 0, 0) },
                            0
                        );
                    }
                });
                // A queued message does not prove cancellation was dispatched.
                // Keep pumping until close/watchdog, without reading again
                // after WM_CLOSE destroys the target. The sender's watchdog
                // bounds an idle GetMessage; this deadline also bounds noise.
                let deadline = std::time::Instant::now() + std::time::Duration::from_secs(2);
                let mut observed = Vec::new();
                let retrieved = loop {
                    let retrieved = unsafe { GetMessageW(&mut message, modal.0, 0, 0) };
                    if retrieved <= 0 {
                        break retrieved;
                    }
                    if observed.len() < 16 {
                        observed.push(message.message);
                    }
                    if message.message == UNRELATED {
                        let _ = allow_cancel.send(());
                    }
                    unsafe { DispatchMessageW(&message) };
                    if matches!(message.message, WM_CLOSE | WATCHDOG)
                        || std::time::Instant::now() >= deadline
                    {
                        break retrieved;
                    }
                };
                let _ = completed.send(());
                sender.join().unwrap();
                let target_destroyed = unsafe { IsWindow(modal.0) } == 0;
                let sibling_preserved = unsafe { IsWindow(notification.0) } != 0;
                PROBE.with(|slot| *slot.borrow_mut() = None);
                drop(notification);
                drop(modal);
                drop(apartment);
                assert_uninitialized();
                assert!(
                    closed.load(Ordering::Acquire),
                    "the owning STA must post the close request; observed messages {observed:x?}"
                );
                assert!(retrieved > 0);
                assert!(
                    target_destroyed,
                    "cancellation must close the target, not merely wake its modal queue"
                );
                assert!(
                    sibling_preserved,
                    "cancellation must not target a sibling or owner window"
                );
                assert_eq!(message.message, WM_CLOSE);
                assert!(
                    observed.contains(&UNRELATED),
                    "exercise unrelated-message-first scheduling"
                );
            })
            .join()
            .unwrap();
        }

        #[test]
        fn real_sta_cancellation_survives_a_filtered_message_pump() {
            std::thread::spawn(|| {
                struct FilterWindow(RawHwnd);
                impl Drop for FilterWindow {
                    fn drop(&mut self) {
                        unsafe { DestroyWindow(self.0) };
                    }
                }

                let apartment = Apartment::initialize().unwrap();
                let pending = Arc::new(PendingDialog::default());
                let callback_thread = Arc::new(AtomicU32::new(0));
                let observed_thread = Arc::clone(&callback_thread);
                let cancellation = unshown_dialog(
                    &pending,
                    Arc::new(move || {
                        observed_thread.store(unsafe { GetCurrentThreadId() }, Ordering::SeqCst);
                        false
                    }),
                );
                let filter = FilterWindow(unsafe {
                    CreateWindowExW(
                        0,
                        w!("STATIC").as_ptr(),
                        w!("").as_ptr(),
                        0,
                        0,
                        0,
                        0,
                        0,
                        HWND_MESSAGE,
                        std::ptr::null_mut(),
                        std::ptr::null_mut(),
                        std::ptr::null(),
                    )
                });
                assert!(!filter.0.is_null());
                assert!(!pending.cancelled.load(Ordering::Acquire));
                let window = cancellation.window;
                let address = window as isize;
                // Exercise the real wake transport from another thread. The
                // authority callback marks delivery on the owning STA; do not
                // set the sticky flag here, which would conceal nondelivery.
                std::thread::spawn(move || notify_cancel(address))
                    .join()
                    .unwrap();
                let deadline = std::time::Instant::now() + std::time::Duration::from_millis(500);
                let mut message = MSG::default();
                while !pending.cancelled.load(Ordering::Acquire)
                    && std::time::Instant::now() < deadline
                {
                    // An opaque modal loop may filter queued messages to its
                    // own window. Never manually dispatch the cancellation
                    // window's queued message or timer to make this test pass.
                    if unsafe { PeekMessageW(&mut message, filter.0, 0, 0, PM_REMOVE) } != 0 {
                        unsafe { DispatchMessageW(&message) };
                    }
                    std::thread::sleep(std::time::Duration::from_millis(1));
                }
                let delivered = pending.cancelled.load(Ordering::Acquire);
                drop(filter);
                drop(cancellation);
                assert_cleaned_up(&pending, window);
                assert!(delivered, "filtered STA pump starved native cancellation");
                assert_eq!(
                    callback_thread.load(Ordering::SeqCst),
                    unsafe { GetCurrentThreadId() },
                    "COM cancellation and authority checks must stay on the owning STA"
                );
                drop(apartment);
                assert_uninitialized();
            })
            .join()
            .unwrap();
        }

        #[test]
        fn real_sta_replays_cancel_before_hwnd_registration_and_cleans_up() {
            std::thread::spawn(|| {
                assert_uninitialized();
                let apartment = Apartment::initialize().unwrap();
                assert_sta();
                let pending = Arc::new(PendingDialog::default());
                pending.cancel();
                let cancellation = unshown_dialog(&pending, Arc::new(|| true));
                let window = cancellation.window;
                assert_eq!(unsafe { IsWindowVisible(window) }, 0);
                assert_eq!(
                    unsafe { GetWindowThreadProcessId(window, std::ptr::null_mut()) },
                    unsafe { GetCurrentThreadId() }
                );
                let mut message = MSG::default();
                assert_ne!(
                    unsafe {
                        PeekMessageW(
                            &mut message,
                            window,
                            CANCEL_MESSAGE,
                            CANCEL_MESSAGE,
                            PM_REMOVE,
                        )
                    },
                    0,
                    "registration must replay sticky cancellation to the real HWND"
                );
                unsafe { DispatchMessageW(&message) };
                assert!(pending.cancelled.load(Ordering::Acquire));
                drop(cancellation);
                assert_cleaned_up(&pending, window);
                drop(apartment);
                assert_uninitialized();
            })
            .join()
            .unwrap();
        }

        #[test]
        fn real_sta_timer_detects_generation_invalidation_without_a_cancel_post() {
            std::thread::spawn(|| {
                let apartment = Apartment::initialize().unwrap();
                let pending = Arc::new(PendingDialog::default());
                let callback_thread = Arc::new(AtomicU32::new(0));
                let observed_thread = Arc::clone(&callback_thread);
                let cancellation = unshown_dialog(
                    &pending,
                    Arc::new(move || {
                        observed_thread.store(unsafe { GetCurrentThreadId() }, Ordering::SeqCst);
                        false
                    }),
                );
                let window = cancellation.window;
                assert!(!pending.cancelled.load(Ordering::Acquire));
                let deadline = std::time::Instant::now() + std::time::Duration::from_secs(2);
                let mut message = MSG::default();
                while unsafe { PeekMessageW(&mut message, window, WM_TIMER, WM_TIMER, PM_REMOVE) }
                    == 0
                {
                    assert!(
                        std::time::Instant::now() < deadline,
                        "native timer did not fire"
                    );
                    std::thread::sleep(std::time::Duration::from_millis(1));
                }
                unsafe { DispatchMessageW(&message) };
                assert!(pending.cancelled.load(Ordering::Acquire));
                assert_eq!(
                    callback_thread.load(Ordering::SeqCst),
                    unsafe { GetCurrentThreadId() },
                    "generation check and COM cancellation stay on the owning STA"
                );
                drop(cancellation);
                assert_cleaned_up(&pending, window);
                drop(apartment);
                assert_uninitialized();
            })
            .join()
            .unwrap();
        }

        #[test]
        fn real_sta_panic_releases_com_window_and_pending_handle() {
            std::thread::spawn(|| {
                let pending = Arc::new(PendingDialog::default());
                let window = std::cell::Cell::new(std::ptr::null_mut());
                let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    let _apartment = Apartment::initialize().unwrap();
                    let cancellation = unshown_dialog(&pending, Arc::new(|| true));
                    window.set(cancellation.window);
                    panic!("synthetic failure after native registration");
                }));
                assert!(result.is_err());
                assert!(!window.get().is_null());
                assert_cleaned_up(&pending, window.get());
                assert_uninitialized();
            })
            .join()
            .unwrap();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static NEXT_FIXTURE: AtomicUsize = AtomicUsize::new(0);

    struct Fixture(PathBuf, PathBuf, (u64, u64));

    impl Fixture {
        fn new() -> Self {
            let repo = dunce::canonicalize(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.."))
                .unwrap();
            let parent = repo.join("artifacts/tmp");
            validate_existing_directory(parent.to_str().unwrap(), &[])
                .expect("safe existing fixture parent");
            let nonce = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            Self::from_candidates(
                &parent,
                (0..32).map(|_| {
                    parent.join(format!(
                        "directory-picker-unit-{}-{nonce}-{}",
                        std::process::id(),
                        NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed)
                    ))
                }),
            )
        }

        fn from_candidates(parent: &Path, candidates: impl Iterator<Item = PathBuf>) -> Self {
            for path in candidates {
                assert_eq!(path.parent(), Some(parent));
                assert!(
                    path.file_name()
                        .unwrap()
                        .to_str()
                        .unwrap()
                        .starts_with("directory-picker-unit-")
                );
                match std::fs::create_dir(&path) {
                    Ok(()) => {
                        assert_eq!(dunce::canonicalize(&path).unwrap(), path);
                        let metadata = std::fs::symlink_metadata(&path).unwrap();
                        assert!(
                            metadata.is_dir()
                                && !metadata.file_type().is_symlink()
                                && !is_reparse(&metadata)
                        );
                        let identity = fixture_identity(&path);
                        return Self(path, parent.to_owned(), identity);
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                    Err(error) => panic!("exclusive fixture creation failed: {error}"),
                }
            }
            panic!("no fresh fixture candidate available");
        }
    }

    #[cfg(windows)]
    fn fixture_identity(path: &Path) -> (u64, u64) {
        use std::os::windows::{fs::OpenOptionsExt, io::AsRawHandle};
        use windows_sys::Win32::Storage::FileSystem::{
            BY_HANDLE_FILE_INFORMATION, GetFileInformationByHandle,
        };
        let directory = std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(0x02000000 | 0x00200000)
            .open(path)
            .unwrap();
        let mut information = BY_HANDLE_FILE_INFORMATION::default();
        assert_ne!(
            unsafe { GetFileInformationByHandle(directory.as_raw_handle(), &mut information) },
            0
        );
        (
            u64::from(information.dwVolumeSerialNumber),
            (u64::from(information.nFileIndexHigh) << 32) | u64::from(information.nFileIndexLow),
        )
    }

    #[cfg(not(windows))]
    fn fixture_identity(path: &Path) -> (u64, u64) {
        use std::os::unix::fs::MetadataExt;
        let metadata = std::fs::symlink_metadata(path).unwrap();
        (metadata.dev(), metadata.ino())
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            assert_eq!(self.0.parent(), Some(self.1.as_path()));
            assert_eq!(dunce::canonicalize(&self.0).unwrap(), self.0);
            let metadata = std::fs::symlink_metadata(&self.0).unwrap();
            assert!(
                metadata.is_dir() && !metadata.file_type().is_symlink() && !is_reparse(&metadata)
            );
            assert_eq!(
                fixture_identity(&self.0),
                self.2,
                "refuse cleanup of a substituted directory"
            );
            std::fs::remove_dir_all(&self.0)
                .expect("remove only exclusively created, identity-checked fixture");
        }
    }

    #[test]
    fn fixture_creation_never_reuses_or_removes_an_existing_candidate() {
        let existing = Fixture::new();
        let sentinel = existing.0.join("sentinel");
        std::fs::write(&sentinel, b"preexisting synthetic fixture").unwrap();
        let fresh = existing.0.with_file_name(format!(
            "{}-next",
            existing.0.file_name().unwrap().to_str().unwrap()
        ));
        let selected =
            Fixture::from_candidates(&existing.1, [existing.0.clone(), fresh].into_iter());
        assert_ne!(selected.0, existing.0);
        drop(selected);
        assert_eq!(
            std::fs::read(&sentinel).unwrap(),
            b"preexisting synthetic fixture"
        );
    }

    #[cfg(windows)]
    #[test]
    fn real_shell_item_preserves_unicode_identity_for_supported_separators() {
        let fixture = Fixture::new();
        let directory = fixture.0.join("Étude 数据 🧪");
        std::fs::create_dir(&directory).unwrap();
        let expected_identity = fixture_identity(&directory);
        let backslashes = directory.to_str().unwrap().replace('/', "\\");
        let mixed = backslashes.replacen("\\artifacts\\tmp\\", "\\artifacts/tmp\\", 1);
        assert_ne!(backslashes, mixed);
        for (case, value) in [("backslashes", backslashes), ("mixed", mixed)] {
            let validated = validate_existing_directory(&value, &[]).unwrap();
            let returned = std::thread::spawn(move || native::shell_item_roundtrip(&validated))
                .join()
                .unwrap()
                .unwrap_or_else(|hresult| panic!("Shell case {case} failed: HRESULT {hresult:#x}"));
            assert!(validate_existing_directory(returned.to_str().unwrap(), &[]).is_ok());
            assert!(fixture_identity(&returned) == expected_identity);
            assert!(returned.file_name() == directory.file_name());
        }
    }

    #[test]
    fn request_and_outcomes_are_exact_and_path_free_on_non_success() {
        for invalid_call in [
            json!(null),
            json!({}),
            json!({"request":null}),
            json!({"request":{"purpose":"create-parent"}, "owner":123}),
        ] {
            assert!(decode_request(&invalid_call).is_none());
        }
        assert!(decode_request(&json!({"request":{"purpose":"create-parent"}})).is_some());
        for purpose in ["create-parent", "open-project"] {
            assert!(serde_json::from_value::<DirectoryRequest>(json!({"purpose":purpose})).is_ok());
            assert!(
                serde_json::from_value::<DirectoryRequest>(json!({
                    "purpose":purpose, "previousLocation":"C:\\Synthetic folder"
                }))
                .is_ok()
            );
        }
        for value in [
            json!({}),
            json!({"purpose":"delete"}),
            json!({"purpose":"open-project","previousLocation":null}),
            json!({"purpose":"open-project","previousLocation":1}),
            json!({"purpose":"open-project","path":"C:\\private"}),
            json!({"purpose":"open-project","owner":123}),
        ] {
            assert!(serde_json::from_value::<DirectoryRequest>(value).is_err());
        }
        for (outcome, status) in [
            (DirectoryOutcome::Cancelled, "cancelled"),
            (DirectoryOutcome::Unavailable, "unavailable"),
            (DirectoryOutcome::Failed, "failed"),
        ] {
            assert_eq!(
                serde_json::to_value(outcome).unwrap(),
                json!({"status":status})
            );
        }
        assert_eq!(
            serde_json::to_value(DefaultParentOutcome::Unavailable).unwrap(),
            json!({"status":"unavailable"})
        );
        assert_eq!(
            serde_json::to_value(DefaultParentOutcome::Failed).unwrap(),
            json!({"status":"failed"})
        );
    }

    #[test]
    fn existing_unicode_directory_is_preserved_and_discovery_does_not_provision() {
        let fixture = Fixture::new();
        let local = fixture.0.join("Local données");
        std::fs::create_dir(&local).unwrap();
        let product = local.join("Research Observatory");
        assert_eq!(
            default_parent_from_known_folders(&local, &local, &[]),
            Err(PathFailure::Unavailable)
        );
        assert!(
            !product.exists(),
            "discovery must never provision the product parent"
        );
        std::fs::create_dir(&product).unwrap();
        assert_eq!(
            validate_existing_directory(product.to_str().unwrap(), &[]),
            Ok(product.clone())
        );
        let forward = product.to_str().unwrap().replace('\\', "/");
        assert_eq!(
            validate_existing_directory(&forward, &[]),
            Ok(PathBuf::from(&forward))
        );
        assert!(validate_existing_directory(&format!("{forward}/"), &[]).is_ok());
        assert_eq!(
            default_parent_from_known_folders(&local, &local, &[]),
            Ok(product.clone())
        );
        assert_eq!(std::fs::read_dir(&product).unwrap().count(), 0);
    }

    #[test]
    fn paths_reject_invalid_missing_file_installation_and_redirected_default() {
        let fixture = Fixture::new();
        for invalid in [
            "",
            "relative",
            "C:relative",
            "\\\\server\\share",
            "\\\\?\\C:\\folder",
            "C:\\folder\0suffix",
            "C:\\folder\\..\\other",
            "C:\\folder\\file:stream",
        ] {
            assert_eq!(
                validate_existing_directory(invalid, &[]),
                Err(PathFailure::Invalid),
                "{invalid:?}"
            );
        }
        assert_eq!(
            validate_existing_directory(fixture.0.join("missing").to_str().unwrap(), &[]),
            Err(PathFailure::Unavailable)
        );
        let file = fixture.0.join("file");
        std::fs::write(&file, b"synthetic").unwrap();
        assert_eq!(
            validate_existing_directory(file.to_str().unwrap(), &[]),
            Err(PathFailure::Invalid)
        );
        assert_eq!(
            validate_existing_directory(
                fixture.0.to_str().unwrap(),
                std::slice::from_ref(&fixture.0)
            ),
            Err(PathFailure::Invalid)
        );
        assert_eq!(
            default_parent_from_known_folders(&fixture.0, &fixture.0.join("redirected"), &[]),
            Err(PathFailure::Invalid)
        );
        let at_limit = format!("C:\\{}x", "😀".repeat(2046));
        assert_eq!(at_limit.encode_utf16().count(), 4096);
        assert!(local_path_syntax(&at_limit));
        assert!(!local_path_syntax(&format!("{at_limit}x")));
    }

    #[test]
    fn native_paths_and_requests_reject_c1_controls_before_filesystem_access() {
        for control in '\u{80}'..='\u{9f}' {
            let path = format!("C:\\Synthetic{control}folder");
            assert!(
                !local_path_syntax(&path),
                "C1 control U+{:04X} must be rejected",
                u32::from(control)
            );
            assert_eq!(
                validate_existing_directory(&path, &[]),
                Err(PathFailure::Invalid)
            );
            assert!(
                decode_request(&json!({"request":{
                    "purpose":"create-parent", "previousLocation":path
                }}))
                .is_none()
            );
        }
    }

    #[test]
    fn existing_parent_checks_every_ancestor_and_installation_component_boundary() {
        let fixture = Fixture::new();
        let install = fixture.0.join("install");
        let neighbour = fixture.0.join("installation-not-the-root");
        std::fs::create_dir(&install).unwrap();
        std::fs::create_dir(&neighbour).unwrap();
        assert_eq!(
            validate_existing_directory(
                neighbour.to_str().unwrap(),
                std::slice::from_ref(&install)
            ),
            Ok(neighbour)
        );
        assert_eq!(
            validate_existing_directory(
                install.to_str().unwrap(),
                &[PathBuf::from(install.to_str().unwrap().to_uppercase())]
            ),
            Err(PathFailure::Invalid)
        );
        let file = fixture.0.join("not-a-directory");
        std::fs::write(&file, b"synthetic").unwrap();
        assert_eq!(
            validate_existing_directory(file.join("child").to_str().unwrap(), &[]),
            Err(PathFailure::Invalid)
        );
    }

    #[cfg(windows)]
    #[test]
    fn reparse_parent_and_ancestor_are_rejected_without_following() {
        let fixture = Fixture::new();
        let real = fixture.0.join("real");
        std::fs::create_dir(&real).unwrap();
        std::fs::create_dir(real.join("child")).unwrap();
        let link = fixture.0.join("link");
        // Junctions exercise the same reparse boundary without requiring a
        // Developer Mode / symlink-privileged test account. All inputs are
        // newly created fixture paths, passed as data rather than shell text.
        use std::os::windows::process::CommandExt;
        let powershell = PathBuf::from(std::env::var_os("SystemRoot").unwrap())
            .join("System32/WindowsPowerShell/v1.0/powershell.exe");
        let output = std::process::Command::new(powershell)
            .args(["-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
                "$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path $env:RO_DIRECTORY_TEST_LINK -Target $env:RO_DIRECTORY_TEST_TARGET | Out-Null"])
            .env("RO_DIRECTORY_TEST_LINK", &link)
            .env("RO_DIRECTORY_TEST_TARGET", &real)
            .creation_flags(0x08000000)
            .output().expect("create owned junction fixture");
        assert!(
            output.status.success(),
            "owned junction fixture could not be created"
        );
        assert!(is_reparse(&std::fs::symlink_metadata(&link).unwrap()));
        assert_eq!(
            validate_existing_directory(link.to_str().unwrap(), &[]),
            Err(PathFailure::Invalid)
        );
        assert_eq!(
            validate_existing_directory(link.join("child").to_str().unwrap(), &[]),
            Err(PathFailure::Invalid)
        );
        std::fs::remove_dir(&link).unwrap();
        assert!(
            real.join("child").is_dir(),
            "validation never changes the target"
        );
    }

    fn selected() -> DirectoryOutcome {
        DirectoryOutcome::Selected {
            path: "C:\\Synthetic selection".into(),
        }
    }

    #[cfg(windows)]
    fn fixture_lock_manager(
        fixture: &Fixture,
        mode: crate::application_lock::SignInMode,
    ) -> (
        crate::application_lock::ApplicationLockManager,
        PathBuf,
        Vec<u8>,
    ) {
        use crate::application_lock::{
            ApplicationLockManager, ApplicationLockState, LockConfigurationState,
        };
        use crate::application_sign_in_policy::{POLICY_FILE, SignInPolicy};
        use std::io::Write;

        // Prepare only an explicit synthetic policy inside our exclusively
        // created and identity-checked fixture. This never invokes a provider,
        // credential store, Core startup, or a current-user application root.
        let security = fixture.0.join("security");
        std::fs::create_dir(&security).unwrap();
        let path = security.join(POLICY_FILE);
        let bytes = SignInPolicy::normalized_target(1, mode, None, 0)
            .unwrap()
            .canonical_bytes()
            .unwrap();
        let mut policy = std::fs::File::create_new(&path).unwrap();
        policy.write_all(&bytes).unwrap();
        policy.sync_all().unwrap();
        drop(policy);
        let manager = ApplicationLockManager::acquire(&fixture.0).unwrap();
        let snapshot = manager.status();
        assert_eq!(snapshot.configuration_state, LockConfigurationState::Valid);
        assert_eq!(snapshot.sign_in_mode, mode);
        assert_eq!(snapshot.inactivity_timeout_minutes, 0);
        assert_eq!(snapshot.state, ApplicationLockState::Unlocked);
        assert!(matches!(
            ApplicationLockManager::acquire(&fixture.0),
            Err("RO-DESKTOP-ALREADY-RUNNING")
        ));
        (manager, path, bytes)
    }

    #[cfg(windows)]
    #[test]
    fn actual_protected_lock_invalidates_ticket_and_cancels_pending_selection() {
        use crate::application_lock::{ApplicationLockReason, ApplicationLockState, SignInMode};

        let fixture = Fixture::new();
        let (lock, policy_path, before) =
            fixture_lock_manager(&fixture, SignInMode::WindowsPassword);
        let ticket = lock.begin_protected_action().unwrap();
        let checking_lock = lock.clone();
        let manager = DirectoryPickerManager::default();
        let worker_manager = manager.clone();
        let (entered_tx, entered_rx) = std::sync::mpsc::channel();
        let (release_tx, release_rx) = std::sync::mpsc::channel();
        let worker = std::thread::spawn(move || {
            worker_manager.run_worker(
                Arc::new(move || checking_lock.finish_protected_action(ticket).is_ok()),
                move |reservation, _| {
                    entered_tx.send(Arc::clone(&reservation.pending)).unwrap();
                    release_rx
                        .recv_timeout(std::time::Duration::from_secs(5))
                        .unwrap();
                    selected()
                },
            )
        });
        let pending = entered_rx
            .recv_timeout(std::time::Duration::from_secs(5))
            .unwrap();
        let (snapshot, changed) = lock.lock(ApplicationLockReason::Manual);
        assert!(changed);
        assert_eq!(snapshot.state, ApplicationLockState::Locked);
        assert_eq!(
            lock.finish_protected_action(ticket),
            Err("RO-APPLICATION-LOCKED")
        );
        assert_eq!(lock.begin_protected_action(), Err("RO-APPLICATION-LOCKED"));
        // This is the same explicit lock-to-picker notification used by the
        // native command composition; the backend is intentionally unshown.
        manager.cancel_pending();
        assert!(pending.cancelled.load(Ordering::Acquire));
        assert!(manager.reserve().is_none());
        release_tx.send(()).unwrap();
        assert_eq!(worker.join().unwrap(), DirectoryOutcome::Cancelled);
        manager.wait_for_cleanup();
        assert!(manager.reserve().is_some());
        assert_eq!(std::fs::read(policy_path).unwrap(), before);
    }

    #[cfg(windows)]
    #[test]
    fn actual_protected_ticket_recheck_discards_late_path_without_cancel_notification() {
        use crate::application_lock::{ApplicationLockReason, SignInMode};

        let fixture = Fixture::new();
        let (lock, policy_path, before) =
            fixture_lock_manager(&fixture, SignInMode::WindowsPassword);
        let ticket = lock.begin_protected_action().unwrap();
        let checking_lock = lock.clone();
        let changing_lock = lock.clone();
        let manager = DirectoryPickerManager::default();
        let result = manager.run_worker(
            Arc::new(move || checking_lock.finish_protected_action(ticket).is_ok()),
            move |reservation, _| {
                assert!(changing_lock.lock(ApplicationLockReason::Manual).1);
                assert!(!reservation.pending.cancelled.load(Ordering::Acquire));
                selected()
            },
        );
        assert_eq!(
            serde_json::to_value(result).unwrap(),
            json!({"status":"cancelled"})
        );
        assert_eq!(
            lock.finish_protected_action(ticket),
            Err("RO-APPLICATION-LOCKED")
        );
        assert!(manager.reserve().is_some());
        assert_eq!(std::fs::read(policy_path).unwrap(), before);
    }

    #[cfg(windows)]
    #[test]
    fn actual_none_mode_manual_lock_is_noop_and_does_not_cancel_pending_selection() {
        use crate::application_lock::{ApplicationLockReason, ApplicationLockState, SignInMode};

        let fixture = Fixture::new();
        let (lock, policy_path, before) = fixture_lock_manager(&fixture, SignInMode::None);
        let ticket = lock.begin_protected_action().unwrap();
        let checking_lock = lock.clone();
        let manager = DirectoryPickerManager::default();
        let worker_manager = manager.clone();
        let (entered_tx, entered_rx) = std::sync::mpsc::channel();
        let (release_tx, release_rx) = std::sync::mpsc::channel();
        let worker = std::thread::spawn(move || {
            worker_manager.run_worker(
                Arc::new(move || checking_lock.finish_protected_action(ticket).is_ok()),
                move |reservation, _| {
                    entered_tx.send(Arc::clone(&reservation.pending)).unwrap();
                    release_rx
                        .recv_timeout(std::time::Duration::from_secs(5))
                        .unwrap();
                    selected()
                },
            )
        });
        let pending = entered_rx
            .recv_timeout(std::time::Duration::from_secs(5))
            .unwrap();
        let (snapshot, changed) = lock.lock(ApplicationLockReason::Manual);
        if changed {
            manager.cancel_pending();
        }
        assert!(
            !changed,
            "disabled application protection must not claim a lock"
        );
        assert_eq!(snapshot.state, ApplicationLockState::Unlocked);
        assert_eq!(lock.finish_protected_action(ticket), Ok(()));
        assert_eq!(lock.begin_protected_action(), Ok(ticket));
        assert!(!pending.cancelled.load(Ordering::Acquire));
        assert!(manager.reserve().is_none());
        release_tx.send(()).unwrap();
        assert_eq!(worker.join().unwrap(), selected());
        manager.wait_for_cleanup();
        assert!(manager.reserve().is_some());
        assert_eq!(std::fs::read(policy_path).unwrap(), before);
    }

    #[test]
    fn admission_survives_cancel_and_releases_only_after_worker_cleanup() {
        let manager = DirectoryPickerManager::default();
        let worker_manager = manager.clone();
        let (entered_tx, entered_rx) = std::sync::mpsc::channel();
        let (release_tx, release_rx) = std::sync::mpsc::channel();
        let worker = std::thread::spawn(move || {
            worker_manager.run_worker(Arc::new(|| true), move |reservation, _| {
                entered_tx.send(Arc::clone(&reservation.pending)).unwrap();
                release_rx.recv().unwrap();
                selected()
            })
        });
        let pending = entered_rx.recv().unwrap();
        manager.cancel_pending();
        assert!(
            pending.cancelled.load(Ordering::Acquire),
            "cancel remains sticky before native window registration"
        );
        assert!(
            manager.reserve().is_none(),
            "cancel does not admit a second dialog"
        );
        release_tx.send(()).unwrap();
        assert_eq!(worker.join().unwrap(), DirectoryOutcome::Cancelled);
        assert!(manager.reserve().is_some(), "cleanup restores admission");
    }

    #[test]
    fn dropping_waiter_does_not_drop_native_reservation_or_result_guard() {
        let manager = DirectoryPickerManager::default();
        let worker_manager = manager.clone();
        let (entered_tx, entered_rx) = std::sync::mpsc::channel();
        let (release_tx, release_rx) = std::sync::mpsc::channel();
        let (finished_tx, finished_rx) = std::sync::mpsc::channel();
        let waiter = std::thread::spawn(move || {
            let result = worker_manager.run_worker(Arc::new(|| true), move |_, _| {
                entered_tx.send(()).unwrap();
                release_rx.recv().unwrap();
                selected()
            });
            finished_tx.send(result).unwrap();
        });
        entered_rx.recv().unwrap();
        drop(waiter);
        manager.cancel_pending();
        assert!(manager.reserve().is_none());
        release_tx.send(()).unwrap();
        assert_eq!(finished_rx.recv().unwrap(), DirectoryOutcome::Cancelled);
        manager.wait_for_cleanup();
        assert!(manager.reserve().is_some());
    }

    #[test]
    fn close_is_single_admission_and_waits_without_holding_worker_locks() {
        let manager = DirectoryPickerManager::default();
        let reservation = manager.reserve().unwrap();
        assert!(matches!(
            manager.begin_close(),
            CloseDisposition::WaitForCleanup
        ));
        assert!(matches!(
            manager.begin_close(),
            CloseDisposition::AlreadyClosing
        ));
        assert!(!manager.is_open());
        assert!(manager.reserve().is_none());
        assert!(reservation.pending.cancelled.load(Ordering::Acquire));
        let waiting_manager = manager.clone();
        let (done_tx, done_rx) = std::sync::mpsc::channel();
        let waiter = std::thread::spawn(move || {
            waiting_manager.wait_for_cleanup();
            done_tx.send(()).unwrap();
        });
        assert!(done_rx.try_recv().is_err());
        drop(reservation);
        done_rx.recv().unwrap();
        waiter.join().unwrap();
        assert!(matches!(manager.begin_close(), CloseDisposition::CloseNow));
        assert!(
            manager.reserve().is_none(),
            "window close never reopens admission"
        );
    }

    #[test]
    fn authority_changes_before_work_and_after_selection_discard_paths() {
        let manager = DirectoryPickerManager::default();
        let checks = Arc::new(AtomicUsize::new(0));
        let checking = Arc::clone(&checks);
        assert_eq!(
            manager.run_worker(
                Arc::new(move || checking.fetch_add(1, Ordering::SeqCst) == 0),
                |_, _| panic!("invalidated before backend")
            ),
            DirectoryOutcome::Cancelled
        );
        assert!(manager.reserve().is_some());

        let generation = Arc::new(AtomicUsize::new(7));
        let checking = Arc::clone(&generation);
        assert_eq!(
            manager.run_worker(
                Arc::new(move || checking.load(Ordering::SeqCst) == 7),
                move |_, _| {
                    // Lock followed by a new unlocked session is not the old authority.
                    generation.store(9, Ordering::SeqCst);
                    selected()
                }
            ),
            DirectoryOutcome::Cancelled
        );
        assert!(manager.reserve().is_some());
    }

    #[test]
    fn errors_and_worker_panics_release_reservation_without_a_path() {
        let manager = DirectoryPickerManager::default();
        for outcome in [
            DirectoryOutcome::Cancelled,
            DirectoryOutcome::Unavailable,
            DirectoryOutcome::Failed,
        ] {
            let expected = serde_json::to_value(&outcome).unwrap();
            assert_eq!(
                serde_json::to_value(manager.run_worker(Arc::new(|| true), move |_, _| outcome))
                    .unwrap(),
                expected
            );
            assert!(manager.reserve().is_some());
        }
        assert_eq!(
            manager.run_worker(Arc::new(|| true), |_, _| panic!("synthetic worker failure")),
            DirectoryOutcome::Failed
        );
        assert!(manager.reserve().is_some());
        assert_eq!(
            manager.run_worker(
                Arc::new(|| panic!("synthetic authority failure")),
                |_, _| selected()
            ),
            DirectoryOutcome::Cancelled
        );
        assert!(manager.reserve().is_some());
    }

    #[test]
    fn poisoned_admission_denies_new_work_but_still_cancels_and_cleans_up() {
        let manager = DirectoryPickerManager::default();
        let reservation = manager.reserve().unwrap();
        let poisoner = manager.clone();
        let _ = std::thread::spawn(move || {
            let _guard = poisoner.shared.0.lock().unwrap();
            panic!("synthetic admission failure");
        })
        .join();
        manager.cancel_pending();
        assert!(reservation.pending.cancelled.load(Ordering::Acquire));
        assert!(manager.reserve().is_none());
        drop(reservation);
        manager.wait_for_cleanup();
        assert!(!manager.is_open());
    }
}
