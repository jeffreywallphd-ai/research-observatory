//! Windows-only native OLE file-drop boundary for the approved attachment zone.
//! Tauri/Tao and WebView2 stock file-drop surfaces are disabled before show.

use crate::document_attachment::{self, DocumentAttachmentManager};
use crate::import_source::HeldImportSource;
use std::{
    cell::RefCell,
    ffi::OsString,
    os::windows::ffi::OsStringExt,
    path::PathBuf,
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant},
};
use webview2_com::Microsoft::Web::WebView2::Win32::{
    ICoreWebView2Controller, ICoreWebView2Controller4,
};
#[cfg(feature = "integration-harness")]
use windows::Win32::Graphics::Gdi::ClientToScreen;
use windows::{
    Win32::{
        Foundation::{DRAGDROP_E_NOTREGISTERED, HWND, LPARAM, POINT, POINTL, RECT},
        Graphics::Gdi::ScreenToClient,
        System::{
            Com::{DVASPECT_CONTENT, FORMATETC, IDataObject, TYMED_HGLOBAL},
            Ole::{
                CF_HDROP, DROPEFFECT, DROPEFFECT_COPY, DROPEFFECT_NONE, IDropTarget,
                IDropTarget_Impl, OleInitialize, OleUninitialize, RegisterDragDrop,
                ReleaseStgMedium, RevokeDragDrop,
            },
            SystemServices::MODIFIERKEYS_FLAGS,
        },
        UI::{
            Shell::{DragQueryFileW, HDROP},
            WindowsAndMessaging::{
                EnumChildWindows, GetClassNameW, GetParent, GetWindowThreadProcessId,
                IsWindowVisible,
            },
        },
    },
    core::{BOOL, Interface, implement},
};

#[cfg(feature = "integration-harness")]
mod observation {
    use std::sync::atomic::{AtomicU64, Ordering};
    pub(super) static ENTER: AtomicU64 = AtomicU64::new(0);
    pub(super) static OVER: AtomicU64 = AtomicU64::new(0);
    pub(super) static DROP: AtomicU64 = AtomicU64::new(0);
    pub(super) static HELD: AtomicU64 = AtomicU64::new(0);
    pub(super) static CANDIDATE: AtomicU64 = AtomicU64::new(0);
    pub(super) fn increment(counter: &AtomicU64) {
        counter.fetch_add(1, Ordering::Relaxed);
    }
    pub(super) fn load(counter: &AtomicU64) -> u64 {
        counter.load(Ordering::Relaxed)
    }
}

#[cfg(feature = "integration-harness")]
pub(crate) fn record_held_stage() {
    observation::increment(&observation::HELD);
}
#[cfg(feature = "integration-harness")]
pub(crate) fn record_candidate() {
    observation::increment(&observation::CANDIDATE);
}
#[cfg(feature = "integration-harness")]
pub(crate) fn counts() -> serde_json::Value {
    serde_json::json!({"oleEnter":observation::load(&observation::ENTER),
        "oleOver":observation::load(&observation::OVER),
        "oleDrop":observation::load(&observation::DROP),
        "heldStage":observation::load(&observation::HELD),
        "candidate":observation::load(&observation::CANDIDATE),
        "scopeAllowed":null,"scopeCheckSupported":false})
}

const ZONE_SELECTOR: &str = "[data-document-native-drop-target=\"true\"]";
// A reflow during this bounded interval may admit a candidate, but cannot
// commit it without explicit human confirmation and a fresh Core check.
// Unknown, expired, moved and changed-operation samples always deny.
const SAMPLE_AGE: Duration = Duration::from_millis(100);
const HOVER_REFRESH: Duration = Duration::from_millis(25);
const HOVER_LIMIT: Duration = Duration::from_secs(30);

struct InstalledTarget {
    hwnd: HWND,
    #[cfg(feature = "integration-harness")]
    parent: HWND,
    #[cfg(feature = "integration-harness")]
    controller: ICoreWebView2Controller,
    _target: IDropTarget,
}

struct OleApartment;

impl OleApartment {
    fn initialize() -> Result<Self, &'static str> {
        // Wry calls CoInitializeEx for its STA, but the OLE drag/drop APIs
        // additionally require OleInitialize on this same UI thread.
        unsafe { OleInitialize(None) }.map_err(|_| "RO-DOCUMENT-OLE-INITIALIZE-FAILED")?;
        Ok(Self)
    }
}

impl Drop for OleApartment {
    fn drop(&mut self) {
        unsafe { OleUninitialize() };
    }
}

struct PendingTargets {
    entries: Vec<InstalledTarget>,
    _ole: OleApartment,
}

impl Drop for PendingTargets {
    fn drop(&mut self) {
        for entry in self.entries.drain(..) {
            let _ = unsafe { RevokeDragDrop(entry.hwnd) };
        }
    }
}

thread_local! {
    static TARGETS: RefCell<Option<PendingTargets>> = const { RefCell::new(None) };
}

#[derive(Default)]
struct ProbeState {
    serial: u64,
    inflight_serial: Option<u64>,
    hover_generation: u64,
    hovering: bool,
    operation_id: Option<String>,
    point: Option<(i32, i32)>,
    result: Option<bool>,
    sampled_at: Option<Instant>,
    requested_at: Option<Instant>,
}

impl ProbeState {
    fn permits(&self, operation_id: &str, point: (i32, i32), now: Instant) -> bool {
        self.operation_id.as_deref() == Some(operation_id)
            && self.point == Some(point)
            && self.result == Some(true)
            && self
                .sampled_at
                .is_some_and(|when| now.saturating_duration_since(when) <= SAMPLE_AGE)
    }

    fn should_probe(&self, operation_id: &str, point: (i32, i32), now: Instant) -> bool {
        // WebView2 does not expose cancellation for an outstanding evaluation.
        // If it never replies, this drag fails closed instead of queuing work.
        if self.inflight_serial.is_some() {
            return false;
        }
        if self.operation_id.as_deref() != Some(operation_id) || self.point != Some(point) {
            return true;
        }
        self.sampled_at
            .is_none_or(|when| now.saturating_duration_since(when) > SAMPLE_AGE / 2)
    }

    fn finish_probe(
        &mut self,
        operation_id: &str,
        point: (i32, i32),
        serial: u64,
        dispatched_at: Instant,
        inside: bool,
        now: Instant,
    ) {
        if self.inflight_serial != Some(serial) {
            return;
        }
        self.inflight_serial = None;
        if self.serial != serial
            || self.operation_id.as_deref() != Some(operation_id)
            || self.point != Some(point)
            || self.requested_at != Some(dispatched_at)
        {
            return;
        }
        self.requested_at = None;
        if now.saturating_duration_since(dispatched_at) > SAMPLE_AGE {
            // A late DOM answer cannot acquire a fresh validity period merely
            // because WebView2 delivered its callback late.
            self.result = None;
            self.sampled_at = None;
        } else {
            self.result = Some(inside);
            self.sampled_at = Some(dispatched_at);
        }
    }

    fn hover_key(&self, generation: u64) -> Option<(String, (i32, i32))> {
        if !self.hovering || self.hover_generation != generation {
            return None;
        }
        Some((self.operation_id.clone()?, self.point?))
    }

    fn begin_hover(&mut self, operation_id: &str, point: (i32, i32)) -> Option<u64> {
        let changed =
            self.operation_id.as_deref() != Some(operation_id) || self.point != Some(point);
        if changed {
            // Keep the single active timer, but invalidate its prior exact
            // point and any callback still pending for that point.
            self.serial = self.serial.wrapping_add(1);
            self.operation_id = Some(operation_id.to_owned());
            self.point = Some(point);
            self.result = None;
            self.sampled_at = None;
            self.requested_at = None;
        }
        if self.hovering {
            return None;
        }
        self.hovering = true;
        self.hover_generation = self.hover_generation.wrapping_add(1);
        Some(self.hover_generation)
    }

    fn invalidate(&mut self) {
        self.serial = self.serial.wrapping_add(1);
        self.hover_generation = self.hover_generation.wrapping_add(1);
        self.hovering = false;
        self.operation_id = None;
        self.point = None;
        self.result = None;
        self.sampled_at = None;
        self.requested_at = None;
        // The physical WebView2 evaluation remains outstanding until its
        // callback arrives. Preserve that token across leave/operation change.
    }

    #[cfg(feature = "integration-harness")]
    fn age_bucket(&self, now: Instant) -> &'static str {
        let Some(sampled_at) = self.sampled_at else {
            return "none";
        };
        let age = now.saturating_duration_since(sampled_at);
        if age <= SAMPLE_AGE / 2 {
            "fresh"
        } else if age <= SAMPLE_AGE {
            "aging"
        } else if age <= SAMPLE_AGE * 3 {
            "expired-short"
        } else {
            "expired-long"
        }
    }

    #[cfg(feature = "integration-harness")]
    fn denial_reason(&self, operation_id: &str, point: (i32, i32), now: Instant) -> &'static str {
        if self.operation_id.as_deref() != Some(operation_id) {
            "cache-operation"
        } else if self.point != Some(point) {
            "cache-point"
        } else if self.result == Some(false) {
            "cache-negative"
        } else if self.result != Some(true) || self.sampled_at.is_none() {
            "cache-unknown"
        } else if self
            .sampled_at
            .is_some_and(|sampled_at| now.saturating_duration_since(sampled_at) > SAMPLE_AGE)
        {
            "cache-expired"
        } else {
            "accepted"
        }
    }
}

#[implement(IDropTarget)]
struct NativeDropTarget {
    parent: HWND,
    controller: ICoreWebView2Controller,
    window: tauri::WebviewWindow,
    manager: DocumentAttachmentManager,
    probe: Arc<Mutex<ProbeState>>,
}

impl NativeDropTarget {
    fn new(
        parent: HWND,
        controller: ICoreWebView2Controller,
        window: tauri::WebviewWindow,
        manager: DocumentAttachmentManager,
    ) -> Self {
        Self {
            parent,
            controller,
            window,
            manager,
            probe: Arc::default(),
        }
    }

    fn css_point(&self, point: &POINTL) -> Option<(i32, i32)> {
        let mut client = POINT {
            x: point.x,
            y: point.y,
        };
        if !unsafe { ScreenToClient(self.parent, &mut client) }.as_bool() {
            return None;
        }
        let mut bounds = RECT::default();
        unsafe { self.controller.Bounds(&mut bounds) }.ok()?;
        let x = client.x.checked_sub(bounds.left)?;
        let y = client.y.checked_sub(bounds.top)?;
        (x >= 0 && y >= 0 && x < bounds.right - bounds.left && y < bounds.bottom - bounds.top)
            .then_some((x, y))
    }

    fn script(point: (i32, i32)) -> String {
        // Only native integer coordinates enter script. The renderer receives
        // no file identity, bytes, Core root, permission, or authority token.
        format!(
            r#"(() => {{ const d = window.devicePixelRatio;
            if (!Number.isFinite(d) || d <= 0) return false;
            const x = {0} / d, y = {1} / d;
            const hit = document.elementFromPoint(x, y);
            const zone = hit && hit.closest('{2}');
            if (!zone || !zone.isConnected) return false;
            const rect = zone.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && x >= rect.left && x < rect.right
                && y >= rect.top && y < rect.bottom;
        }})()"#,
            point.0, point.1, ZONE_SELECTOR
        )
    }

    fn cached(&self, operation_id: &str, point: (i32, i32)) -> bool {
        let Ok(state) = self.probe.lock() else {
            return false;
        };
        state.permits(operation_id, point, Instant::now())
    }

    fn request_probe(
        window: &tauri::WebviewWindow,
        manager: &DocumentAttachmentManager,
        probe: &Arc<Mutex<ProbeState>>,
        operation_id: String,
        point: (i32, i32),
        hover_generation: Option<u64>,
    ) {
        let (serial, dispatched_at) = {
            let Ok(mut state) = probe.lock() else {
                return;
            };
            let now = Instant::now();
            if let Some(generation) = hover_generation
                && state.hover_key(generation).as_ref() != Some(&(operation_id.clone(), point))
            {
                return;
            }
            if !state.should_probe(&operation_id, point, now) {
                return;
            }
            let changed =
                state.operation_id.as_deref() != Some(&operation_id) || state.point != Some(point);
            state.serial = state.serial.wrapping_add(1);
            state.operation_id = Some(operation_id.clone());
            state.point = Some(point);
            if changed {
                state.result = None;
                state.sampled_at = None;
            }
            state.requested_at = Some(now);
            state.inflight_serial = Some(state.serial);
            (state.serial, now)
        };
        let probe_for_callback = Arc::clone(probe);
        let manager_for_callback = manager.clone();
        let operation_for_callback = operation_id.clone();
        if window
            .eval_with_callback(Self::script(point), move |result| {
                let inside = serde_json::from_str::<bool>(&result).unwrap_or(false);
                let still_armed =
                    manager_for_callback.armed_drop().as_deref() == Some(&operation_for_callback);
                if let Ok(mut state) = probe_for_callback.lock() {
                    state.finish_probe(
                        &operation_for_callback,
                        point,
                        serial,
                        dispatched_at,
                        inside && still_armed,
                        Instant::now(),
                    );
                }
            })
            .is_err()
        {
            if let Ok(mut state) = probe.lock() {
                state.finish_probe(
                    &operation_id,
                    point,
                    serial,
                    dispatched_at,
                    false,
                    Instant::now(),
                );
            }
        }
    }

    fn hover_probe(&self, operation_id: String, point: (i32, i32)) {
        let start_generation = {
            let Ok(mut state) = self.probe.lock() else {
                return;
            };
            state.begin_hover(&operation_id, point)
        };
        Self::request_probe(
            &self.window,
            &self.manager,
            &self.probe,
            operation_id,
            point,
            None,
        );
        let Some(generation) = start_generation else {
            return;
        };
        let (window, manager, probe) = (
            self.window.clone(),
            self.manager.clone(),
            Arc::clone(&self.probe),
        );
        let parent_id = self.parent.0 as isize;
        if thread::Builder::new()
            .name("document-drop-hover".into())
            .spawn(move || {
                let deadline = Instant::now() + HOVER_LIMIT;
                loop {
                    thread::sleep(HOVER_REFRESH);
                    let key = probe
                        .lock()
                        .ok()
                        .and_then(|state| state.hover_key(generation));
                    let Some((operation_id, point)) = key else {
                        return;
                    };
                    if Instant::now() >= deadline
                        || !unsafe { IsWindowVisible(HWND(parent_id as *mut _)) }.as_bool()
                    {
                        if let Ok(mut state) = probe.lock()
                            && state.hover_generation == generation
                        {
                            state.invalidate();
                        }
                        return;
                    }
                    if manager.armed_drop().as_deref() != Some(&operation_id) {
                        if let Ok(mut state) = probe.lock()
                            && state.hover_key(generation).as_ref() == Some(&(operation_id, point))
                        {
                            state.invalidate();
                            return;
                        }
                        // The operation or point changed after this tick's
                        // snapshot; the same timer will inspect the new key.
                        continue;
                    }
                    Self::request_probe(
                        &window,
                        &manager,
                        &probe,
                        operation_id,
                        point,
                        Some(generation),
                    );
                }
            })
            .is_err()
        {
            self.invalidate();
        }
    }

    fn invalidate(&self) {
        if let Ok(mut state) = self.probe.lock() {
            state.invalidate();
        }
    }

    fn single_path(data: windows::core::Ref<'_, IDataObject>) -> Option<PathBuf> {
        let format = FORMATETC {
            cfFormat: CF_HDROP.0,
            ptd: std::ptr::null_mut(),
            dwAspect: DVASPECT_CONTENT.0,
            lindex: -1,
            tymed: TYMED_HGLOBAL.0 as u32,
        };
        let mut medium = unsafe { data.as_ref()?.GetData(&format) }.ok()?;
        let path = (|| {
            let hdrop = HDROP(unsafe { medium.u.hGlobal.0 } as _);
            if unsafe { DragQueryFileW(hdrop, u32::MAX, None) } != 1 {
                return None;
            }
            let length = unsafe { DragQueryFileW(hdrop, 0, None) } as usize;
            if length == 0 || length > 32_767 {
                return None;
            }
            let mut wide = vec![0u16; length + 1];
            if unsafe { DragQueryFileW(hdrop, 0, Some(&mut wide)) } as usize != length
                || wide[length] != 0
                || wide[..length].contains(&0)
            {
                return None;
            }
            Some(PathBuf::from(OsString::from_wide(&wide[..length])))
        })();
        unsafe {
            ReleaseStgMedium(&mut medium);
        }
        path
    }
}

#[allow(non_snake_case)]
impl IDropTarget_Impl for NativeDropTarget_Impl {
    fn DragEnter(
        &self,
        _data: windows::core::Ref<'_, IDataObject>,
        _keys: MODIFIERKEYS_FLAGS,
        point: &POINTL,
        effect: *mut DROPEFFECT,
    ) -> windows::core::Result<()> {
        #[cfg(feature = "integration-harness")]
        observation::increment(&observation::ENTER);
        unsafe {
            *effect = DROPEFFECT_NONE;
        }
        if let (Some(operation_id), Some(point)) =
            (self.manager.armed_drop(), self.css_point(point))
        {
            self.hover_probe(operation_id, point);
        } else {
            self.invalidate();
        }
        Ok(())
    }

    fn DragOver(
        &self,
        _keys: MODIFIERKEYS_FLAGS,
        point: &POINTL,
        effect: *mut DROPEFFECT,
    ) -> windows::core::Result<()> {
        #[cfg(feature = "integration-harness")]
        observation::increment(&observation::OVER);
        unsafe {
            *effect = DROPEFFECT_NONE;
        }
        if let (Some(operation_id), Some(point)) =
            (self.manager.armed_drop(), self.css_point(point))
        {
            if self.cached(&operation_id, point) {
                unsafe {
                    *effect = DROPEFFECT_COPY;
                }
            }
            // Refresh a positive sample before its hard expiry while the
            // source remains over the same exact point. A delayed Drop still
            // denies if callbacks stop or the DOM sample does not complete.
            self.hover_probe(operation_id, point);
        } else {
            self.invalidate();
        }
        Ok(())
    }

    fn DragLeave(&self) -> windows::core::Result<()> {
        self.invalidate();
        Ok(())
    }

    fn Drop(
        &self,
        data: windows::core::Ref<'_, IDataObject>,
        _keys: MODIFIERKEYS_FLAGS,
        point: &POINTL,
        effect: *mut DROPEFFECT,
    ) -> windows::core::Result<()> {
        #[cfg(feature = "integration-harness")]
        observation::increment(&observation::DROP);
        unsafe {
            *effect = DROPEFFECT_NONE;
        }
        let Some(operation_id) = self.manager.armed_drop() else {
            #[cfg(feature = "integration-harness")]
            crate::directory_integration_harness::observe_document_drop_decision(
                "not-armed",
                "none",
                false,
            );
            self.invalidate();
            return Ok(());
        };
        let Some(point) = self.css_point(point) else {
            #[cfg(feature = "integration-harness")]
            crate::directory_integration_harness::observe_document_drop_decision(
                "point-unavailable",
                "none",
                false,
            );
            self.invalidate();
            return Ok(());
        };
        let cached = if let Ok(state) = self.probe.lock() {
            let now = Instant::now();
            let permitted = state.permits(&operation_id, point, now);
            #[cfg(feature = "integration-harness")]
            let diagnosis = (
                state.denial_reason(&operation_id, point, now),
                state.age_bucket(now),
                state.inflight_serial.is_some(),
            );
            drop(state);
            #[cfg(feature = "integration-harness")]
            if !permitted {
                crate::directory_integration_harness::observe_document_drop_decision(
                    diagnosis.0,
                    diagnosis.1,
                    diagnosis.2,
                );
            }
            permitted
        } else {
            #[cfg(feature = "integration-harness")]
            crate::directory_integration_harness::observe_document_drop_decision(
                "cache-lock",
                "none",
                false,
            );
            false
        };
        if !cached {
            self.invalidate();
            return Ok(());
        }
        let Some(path) = NativeDropTarget::single_path(data) else {
            #[cfg(feature = "integration-harness")]
            crate::directory_integration_harness::observe_document_drop_decision(
                "source-format",
                "none",
                false,
            );
            self.invalidate();
            return Ok(());
        };
        self.invalidate();
        if self.manager.armed_drop().as_deref() != Some(&operation_id) {
            #[cfg(feature = "integration-harness")]
            crate::directory_integration_harness::observe_document_drop_decision(
                "not-armed",
                "none",
                false,
            );
            return Ok(());
        }
        let Ok(source) = HeldImportSource::open_document_selected(&path) else {
            #[cfg(feature = "integration-harness")]
            crate::directory_integration_harness::observe_document_drop_decision(
                "source-open",
                "none",
                false,
            );
            return Ok(());
        };
        if document_attachment::stage_dropped_source(&self.manager, &self.window, source) {
            // COPY is reported only after the held native source is pinned and
            // staging is admitted for the same live operation.
            #[cfg(feature = "integration-harness")]
            crate::directory_integration_harness::observe_document_drop_decision(
                "accepted", "none", false,
            );
            unsafe {
                *effect = DROPEFFECT_COPY;
            }
        } else {
            #[cfg(feature = "integration-harness")]
            crate::directory_integration_harness::observe_document_drop_decision(
                "stage-admission",
                "none",
                false,
            );
        }
        Ok(())
    }
}

unsafe extern "system" fn collect_child(hwnd: HWND, state: LPARAM) -> BOOL {
    let children = unsafe { &mut *(state.0 as *mut Vec<HWND>) };
    children.push(hwnd);
    true.into()
}

fn window_class(hwnd: HWND) -> Option<String> {
    let mut buffer = [0u16; 256];
    let length = unsafe { GetClassNameW(hwnd, &mut buffer) } as usize;
    (length > 0).then(|| String::from_utf16_lossy(&buffer[..length]))
}

struct TargetNode {
    hwnd: HWND,
    parent: HWND,
    class: String,
    thread: u32,
    process: u32,
}

fn in_host_subtree(hwnd: HWND, host: HWND, nodes: &[TargetNode]) -> bool {
    let mut current = hwnd;
    for _ in 0..=nodes.len() {
        if current == host {
            return true;
        }
        let Some(node) = nodes.iter().find(|node| node.hwnd == current) else {
            return false;
        };
        current = node.parent;
    }
    false
}

fn planned_webview_targets(
    root: HWND,
    nodes: &[TargetNode],
    ui_thread: u32,
    process: u32,
) -> Result<Vec<HWND>, &'static str> {
    if nodes.is_empty() || nodes.len() > 32 {
        return Err("RO-DOCUMENT-WEBVIEW-DROP-TARGET-UNAVAILABLE");
    }
    let mut hosts = nodes.iter().filter(|node| node.class == "WRY_WEBVIEW");
    let host = hosts
        .next()
        .ok_or("RO-DOCUMENT-WEBVIEW-DROP-TARGET-UNAVAILABLE")?;
    if hosts.next().is_some() || host.parent != root {
        return Err("RO-DOCUMENT-WEBVIEW-DROP-TARGET-AMBIGUOUS");
    }
    let mut selected = vec![host.hwnd];
    let mut render_host = false;
    for node in nodes {
        if node.hwnd == host.hwnd || !in_host_subtree(node.hwnd, host.hwnd, nodes) {
            continue;
        }
        if !matches!(
            node.class.as_str(),
            "Chrome_WidgetWin_0" | "Chrome_WidgetWin_1" | "Chrome_RenderWidgetHostHWND"
        ) {
            return Err("RO-DOCUMENT-WEBVIEW-DROP-CLASS-UNEXPECTED");
        }
        render_host |= node.class == "Chrome_RenderWidgetHostHWND";
        selected.push(node.hwnd);
    }
    if !render_host || selected.len() < 2 {
        return Err("RO-DOCUMENT-WEBVIEW-DROP-TARGET-UNAVAILABLE");
    }
    for hwnd in &selected {
        let node = nodes
            .iter()
            .find(|node| node.hwnd == *hwnd)
            .ok_or("RO-DOCUMENT-WEBVIEW-DROP-TARGET-UNAVAILABLE")?;
        if node.thread == 0 || node.process == 0 {
            return Err("RO-DOCUMENT-WEBVIEW-DROP-THREAD-MISMATCH");
        }
        // WebView2 owns the deeper Chromium child windows in another process.
        // The pinned Wry adapter registers OLE targets on every descendant;
        // only our host and its first same-process child must retain UI-thread
        // ownership. Every deeper target is constrained by ancestry/class and
        // must still accept our registration before the main window is shown.
        if matches!(node.class.as_str(), "WRY_WEBVIEW" | "Chrome_WidgetWin_0")
            && (node.thread != ui_thread || node.process != process)
        {
            return Err("RO-DOCUMENT-WEBVIEW-DROP-THREAD-MISMATCH");
        }
    }
    Ok(selected)
}

/// Called synchronously on the UI thread while the main window is hidden.
pub(crate) fn install(
    window: &tauri::WebviewWindow,
    manager: &DocumentAttachmentManager,
) -> Result<(), &'static str> {
    let parent = window
        .hwnd()
        .map_err(|_| "RO-DOCUMENT-DROP-WINDOW-UNAVAILABLE")?;
    let result_cell = Arc::new(Mutex::new(None));
    let completion = Arc::clone(&result_cell);
    let parent_id = parent.0 as isize;
    let (callback_window, manager) = (window.clone(), manager.clone());
    window
        .with_webview(move |platform| {
            let parent = HWND(parent_id as *mut _);
            let result = (|| {
                let ole = OleApartment::initialize()?;
                let mut installed = PendingTargets {
                    entries: Vec::new(),
                    _ole: ole,
                };
                // Tao must not own the parent HWND target. The controlled
                // builder disables it; detect a changed default before show.
                match unsafe { RevokeDragDrop(parent) } {
                    Err(error) if error.code() == DRAGDROP_E_NOTREGISTERED => {}
                    _ => return Err("RO-DOCUMENT-PARENT-DROP-REGISTERED"),
                }
                let controller = platform.controller();
                let controller4 = controller
                    .cast::<ICoreWebView2Controller4>()
                    .map_err(|_| "RO-DOCUMENT-EXTERNAL-DROP-CONTROL-UNAVAILABLE")?;
                unsafe { controller4.SetAllowExternalDrop(false) }
                    .map_err(|_| "RO-DOCUMENT-EXTERNAL-DROP-CONTROL-UNAVAILABLE")?;
                let mut children: Vec<HWND> = Vec::new();
                let _ = unsafe {
                    EnumChildWindows(
                        Some(parent),
                        Some(collect_child),
                        LPARAM((&mut children as *mut Vec<HWND>) as isize),
                    )
                };
                let nodes: Vec<TargetNode> = children.into_iter().map(|hwnd| {
                    let parent = unsafe { GetParent(hwnd) }
                        .map_err(|_| "RO-DOCUMENT-WEBVIEW-DROP-TARGET-UNAVAILABLE")?;
                    let class = window_class(hwnd)
                        .ok_or("RO-DOCUMENT-WEBVIEW-DROP-TARGET-UNAVAILABLE")?;
                    let mut process = 0;
                    let thread = unsafe { GetWindowThreadProcessId(hwnd, Some(&mut process)) };
                    Ok(TargetNode { hwnd, parent, class, thread, process })
                }).collect::<Result<_, &'static str>>()?;
                #[cfg(feature = "integration-harness")]
                {
                    let ui_thread = unsafe { windows_sys::Win32::System::Threading::GetCurrentThreadId() };
                    let ui_process = unsafe { windows_sys::Win32::System::Threading::GetCurrentProcessId() };
                    eprintln!("RO-DROP-SETUP child-count={}", nodes.len());
                    for (index, node) in nodes.iter().take(32).enumerate() {
                        eprintln!(
                            "RO-DROP-SETUP child-index={index} hwnd={} class={} ui-thread={} ui-process={}",
                            node.hwnd.0 as isize, node.class,
                            node.thread == ui_thread, node.process == ui_process
                        );
                    }
                }
                let targets = planned_webview_targets(
                    parent,
                    &nodes,
                    unsafe { windows_sys::Win32::System::Threading::GetCurrentThreadId() },
                    unsafe { windows_sys::Win32::System::Threading::GetCurrentProcessId() },
                )?;
                for hwnd in targets {
                    match unsafe { RevokeDragDrop(hwnd) } {
                        Ok(()) => {
                            #[cfg(feature = "integration-harness")]
                            eprintln!("RO-DROP-SETUP replaced-target hwnd={}", hwnd.0 as isize);
                        }
                        Err(error) if error.code() == DRAGDROP_E_NOTREGISTERED => {}
                        _ => return Err("RO-DOCUMENT-WEBVIEW-DROP-REVOKE-FAILED"),
                    }
                    let target: IDropTarget = NativeDropTarget::new(
                        parent, controller.clone(), callback_window.clone(), manager.clone(),
                    ).into();
                    if let Err(_error) = unsafe { RegisterDragDrop(hwnd, &target) } {
                        #[cfg(feature = "integration-harness")]
                        eprintln!(
                            "RO-DROP-SETUP register-failed hwnd={} hresult=0x{:08X}",
                            hwnd.0 as isize, _error.code().0 as u32
                        );
                        return Err("RO-DOCUMENT-WEBVIEW-DROP-REGISTER-FAILED");
                    }
                    installed.entries.push(InstalledTarget {
                        hwnd,
                        #[cfg(feature = "integration-harness")]
                        parent,
                        #[cfg(feature = "integration-harness")]
                        controller: controller.clone(),
                        _target: target,
                    });
                }
                TARGETS.with(|targets| {
                    let mut slot = targets.borrow_mut();
                    if slot.is_some() {
                        return Err("RO-DOCUMENT-WEBVIEW-DROP-ALREADY-INSTALLED");
                    }
                    *slot = Some(installed);
                    Ok(())
                })?;
                Ok(())
            })();
            if let Ok(mut slot) = completion.lock() {
                *slot = Some(result);
            }
        })
        .map_err(|_| "RO-DOCUMENT-WEBVIEW-DROP-UNAVAILABLE")?;
    // Tauri/Wry dispatches with_webview inline on the setup/UI thread. If
    // this pinned behavior changes, do not wait on that thread or show the
    // window with the native drop boundary in an unknown state.
    result_cell
        .lock()
        .map_err(|_| "RO-DOCUMENT-WEBVIEW-DROP-UNAVAILABLE")?
        .take()
        .ok_or("RO-DOCUMENT-WEBVIEW-DROP-DEFERRED")?
}

pub(crate) fn uninstall() {
    TARGETS.with(|targets| {
        targets.borrow_mut().take();
    });
}

#[cfg(feature = "integration-harness")]
pub(crate) fn screen_point(
    window: &tauri::WebviewWindow,
    css: (f64, f64),
    dpr: f64,
) -> Option<(i32, i32)> {
    if !css.0.is_finite() || !css.1.is_finite() || !dpr.is_finite() || !(0.5..=8.0).contains(&dpr) {
        return None;
    }
    let parent = window.hwnd().ok()?;
    TARGETS.with(|targets| {
        let entries = targets.borrow();
        let entry = entries.as_ref()?.entries.first()?;
        if entry.parent != parent {
            return None;
        }
        let mut bounds = RECT::default();
        unsafe { entry.controller.Bounds(&mut bounds) }.ok()?;
        let x = (css.0 * dpr).round();
        let y = (css.1 * dpr).round();
        if x < 0.0
            || y < 0.0
            || x >= f64::from(bounds.right - bounds.left)
            || y >= f64::from(bounds.bottom - bounds.top)
        {
            return None;
        }
        let mut point = POINT {
            x: bounds.left.checked_add(x as i32)?,
            y: bounds.top.checked_add(y as i32)?,
        };
        if !unsafe { ClientToScreen(parent, &mut point) }.as_bool() {
            return None;
        }
        Some((point.x, point.y))
    })
}

#[cfg(feature = "integration-harness")]
pub(crate) fn target_classes() -> Vec<String> {
    TARGETS.with(|targets| {
        targets
            .borrow()
            .as_ref()
            .into_iter()
            .flat_map(|installed| installed.entries.iter())
            .map(|entry| window_class(entry.hwnd).unwrap_or_default())
            .collect()
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hwnd(value: usize) -> HWND {
        HWND(value as *mut _)
    }

    fn node(value: usize, parent: usize, class: &str, thread: u32, process: u32) -> TargetNode {
        TargetNode {
            hwnd: hwnd(value),
            parent: hwnd(parent),
            class: class.into(),
            thread,
            process,
        }
    }

    #[test]
    fn selects_verified_foreign_webview_leaf_but_denies_unknown_or_cross_tree_nodes() {
        let mut nodes = vec![
            node(11, 10, "WRY_WEBVIEW", 7, 9),
            node(12, 11, "Chrome_WidgetWin_0", 7, 9),
            node(13, 12, "Chrome_WidgetWin_1", 8, 10),
            node(14, 13, "Chrome_RenderWidgetHostHWND", 8, 10),
            node(15, 10, "Chrome_RenderWidgetHostHWND", 8, 10),
        ];
        assert_eq!(
            planned_webview_targets(hwnd(10), &nodes, 7, 9).unwrap(),
            vec![hwnd(11), hwnd(12), hwnd(13), hwnd(14)]
        );
        nodes[1].thread = 8;
        assert_eq!(
            planned_webview_targets(hwnd(10), &nodes, 7, 9),
            Err("RO-DOCUMENT-WEBVIEW-DROP-THREAD-MISMATCH")
        );
        nodes[1].thread = 7;
        nodes[3].class = "UNKNOWN_CHILD".into();
        assert_eq!(
            planned_webview_targets(hwnd(10), &nodes, 7, 9),
            Err("RO-DOCUMENT-WEBVIEW-DROP-CLASS-UNEXPECTED")
        );
        nodes[3].class = "Chrome_RenderWidgetHostHWND".into();
        nodes.push(node(16, 10, "WRY_WEBVIEW", 7, 9));
        assert_eq!(
            planned_webview_targets(hwnd(10), &nodes, 7, 9),
            Err("RO-DOCUMENT-WEBVIEW-DROP-TARGET-AMBIGUOUS")
        );
    }

    #[test]
    fn drop_zone_cache_denies_unknown_stale_operation_and_point() {
        let now = Instant::now();
        let mut state = ProbeState {
            serial: 1,
            inflight_serial: None,
            hover_generation: 0,
            hovering: false,
            operation_id: Some("op-a".into()),
            point: Some((120, 260)),
            result: Some(true),
            sampled_at: Some(now),
            requested_at: None,
        };
        assert!(state.permits("op-a", (120, 260), now));
        assert!(!state.permits("op-b", (120, 260), now));
        assert!(!state.permits("op-a", (121, 260), now));
        assert!(!state.permits(
            "op-a",
            (120, 260),
            now + SAMPLE_AGE + Duration::from_millis(1)
        ));
        state.result = None;
        assert!(!state.permits("op-a", (120, 260), now));
        state.result = Some(false);
        assert!(!state.permits("op-a", (120, 260), now));
    }

    #[test]
    fn still_hovering_requests_fresh_sample_before_hard_drop_expiry() {
        let now = Instant::now();
        let mut state = ProbeState {
            serial: 1,
            inflight_serial: None,
            hover_generation: 0,
            hovering: false,
            operation_id: Some("op-a".into()),
            point: Some((120, 260)),
            result: Some(true),
            sampled_at: Some(now),
            requested_at: None,
        };
        assert!(!state.should_probe("op-a", (120, 260), now + Duration::from_millis(49)));
        assert!(state.should_probe("op-a", (120, 260), now + Duration::from_millis(51)));
        state.requested_at = Some(now + Duration::from_millis(51));
        state.inflight_serial = Some(state.serial);
        // A pending refresh retains the original positive sample only until
        // its original hard expiry, then fails closed without a new callback.
        assert!(state.permits("op-a", (120, 260), now + Duration::from_millis(52)));
        assert!(!state.should_probe("op-a", (120, 260), now + Duration::from_millis(52)));
        assert!(!state.permits("op-a", (120, 260), now + Duration::from_millis(101)));
        // A completed fresh DOM sample permits the delayed same-point Drop.
        state.sampled_at = Some(now + Duration::from_millis(60));
        state.requested_at = None;
        state.inflight_serial = None;
        assert!(state.permits("op-a", (120, 260), now + Duration::from_millis(121)));
        assert!(!state.permits("op-a", (120, 260), now + Duration::from_millis(161)));
        assert!(state.should_probe("op-a", (121, 260), now + Duration::from_millis(61)));
    }

    #[test]
    fn slow_same_point_dom_query_is_not_superseded_before_hard_timeout() {
        let now = Instant::now();
        let state = ProbeState {
            serial: 1,
            inflight_serial: Some(1),
            hover_generation: 0,
            hovering: false,
            operation_id: Some("op-a".into()),
            point: Some((120, 260)),
            result: None,
            sampled_at: None,
            requested_at: Some(now),
        };
        assert!(!state.should_probe("op-a", (120, 260), now + Duration::from_millis(51)));
        assert!(!state.should_probe("op-a", (120, 260), now + Duration::from_millis(101)));
        assert!(!state.should_probe("op-b", (120, 260), now + Duration::from_millis(51)));
        assert!(!state.should_probe("op-a", (121, 260), now + Duration::from_millis(51)));
    }

    #[test]
    fn dom_callback_is_bound_to_dispatch_time_exact_key_and_active_hover_generation() {
        let now = Instant::now();
        let mut state = ProbeState {
            serial: 7,
            inflight_serial: Some(7),
            hover_generation: 3,
            hovering: true,
            operation_id: Some("op-a".into()),
            point: Some((120, 260)),
            result: None,
            sampled_at: None,
            requested_at: Some(now),
        };
        assert_eq!(state.hover_key(3), Some(("op-a".into(), (120, 260))));
        assert_eq!(state.hover_key(2), None);
        assert_eq!(state.begin_hover("op-a", (120, 260)), None);
        state.finish_probe(
            "op-a",
            (120, 260),
            7,
            now,
            true,
            now + Duration::from_millis(70),
        );
        assert_eq!(state.sampled_at, Some(now));
        assert!(state.permits("op-a", (120, 260), now + Duration::from_millis(80)));
        assert!(!state.permits("op-a", (120, 260), now + Duration::from_millis(101)));
        state.requested_at = Some(now + Duration::from_millis(80));
        state.serial = 8;
        state.inflight_serial = Some(8);
        state.finish_probe(
            "op-a",
            (120, 260),
            8,
            now + Duration::from_millis(80),
            true,
            now + Duration::from_millis(181),
        );
        assert_eq!(state.sampled_at, None);
        assert!(!state.permits("op-a", (120, 260), now + Duration::from_millis(181)));
        state.invalidate();
        assert_eq!(state.hover_key(3), None);
        assert!(!state.permits("op-a", (120, 260), now + Duration::from_millis(80)));
    }

    #[test]
    fn changed_hover_point_reuses_one_timer_but_revokes_prior_exact_key() {
        let mut state = ProbeState {
            serial: 4,
            inflight_serial: None,
            hover_generation: 7,
            hovering: true,
            operation_id: Some("op-a".into()),
            point: Some((120, 260)),
            result: Some(true),
            sampled_at: Some(Instant::now()),
            requested_at: None,
        };
        assert_eq!(state.begin_hover("op-a", (121, 260)), None);
        assert_eq!(state.hover_key(7), Some(("op-a".into(), (121, 260))));
        assert!(!state.permits("op-a", (120, 260), Instant::now()));
        state.invalidate();
        assert_eq!(state.hover_key(7), None);
    }

    #[test]
    fn leave_and_new_operation_wait_for_old_physical_dom_callback() {
        let start = Instant::now();
        let mut state = ProbeState {
            serial: 1,
            inflight_serial: Some(1),
            hover_generation: 1,
            hovering: true,
            operation_id: Some("op-a".into()),
            point: Some((120, 260)),
            result: None,
            sampled_at: None,
            requested_at: Some(start),
        };
        state.invalidate();
        assert_eq!(state.inflight_serial, Some(1));
        let next = state.begin_hover("op-b", (121, 260)).unwrap();
        assert_eq!(state.hover_key(next), Some(("op-b".into(), (121, 260))));
        assert!(!state.should_probe("op-b", (121, 260), start + SAMPLE_AGE * 2));
        state.finish_probe("op-a", (120, 260), 1, start, true, start + SAMPLE_AGE * 2);
        assert_eq!(state.inflight_serial, None);
        assert!(!state.permits("op-b", (121, 260), start + SAMPLE_AGE * 2));
        assert!(state.should_probe("op-b", (121, 260), start + SAMPLE_AGE * 2));
    }

    #[test]
    fn stationary_hover_refreshes_before_drop_without_extending_sample_lifetime() {
        let start = Instant::now();
        let mut state = ProbeState {
            serial: 1,
            inflight_serial: None,
            hover_generation: 1,
            hovering: true,
            operation_id: Some("op-a".into()),
            point: Some((120, 260)),
            result: Some(true),
            sampled_at: Some(start),
            requested_at: None,
        };
        assert!(!state.should_probe("op-a", (120, 260), start + HOVER_REFRESH));
        assert!(!state.should_probe("op-a", (120, 260), start + HOVER_REFRESH * 2));
        let refresh = start + HOVER_REFRESH * 3;
        assert!(state.should_probe("op-a", (120, 260), refresh));
        state.serial += 1;
        state.requested_at = Some(refresh);
        state.inflight_serial = Some(state.serial);
        state.finish_probe(
            "op-a",
            (120, 260),
            2,
            refresh,
            true,
            start + Duration::from_millis(85),
        );
        assert!(state.permits("op-a", (120, 260), start + Duration::from_millis(120)));
        assert!(!state.permits("op-a", (120, 260), start + Duration::from_millis(176)));
    }

    #[cfg(feature = "integration-harness")]
    #[test]
    fn drop_denial_diagnostic_matches_exact_cache_admission_without_identity_data() {
        let now = Instant::now();
        let mut state = ProbeState::default();
        assert_eq!(
            state.denial_reason("op-a", (120, 260), now),
            "cache-operation"
        );
        assert_eq!(state.age_bucket(now), "none");
        state.operation_id = Some("op-a".into());
        assert_eq!(state.denial_reason("op-a", (120, 260), now), "cache-point");
        state.point = Some((120, 260));
        state.requested_at = Some(now);
        assert_eq!(
            state.denial_reason("op-a", (120, 260), now),
            "cache-unknown"
        );
        state.result = Some(false);
        assert_eq!(
            state.denial_reason("op-a", (120, 260), now),
            "cache-negative"
        );
        state.result = Some(true);
        state.sampled_at = Some(now);
        assert!(state.permits("op-a", (120, 260), now));
        assert_eq!(state.denial_reason("op-a", (120, 260), now), "accepted");
        assert_eq!(state.age_bucket(now), "fresh");
        let later = now + Duration::from_millis(120);
        assert!(!state.permits("op-a", (120, 260), later));
        assert_eq!(
            state.denial_reason("op-a", (120, 260), later),
            "cache-expired"
        );
        assert_eq!(state.age_bucket(later), "expired-short");
        assert_eq!(
            state.age_bucket(now + Duration::from_millis(301)),
            "expired-long"
        );
    }
}
