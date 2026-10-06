//! Windows-only native OLE file-drop boundary for the approved attachment zone.
//! Tauri/Tao and WebView2 stock file-drop surfaces are disabled before show.

use crate::document_attachment::{self, DocumentAttachmentManager};
use crate::import_source::HeldImportSource;
use std::{
    cell::RefCell,
    ffi::OsString,
    os::windows::ffi::OsStringExt,
    path::PathBuf,
    rc::Rc,
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant},
};
use webview2_com::Microsoft::Web::WebView2::Win32::{
    ICoreWebView2Controller, ICoreWebView2Controller4,
};
#[cfg(feature = "integration-harness")]
use windows::Win32::Graphics::Gdi::ClientToScreen;
use windows::Win32::UI::WindowsAndMessaging::IsWindow;
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
    pub(super) static REGISTER: AtomicU64 = AtomicU64::new(0);
    pub(super) static GRAPHICS_REGISTER: AtomicU64 = AtomicU64::new(0);
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
    identity: TargetNode,
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
    topology: Rc<RefCell<DropTopology>>,
    _ole: OleApartment,
}

impl Drop for PendingTargets {
    fn drop(&mut self) {
        for entry in self.entries.drain(..) {
            // Cleanup never revokes a HWND whose current identity/ancestry has
            // changed since registration. The graphics leaf is never an entry.
            if let Ok(topology) = self.topology.try_borrow()
                && cleanup_target_is_owned(&topology, &entry.identity)
            {
                let _ = unsafe { RevokeDragDrop(entry.hwnd) };
            }
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
    topology: Rc<RefCell<DropTopology>>,
}

impl NativeDropTarget {
    fn new(
        parent: HWND,
        controller: ICoreWebView2Controller,
        window: tauri::WebviewWindow,
        manager: DocumentAttachmentManager,
        topology: Rc<RefCell<DropTopology>>,
    ) -> Self {
        Self {
            parent,
            controller,
            window,
            manager,
            probe: Arc::default(),
            topology,
        }
    }

    fn topology_valid(&self) -> bool {
        self.window.hwnd().ok() == Some(self.parent)
            && self
                .topology
                .try_borrow_mut()
                .is_ok_and(|mut topology| revalidate_live(&mut topology).is_ok())
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
        if self.topology_valid()
            && let (Some(operation_id), Some(point)) =
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
        if self.topology_valid()
            && let (Some(operation_id), Some(point)) =
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
        if !self.topology_valid() {
            self.invalidate();
            return Ok(());
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
        if self.manager.armed_drop().as_deref() != Some(&operation_id) || !self.topology_valid() {
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
    (children.len() <= 32).into()
}

fn window_class(hwnd: HWND) -> Option<String> {
    let mut buffer = [0u16; 256];
    let length = unsafe { GetClassNameW(hwnd, &mut buffer) } as usize;
    (length > 0).then(|| String::from_utf16_lossy(&buffer[..length]))
}

#[derive(Clone)]
struct TargetNode {
    hwnd: HWND,
    parent: HWND,
    class: String,
    thread: u32,
    process: u32,
    disabled: bool,
    transparent: bool,
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

#[cfg(feature = "integration-harness")]
fn diagnostic_class(class: &str) -> &'static str {
    match class {
        "WRY_WEBVIEW" => "WRY_WEBVIEW",
        "Chrome_WidgetWin_0" => "Chrome_WidgetWin_0",
        "Chrome_WidgetWin_1" => "Chrome_WidgetWin_1",
        "Chrome_RenderWidgetHostHWND" => "Chrome_RenderWidgetHostHWND",
        "Intermediate D3D Window" => "Intermediate_D3D_Window",
        _ => "other",
    }
}

#[cfg(feature = "integration-harness")]
fn sole_diagnostic_node<'a>(nodes: &'a [TargetNode], class: &str) -> Option<&'a TargetNode> {
    let mut matches = nodes.iter().filter(|node| node.class == class);
    let first = matches.next()?;
    matches.next().is_none().then_some(first)
}

#[cfg(feature = "integration-harness")]
fn diagnostic_parent_chain(
    node: &TargetNode,
    root: HWND,
    nodes: &[TargetNode],
    host: Option<HWND>,
) -> (String, bool) {
    let mut current = node.parent;
    let mut classes = Vec::new();
    for _ in 0..nodes.len().min(32) {
        if current == root {
            classes.push("root");
            return (classes.join(">"), false);
        }
        let Some(parent) = nodes.iter().find(|parent| parent.hwnd == current) else {
            classes.push("unresolved");
            return (classes.join(">"), false);
        };
        classes.push(diagnostic_class(&parent.class));
        if Some(parent.hwnd) == host {
            return (classes.join(">"), true);
        }
        current = parent.parent;
    }
    classes.push("bounded");
    (classes.join(">"), false)
}

#[cfg(feature = "integration-harness")]
fn diagnostic_same_nonzero(value: u32, reference: Option<u32>) -> &'static str {
    match reference {
        Some(other) if value != 0 && other != 0 && value == other => "true",
        Some(other) if value != 0 && other != 0 && value != other => "false",
        _ => "unknown",
    }
}

fn noninteractive_graphics_leaf(
    host: HWND,
    nodes: &[TargetNode],
) -> Result<Option<&TargetNode>, &'static str> {
    let subtree: Vec<&TargetNode> = nodes
        .iter()
        .filter(|node| in_host_subtree(node.hwnd, host, nodes))
        .collect();
    let mut graphics = subtree
        .iter()
        .copied()
        .filter(|node| node.class == "Intermediate D3D Window");
    let Some(leaf) = graphics.next() else {
        return Ok(None);
    };
    let error = "RO-DOCUMENT-WEBVIEW-DROP-CLASS-UNEXPECTED";
    if graphics.next().is_some() || subtree.len() != 5 {
        return Err(error);
    }
    let sole = |class: &str| {
        let mut candidates = subtree.iter().copied().filter(|node| node.class == class);
        let first = candidates.next()?;
        candidates.next().is_none().then_some(first)
    };
    let (Some(wry), Some(widget0), Some(widget1), Some(render)) = (
        sole("WRY_WEBVIEW"),
        sole("Chrome_WidgetWin_0"),
        sole("Chrome_WidgetWin_1"),
        sole("Chrome_RenderWidgetHostHWND"),
    ) else {
        return Err(error);
    };
    if wry.hwnd != host
        || widget0.parent != wry.hwnd
        || widget1.parent != widget0.hwnd
        || render.parent != widget1.hwnd
        || leaf.parent != widget1.hwnd
        || !leaf.disabled
        || !leaf.transparent
        || nodes.iter().any(|node| node.parent == leaf.hwnd)
        || subtree
            .iter()
            .any(|node| node.thread == 0 || node.process == 0)
        || render.thread != widget1.thread
        || render.process != widget1.process
        || leaf.thread == render.thread
        || leaf.process == render.process
    {
        return Err(error);
    }
    // This grants no OLE target to the disabled leaf. Its relationship to the
    // UI root process is deliberately not inferred from renderer observations.
    Ok(Some(leaf))
}

fn same_window_identity(first: &TargetNode, second: &TargetNode) -> bool {
    first.hwnd == second.hwnd
        && first.parent == second.parent
        && first.class == second.class
        && first.thread == second.thread
        && first.process == second.process
}

#[derive(Clone)]
struct DropTopology {
    root: HWND,
    root_class: String,
    ui_thread: u32,
    ui_process: u32,
    interactive: Vec<TargetNode>,
    graphics: Option<TargetNode>,
}

impl DropTopology {
    fn capture(
        root: HWND,
        root_class: String,
        nodes: &[TargetNode],
        ui_thread: u32,
        ui_process: u32,
    ) -> Result<Self, &'static str> {
        let selected = planned_webview_targets(root, nodes, ui_thread, ui_process)?;
        let host = selected
            .first()
            .copied()
            .ok_or("RO-DOCUMENT-WEBVIEW-DROP-TARGET-UNAVAILABLE")?;
        let graphics = noninteractive_graphics_leaf(host, nodes)?.cloned();
        let interactive = selected
            .iter()
            .map(|hwnd| {
                nodes
                    .iter()
                    .find(|node| node.hwnd == *hwnd)
                    .cloned()
                    .ok_or("RO-DOCUMENT-WEBVIEW-DROP-TARGET-UNAVAILABLE")
            })
            .collect::<Result<Vec<_>, _>>()?;
        Ok(Self {
            root,
            root_class,
            ui_thread,
            ui_process,
            interactive,
            graphics,
        })
    }

    fn revalidate(&mut self, nodes: &[TargetNode]) -> Result<(), &'static str> {
        let targets = planned_webview_targets(self.root, nodes, self.ui_thread, self.ui_process)?;
        let error = "RO-DOCUMENT-WEBVIEW-DROP-TOPOLOGY-CHANGED";
        if targets.len() != self.interactive.len()
            || self.interactive.iter().any(|prior| {
                !targets.contains(&prior.hwnd)
                    || !nodes
                        .iter()
                        .any(|current| same_window_identity(prior, current))
            })
        {
            return Err(error);
        }
        let host = self.interactive.first().ok_or(error)?.hwnd;
        let current = noninteractive_graphics_leaf(host, nodes)?;
        match (&self.graphics, current) {
            (Some(prior), Some(current)) if same_window_identity(prior, current) => Ok(()),
            (None, None) => Ok(()),
            (None, Some(current)) => {
                // Natural first appearance binds only the already verified
                // noninteractive role. A later replacement never silently repins.
                self.graphics = Some(current.clone());
                Ok(())
            }
            _ => Err(error),
        }
    }
}

fn relevant_styles(hwnd: HWND) -> Result<(bool, bool), &'static str> {
    use windows::Win32::Foundation::{GetLastError, SetLastError, WIN32_ERROR};
    use windows::Win32::UI::WindowsAndMessaging::{
        GWL_EXSTYLE, GWL_STYLE, GetWindowLongPtrW, WS_DISABLED, WS_EX_TRANSPARENT,
    };
    let read = |index| {
        unsafe {
            SetLastError(WIN32_ERROR(0));
        }
        let value = unsafe { GetWindowLongPtrW(hwnd, index) };
        if value == 0 && unsafe { GetLastError() }.0 != 0 {
            Err("RO-DOCUMENT-WEBVIEW-DROP-TARGET-UNAVAILABLE")
        } else {
            Ok(value as u32)
        }
    };
    Ok((
        read(GWL_STYLE)? & WS_DISABLED.0 != 0,
        read(GWL_EXSTYLE)? & WS_EX_TRANSPARENT.0 != 0,
    ))
}

fn live_node(hwnd: HWND) -> Result<TargetNode, &'static str> {
    let error = "RO-DOCUMENT-WEBVIEW-DROP-TARGET-UNAVAILABLE";
    if !unsafe { IsWindow(Some(hwnd)) }.as_bool() {
        return Err(error);
    }
    let parent = unsafe { GetParent(hwnd) }.map_err(|_| error)?;
    let class = window_class(hwnd).ok_or(error)?;
    let mut process = 0;
    let thread = unsafe { GetWindowThreadProcessId(hwnd, Some(&mut process)) };
    let (disabled, transparent) = relevant_styles(hwnd)?;
    if thread == 0 || process == 0 {
        return Err(error);
    }
    Ok(TargetNode {
        hwnd,
        parent,
        class,
        thread,
        process,
        disabled,
        transparent,
    })
}

fn live_nodes(root: HWND) -> Result<Vec<TargetNode>, &'static str> {
    let mut children: Vec<HWND> = Vec::new();
    // The documented EnumChildWindows return value is unused. The callback
    // bounds collection to 33, and the over-limit sentinel fails closed.
    let _ = unsafe {
        EnumChildWindows(
            Some(root),
            Some(collect_child),
            LPARAM((&mut children as *mut Vec<HWND>) as isize),
        )
    };
    if children.is_empty() || children.len() > 32 {
        return Err("RO-DOCUMENT-WEBVIEW-DROP-TARGET-UNAVAILABLE");
    }
    children.into_iter().map(live_node).collect()
}

fn root_is_owned(root: HWND, class: &str, thread: u32, process: u32) -> bool {
    let mut actual_process = 0;
    unsafe { IsWindow(Some(root)) }.as_bool()
        && window_class(root).as_deref() == Some(class)
        && thread != 0
        && process != 0
        && unsafe { windows_sys::Win32::System::Threading::GetCurrentThreadId() } == thread
        && unsafe { windows_sys::Win32::System::Threading::GetCurrentProcessId() } == process
        && unsafe { GetWindowThreadProcessId(root, Some(&mut actual_process)) } == thread
        && actual_process == process
}

fn revalidate_live(topology: &mut DropTopology) -> Result<Vec<TargetNode>, &'static str> {
    if !root_is_owned(
        topology.root,
        &topology.root_class,
        topology.ui_thread,
        topology.ui_process,
    ) {
        return Err("RO-DOCUMENT-WEBVIEW-DROP-TOPOLOGY-CHANGED");
    }
    let nodes = live_nodes(topology.root)?;
    topology.revalidate(&nodes)?;
    Ok(nodes)
}

fn cleanup_target_is_owned(topology: &DropTopology, target: &TargetNode) -> bool {
    if !root_is_owned(
        topology.root,
        &topology.root_class,
        topology.ui_thread,
        topology.ui_process,
    ) {
        return false;
    }
    let mut current = target.hwnd;
    for _ in 0..=topology.interactive.len() {
        if current == topology.root {
            return true;
        }
        let Some(expected) = topology
            .interactive
            .iter()
            .find(|node| node.hwnd == current)
        else {
            return false;
        };
        let Ok(observed) = live_node(current) else {
            return false;
        };
        if !same_window_identity(expected, &observed) {
            return false;
        }
        current = observed.parent;
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
    let graphics = noninteractive_graphics_leaf(host.hwnd, nodes)?;
    let mut selected = vec![host.hwnd];
    let mut render_host = false;
    for node in nodes {
        if node.hwnd == host.hwnd
            || graphics.is_some_and(|leaf| leaf.hwnd == node.hwnd)
            || !in_host_subtree(node.hwnd, host.hwnd, nodes)
        {
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
    install_internal(window, manager, InstallMode::Normal).map(|_| ())
}

#[derive(Clone, Copy)]
enum InstallMode {
    Normal,
    #[cfg(feature = "integration-harness")]
    Five,
    #[cfg(feature = "integration-harness")]
    FiveExpectedMismatch,
}

fn install_internal(
    window: &tauri::WebviewWindow,
    manager: &DocumentAttachmentManager,
    _mode: InstallMode,
) -> Result<serde_json::Value, &'static str> {
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
                if TARGETS.with(|slot| slot.borrow().is_some()) {
                    return Err("RO-DOCUMENT-WEBVIEW-DROP-ALREADY-INSTALLED");
                }
                let ui_thread = unsafe { windows_sys::Win32::System::Threading::GetCurrentThreadId() };
                let ui_process = unsafe { windows_sys::Win32::System::Threading::GetCurrentProcessId() };
                let root_class = window_class(parent).ok_or("RO-DOCUMENT-DROP-WINDOW-UNAVAILABLE")?;
                if callback_window.hwnd().ok() != Some(parent)
                    || !root_is_owned(parent, &root_class, ui_thread, ui_process)
                    || unsafe { IsWindowVisible(parent) }.as_bool()
                {
                    return Err("RO-DOCUMENT-DROP-WINDOW-UNAVAILABLE");
                }
                let ole = OleApartment::initialize()?;
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
                let nodes = live_nodes(parent)?;
                #[cfg(feature = "integration-harness")]
                {
                    let ui_thread = unsafe { windows_sys::Win32::System::Threading::GetCurrentThreadId() };
                    let ui_process = unsafe { windows_sys::Win32::System::Threading::GetCurrentProcessId() };
                    let host = sole_diagnostic_node(&nodes, "WRY_WEBVIEW");
                    let widget = sole_diagnostic_node(&nodes, "Chrome_WidgetWin_1");
                    let render = sole_diagnostic_node(&nodes, "Chrome_RenderWidgetHostHWND");
                    eprintln!(
                        "RO-DROP-SETUP child-count={} wry-unique={} widget1-unique={} render-unique={}",
                        nodes.len(), host.is_some(), widget.is_some(), render.is_some()
                    );
                    for (index, node) in nodes.iter().take(32).enumerate() {
                        let (parent_index, parent_class) = if node.parent == parent {
                            ("root".to_string(), "root")
                        } else if let Some((parent_index, parent_node)) = nodes
                            .iter()
                            .enumerate()
                            .find(|(_, candidate)| candidate.hwnd == node.parent)
                        {
                            (parent_index.to_string(), diagnostic_class(&parent_node.class))
                        } else {
                            ("unresolved".to_string(), "unresolved")
                        };
                        let (parent_chain, reaches_wry) = diagnostic_parent_chain(
                            node, parent, &nodes, host.map(|node| node.hwnd),
                        );
                        eprintln!(
                            "RO-DROP-SETUP child-index={index} class={} parent-index={parent_index} parent-class={parent_class} parent-chain={parent_chain} reaches-wry={reaches_wry} live={} thread-nonzero={} process-nonzero={} ui-thread={} ui-process={} same-pid-wry={} same-thread-wry={} same-pid-widget1={} same-thread-widget1={} same-pid-render={} same-thread-render={}",
                            diagnostic_class(&node.class), unsafe { IsWindow(Some(node.hwnd)) }.as_bool(),
                            node.thread != 0, node.process != 0,
                            node.thread == ui_thread, node.process == ui_process,
                            diagnostic_same_nonzero(node.process, host.map(|item| item.process)),
                            diagnostic_same_nonzero(node.thread, host.map(|item| item.thread)),
                            diagnostic_same_nonzero(node.process, widget.map(|item| item.process)),
                            diagnostic_same_nonzero(node.thread, widget.map(|item| item.thread)),
                            diagnostic_same_nonzero(node.process, render.map(|item| item.process)),
                            diagnostic_same_nonzero(node.thread, render.map(|item| item.thread)),
                        );
                    }
                }
                let captured = DropTopology::capture(parent, root_class, &nodes, ui_thread, ui_process)?;
                #[cfg(feature = "integration-harness")]
                if matches!(_mode, InstallMode::Five | InstallMode::FiveExpectedMismatch)
                    && (nodes.len() != 5 || captured.graphics.is_none() || captured.interactive.len() != 4)
                {
                    return Err("RO-DOCUMENT-FIVE-NODE-INSTALL-UNAVAILABLE");
                }
                let targets: Vec<HWND> = captured.interactive.iter().map(|node| node.hwnd).collect();
                let topology = Rc::new(RefCell::new(captured));
                let mut installed = PendingTargets {
                    entries: Vec::new(), topology: Rc::clone(&topology), _ole: ole,
                };
                for hwnd in targets {
                    let identity = {
                        let topology = topology.try_borrow_mut().map_err(|_| "RO-DOCUMENT-WEBVIEW-DROP-TOPOLOGY-CHANGED")?;
                        let identity = topology.interactive.iter().find(|node| node.hwnd == hwnd)
                            .ok_or("RO-DOCUMENT-WEBVIEW-DROP-TOPOLOGY-CHANGED")?.clone();
                        if !cleanup_target_is_owned(&topology, &identity) {
                            return Err("RO-DOCUMENT-WEBVIEW-DROP-TOPOLOGY-CHANGED");
                        }
                        identity
                    };
                    match unsafe { RevokeDragDrop(hwnd) } {
                        Ok(()) => {
                            #[cfg(feature = "integration-harness")]
                            eprintln!("RO-DROP-SETUP replaced-target hwnd={}", hwnd.0 as isize);
                        }
                        Err(error) if error.code() == DRAGDROP_E_NOTREGISTERED => {}
                        _ => return Err("RO-DOCUMENT-WEBVIEW-DROP-REVOKE-FAILED"),
                    }
                    let target: IDropTarget = NativeDropTarget::new(
                        parent, controller.clone(), callback_window.clone(), manager.clone(), Rc::clone(&topology),
                    ).into();
                    if let Err(_error) = unsafe { RegisterDragDrop(hwnd, &target) } {
                        #[cfg(feature = "integration-harness")]
                        eprintln!(
                            "RO-DROP-SETUP register-failed hwnd={} hresult=0x{:08X}",
                            hwnd.0 as isize, _error.code().0 as u32
                        );
                        return Err("RO-DOCUMENT-WEBVIEW-DROP-REGISTER-FAILED");
                    }
                    #[cfg(feature = "integration-harness")]
                    observation::increment(&observation::REGISTER);
                    #[cfg(feature = "integration-harness")]
                    if identity.class == "Intermediate D3D Window" {
                        observation::increment(&observation::GRAPHICS_REGISTER);
                    }
                    installed.entries.push(InstalledTarget {
                        hwnd, identity,
                        #[cfg(feature = "integration-harness")]
                        parent,
                        #[cfg(feature = "integration-harness")]
                        controller: controller.clone(),
                        _target: target,
                    });
                }
                let final_nodes = {
                    let mut topology = topology.try_borrow_mut().map_err(|_| "RO-DOCUMENT-WEBVIEW-DROP-TOPOLOGY-CHANGED")?;
                    #[cfg(feature = "integration-harness")]
                    if matches!(_mode, InstallMode::FiveExpectedMismatch) {
                        let graphics = topology.graphics.as_mut().ok_or("RO-DOCUMENT-FIVE-NODE-INSTALL-UNAVAILABLE")?;
                        // Fixture-only expected-identity substitution after the four
                        // actual registrations; no OS window identity is changed.
                        graphics.thread = if graphics.thread == 1 { 2 } else { 1 };
                    }
                    revalidate_live(&mut topology)?
                };
                if unsafe { IsWindowVisible(parent) }.as_bool() {
                    return Err("RO-DOCUMENT-DROP-WINDOW-UNAVAILABLE");
                }
                #[cfg(feature = "integration-harness")]
                if matches!(_mode, InstallMode::Five) && final_nodes.len() != 5 {
                    return Err("RO-DOCUMENT-FIVE-NODE-INSTALL-UNAVAILABLE");
                }
                let observed = serde_json::json!({
                    "initialNodeCount":nodes.len(), "finalNodeCount":final_nodes.len(),
                    "interactiveCount":installed.entries.len(),
                    "graphicsRegisteredCount":installed.entries.iter().filter(|entry| entry.identity.class == "Intermediate D3D Window").count(),
                    "excludedGraphicsCount":topology.try_borrow_mut().map_err(|_| "RO-DOCUMENT-WEBVIEW-DROP-TOPOLOGY-CHANGED")?.graphics.iter().count(),
                    "hidden":!unsafe { IsWindowVisible(parent) }.as_bool(),
                });
                TARGETS.with(|targets| {
                    let mut slot = targets.borrow_mut();
                    if slot.is_some() {
                        return Err("RO-DOCUMENT-WEBVIEW-DROP-ALREADY-INSTALLED");
                    }
                    *slot = Some(installed);
                    Ok(())
                })?;
                Ok(observed)
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

#[cfg(feature = "integration-harness")]
pub(crate) fn five_node_ready(window: &tauri::WebviewWindow) -> Result<bool, &'static str> {
    let root = window
        .hwnd()
        .map_err(|_| "RO-DOCUMENT-DROP-WINDOW-UNAVAILABLE")?;
    TARGETS.with(|slot| {
        let slot = slot.borrow();
        let installed = slot
            .as_ref()
            .ok_or("RO-DOCUMENT-WEBVIEW-DROP-TARGET-UNAVAILABLE")?;
        let mut topology = installed
            .topology
            .try_borrow_mut()
            .map_err(|_| "RO-DOCUMENT-WEBVIEW-DROP-TOPOLOGY-CHANGED")?;
        if root != topology.root {
            return Err("RO-DOCUMENT-WEBVIEW-DROP-TOPOLOGY-CHANGED");
        }
        let nodes = revalidate_live(&mut topology)?;
        Ok(nodes.len() == 5 && topology.graphics.is_some() && topology.interactive.len() == 4)
    })
}

#[cfg(feature = "integration-harness")]
pub(crate) fn exercise_five_node_install(
    window: &tauri::WebviewWindow,
    manager: &DocumentAttachmentManager,
) -> Result<serde_json::Value, &'static str> {
    let error = "RO-DOCUMENT-FIVE-NODE-FIXTURE-UNVERIFIED";
    if manager.installed()
        || !manager.fixture_is_idle()
        || [
            &observation::ENTER,
            &observation::OVER,
            &observation::DROP,
            &observation::HELD,
            &observation::CANDIDATE,
        ]
        .iter()
        .any(|counter| observation::load(counter) != 0)
    {
        return Err(error);
    }
    let warmup = counts();
    let mut unfaulted = TARGETS.with(|slot| {
        let slot = slot.borrow();
        let installed = slot.as_ref().ok_or(error)?;
        let mut topology = installed.topology.try_borrow_mut().map_err(|_| error)?;
        revalidate_live(&mut topology)?;
        if topology.graphics.is_none() || topology.interactive.len() != 4 {
            return Err(error);
        }
        Ok(topology.clone())
    })?;
    if window.hwnd().ok() != Some(unfaulted.root) {
        return Err(error);
    }
    window.hide().map_err(|_| error)?;
    if unsafe { IsWindowVisible(unfaulted.root) }.as_bool() {
        return Err(error);
    }
    // Keep this UI-thread OLE apartment alive across failed-install cleanup and
    // the four independent not-registered probes; initialization stays balanced.
    let _proof_apartment = OleApartment::initialize()?;
    manager.set_installed(false);
    uninstall();
    let registrations_before = observation::load(&observation::REGISTER);
    let graphics_before = observation::load(&observation::GRAPHICS_REGISTER);
    let fault = install_internal(window, manager, InstallMode::FiveExpectedMismatch);
    let fault_registrations =
        observation::load(&observation::REGISTER).saturating_sub(registrations_before);
    let fault_graphics_registrations =
        observation::load(&observation::GRAPHICS_REGISTER).saturating_sub(graphics_before);
    eprintln!(
        "RO-FIVE-FAULT final-recheck={} registrations={fault_registrations} graphics-registrations={fault_graphics_registrations}",
        fault
            .as_ref()
            .err()
            .copied()
            .unwrap_or("unexpected-success")
    );
    if !matches!(fault, Err("RO-DOCUMENT-WEBVIEW-DROP-TOPOLOGY-CHANGED"))
        || fault_registrations != 4
    {
        return Err(error);
    }
    let targets_empty = TARGETS.with(|slot| slot.borrow().is_none());
    let manager_unavailable = !manager.installed() && manager.fixture_is_idle();
    let hidden = !unsafe { IsWindowVisible(unfaulted.root) }.as_bool();
    if !targets_empty || !manager_unavailable || !hidden {
        return Err(error);
    }
    // Retain the actual original identity. The expected-identity fault changes
    // no live window, and the unfaulted graph must still match before probing.
    let final_unfaulted = revalidate_live(&mut unfaulted)?;
    if final_unfaulted.len() != 5 {
        return Err(error);
    }
    let mut verified_revokes = 0;
    let mut graphics_probed = false;
    for node in &unfaulted.interactive {
        if window.hwnd().ok() != Some(unfaulted.root)
            || !cleanup_target_is_owned(&unfaulted, node)
            || unsafe { IsWindowVisible(unfaulted.root) }.as_bool()
            || manager.installed()
            || !manager.fixture_is_idle()
        {
            return Err(error);
        }
        graphics_probed |= unfaulted
            .graphics
            .as_ref()
            .is_some_and(|leaf| leaf.hwnd == node.hwnd);
        match unsafe { RevokeDragDrop(node.hwnd) } {
            Err(result) if result.code() == DRAGDROP_E_NOTREGISTERED => verified_revokes += 1,
            _ => return Err(error),
        }
    }
    let observed = install_internal(window, manager, InstallMode::Five)?;
    // A successful install publishes only the four interactive identities.
    if target_classes().len() != 4 || manager.installed() || !manager.fixture_is_idle() {
        return Err(error);
    }
    Ok(serde_json::json!({
        "kind":"document-drop-probe-five-install", "status":"passed",
        "scope":"actual-five-node-hidden-reinstallation-after-graphics-warmup",
        "installation":observed, "warmupNative":warmup,
        "rollback":{"fault":"one-captured-graphics-thread-identity-substitution",
            "finalRecheckCode":fault.as_ref().err().copied(),
            "ordinaryFinalRecheckDenied":fault.is_err(), "actualRegistrations":fault_registrations,
            "targetsEmpty":targets_empty, "managerUnavailable":manager_unavailable,
            "hidden":hidden, "unfaultedLiveGraphStillMatches":final_unfaulted.len() == 5,
            "interactiveNotRegisteredProbes":verified_revokes,
            "graphicsRegisteredOrProbed":graphics_probed || fault_graphics_registrations != 0
                || observed["graphicsRegisteredCount"].as_u64() != Some(0)},
    }))
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
            disabled: false,
            transparent: false,
        }
    }

    fn observed_five_node_fixture() -> Vec<TargetNode> {
        let mut nodes = vec![
            node(11, 10, "WRY_WEBVIEW", 7, 9),
            node(12, 11, "Chrome_WidgetWin_0", 7, 9),
            node(13, 12, "Chrome_WidgetWin_1", 8, 10),
            node(14, 13, "Chrome_RenderWidgetHostHWND", 8, 10),
            node(15, 13, "Intermediate D3D Window", 11, 12),
        ];
        nodes[3].transparent = true;
        nodes[4].disabled = true;
        nodes[4].transparent = true;
        nodes
    }

    #[test]
    fn disabled_graphics_sibling_has_no_interactive_drop_authority() {
        let nodes = observed_five_node_fixture();
        let targets = planned_webview_targets(hwnd(10), &nodes, 7, 9).unwrap();
        assert_eq!(targets, vec![hwnd(11), hwnd(12), hwnd(13), hwnd(14)]);
        assert!(!targets.contains(&hwnd(15)));
    }

    #[test]
    fn graphics_name_or_transparency_alone_cannot_exclude_an_interactive_target() {
        let reference = observed_five_node_fixture();
        for (disabled, transparent) in [(false, false), (false, true), (true, false)] {
            let mut nodes = reference.clone();
            nodes[4].disabled = disabled;
            nodes[4].transparent = transparent;
            assert!(planned_webview_targets(hwnd(10), &nodes, 7, 9).is_err());
        }
    }

    #[test]
    fn graphics_role_requires_unique_exact_chain_and_measured_owner_relationship() {
        let reference = observed_five_node_fixture();
        for replacement in [
            node(15, 14, "Intermediate D3D Window", 11, 12),
            node(15, 12, "Intermediate D3D Window", 11, 12),
            node(15, 13, "Unknown graphics child", 11, 12),
            node(15, 13, "Intermediate D3D Window", 0, 12),
            node(15, 13, "Intermediate D3D Window", 11, 0),
            node(15, 13, "Intermediate D3D Window", 8, 12),
            node(15, 13, "Intermediate D3D Window", 11, 10),
        ] {
            let mut nodes = reference.clone();
            nodes[4] = replacement;
            nodes[4].disabled = true;
            nodes[4].transparent = true;
            assert!(planned_webview_targets(hwnd(10), &nodes, 7, 9).is_err());
        }
        for additional in [
            node(16, 13, "Intermediate D3D Window", 11, 12),
            node(16, 15, "Chrome_WidgetWin_1", 8, 10),
            node(16, 13, "Chrome_RenderWidgetHostHWND", 8, 10),
            node(16, 12, "Chrome_WidgetWin_1", 8, 10),
            node(16, 11, "Chrome_WidgetWin_0", 7, 9),
            node(16, 13, "Unknown interactive child", 8, 10),
        ] {
            let mut nodes = reference.clone();
            nodes.push(additional);
            assert!(planned_webview_targets(hwnd(10), &nodes, 7, 9).is_err());
        }
        let mut nodes = reference;
        nodes[2].parent = hwnd(11);
        assert!(planned_webview_targets(hwnd(10), &nodes, 7, 9).is_err());
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

    #[cfg(feature = "integration-harness")]
    #[test]
    fn setup_diagnostic_redacts_unknown_class_and_traces_only_bounded_parent_classes() {
        let nodes = vec![
            node(11, 10, "WRY_WEBVIEW", 7, 9),
            node(12, 11, "Chrome_WidgetWin_0", 7, 9),
            node(13, 12, "Chrome_WidgetWin_1", 8, 10),
            node(14, 13, "Chrome_RenderWidgetHostHWND", 8, 10),
            node(15, 14, "Intermediate D3D Window", 8, 10),
        ];
        assert_eq!(diagnostic_class("private-work-title"), "other");
        assert_eq!(
            diagnostic_parent_chain(&nodes[4], hwnd(10), &nodes, Some(hwnd(11))),
            (
                "Chrome_RenderWidgetHostHWND>Chrome_WidgetWin_1>Chrome_WidgetWin_0>WRY_WEBVIEW"
                    .to_string(),
                true
            )
        );
    }

    #[test]
    fn first_graphics_appearance_binds_once_without_granting_a_drop_target() {
        let five = observed_five_node_fixture();
        let four = &five[..4];
        let mut topology = DropTopology::capture(hwnd(10), "root".into(), four, 7, 9).unwrap();
        assert!(topology.graphics.is_none());
        topology.revalidate(four).unwrap();
        topology.revalidate(&five).unwrap();
        assert_eq!(topology.interactive.len(), 4);
        assert_eq!(topology.graphics.as_ref().unwrap().hwnd, hwnd(15));
        let mut replaced = five.clone();
        replaced[4].hwnd = hwnd(16);
        assert!(topology.revalidate(&replaced).is_err());
        assert_eq!(topology.graphics.as_ref().unwrap().hwnd, hwnd(15));
        assert!(topology.revalidate(four).is_err());
    }

    #[test]
    fn live_graphics_identity_or_role_substitution_revokes_admission() {
        let reference = observed_five_node_fixture();
        let topology = DropTopology::capture(hwnd(10), "root".into(), &reference, 7, 9).unwrap();
        for change in 0..7 {
            let mut current = reference.clone();
            match change {
                0 => current[4].hwnd = hwnd(16),
                1 => current[4].parent = hwnd(14),
                2 => current[4].class = "Chrome_WidgetWin_1".into(),
                3 => current[4].thread = 13,
                4 => current[4].process = 14,
                5 => current[4].disabled = false,
                _ => current[4].transparent = false,
            }
            assert!(topology.clone().revalidate(&current).is_err());
        }
        let mut unknown = reference.clone();
        unknown.push(node(16, 13, "unknown-interactive", 8, 10));
        assert!(topology.clone().revalidate(&unknown).is_err());
    }

    #[test]
    fn interactive_identity_changes_deny_and_outside_subtree_retains_no_authority() {
        let reference = observed_five_node_fixture();
        let topology = DropTopology::capture(hwnd(10), "root".into(), &reference, 7, 9).unwrap();
        for index in 0..4 {
            for change in 0..5 {
                let mut current = reference.clone();
                match change {
                    0 => current[index].hwnd = hwnd(100 + index),
                    1 => current[index].parent = hwnd(99),
                    2 => current[index].class = "unknown-interactive".into(),
                    3 => current[index].thread += 20,
                    _ => current[index].process += 20,
                }
                assert!(topology.clone().revalidate(&current).is_err());
            }
        }
        let mut outside = reference.clone();
        outside.push(node(30, 10, "unrelated-root-child", 80, 90));
        topology.clone().revalidate(&outside).unwrap();
        assert_eq!(
            planned_webview_targets(hwnd(10), &outside, 7, 9)
                .unwrap()
                .len(),
            4
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
