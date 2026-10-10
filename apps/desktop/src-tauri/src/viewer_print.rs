//! Windows print-to-file uses an IStream over the create-new held deliverable.
//! The driver receives no destination pathname and cannot replace another file.

use crate::viewer_export::{FAILED, LocalDeliverable};
use std::sync::{Arc, Mutex};
use windows::Win32::System::Com::*;
use windows_core::{Error, HRESULT, Interface, Ref, implement};

fn failure() -> Error {
    Error::from_hresult(HRESULT(0x80030005u32 as i32))
}
struct StreamState {
    output: Option<LocalDeliverable>,
    sealed: bool,
}
#[implement(IStream)]
struct HeldPrintStream {
    state: Arc<Mutex<StreamState>>,
    live: Arc<dyn Fn() -> bool + Send + Sync>,
    #[cfg(test)]
    barrier: Option<Arc<WriteBarrier>>,
}

#[cfg(test)]
struct WriteBarrier {
    entered: std::sync::mpsc::Sender<()>,
    release: Mutex<std::sync::mpsc::Receiver<()>>,
    once: std::sync::atomic::AtomicBool,
}
#[cfg(test)]
thread_local! { static PRINT_TEST_BARRIER: std::cell::RefCell<Option<Arc<WriteBarrier>>> = const { std::cell::RefCell::new(None) }; }

impl HeldPrintStream_Impl {
    fn access<T>(
        &self,
        action: impl FnOnce(&mut LocalDeliverable) -> Result<T, &'static str>,
    ) -> windows_core::Result<T> {
        let mut state = self.state.lock().map_err(|_| failure())?;
        if state.sealed || !(self.live)() {
            return Err(failure());
        }
        action(state.output.as_mut().ok_or_else(failure)?).map_err(|_| failure())
    }
}
impl ISequentialStream_Impl for HeldPrintStream_Impl {
    fn Read(&self, pv: *mut core::ffi::c_void, cb: u32, count: *mut u32) -> HRESULT {
        if !count.is_null() {
            unsafe {
                *count = 0;
            }
        }
        if cb > 1_048_576 || (cb != 0 && pv.is_null()) {
            return failure().code();
        }
        if cb == 0 {
            return HRESULT(0);
        }
        match self.access(|o| {
            o.print_read(unsafe { std::slice::from_raw_parts_mut(pv as *mut u8, cb as usize) })
        }) {
            Ok(n) => {
                if !count.is_null() {
                    unsafe {
                        *count = n as u32;
                    }
                }
                HRESULT(if n < cb as usize { 1 } else { 0 })
            }
            Err(e) => e.code(),
        }
    }
    fn Write(&self, pv: *const core::ffi::c_void, cb: u32, count: *mut u32) -> HRESULT {
        if !count.is_null() {
            unsafe {
                *count = 0;
            }
        }
        if cb > 1_048_576 || (cb != 0 && pv.is_null()) {
            return failure().code();
        }
        if cb == 0 {
            return HRESULT(0);
        }
        match self.access(|o| {
            #[cfg(test)]
            if let Some(barrier) = &self.barrier {
                if !barrier.once.swap(true, std::sync::atomic::Ordering::AcqRel) {
                    barrier.entered.send(()).map_err(|_| FAILED)?;
                    barrier
                        .release
                        .lock()
                        .map_err(|_| FAILED)?
                        .recv_timeout(std::time::Duration::from_secs(10))
                        .map_err(|_| FAILED)?;
                    if !(self.live)() {
                        return Err(FAILED);
                    }
                }
            }
            o.print_write(unsafe { std::slice::from_raw_parts(pv as *const u8, cb as usize) })
        }) {
            Ok(()) => {
                if !count.is_null() {
                    unsafe {
                        *count = cb;
                    }
                }
                HRESULT(0)
            }
            Err(e) => e.code(),
        }
    }
}
impl IStream_Impl for HeldPrintStream_Impl {
    fn Seek(
        &self,
        offset: i64,
        origin: STREAM_SEEK,
        position: *mut u64,
    ) -> windows_core::Result<()> {
        let result = self.access(|o| o.print_seek(offset, origin.0))?;
        if !position.is_null() {
            unsafe {
                *position = result;
            }
        }
        Ok(())
    }
    fn SetSize(&self, size: u64) -> windows_core::Result<()> {
        self.access(|o| o.print_size(size))
    }
    fn CopyTo(
        &self,
        _: Ref<'_, IStream>,
        _: u64,
        _: *mut u64,
        _: *mut u64,
    ) -> windows_core::Result<()> {
        Err(failure())
    }
    fn Commit(&self, _: &STGC) -> windows_core::Result<()> {
        self.access(|_| Ok(()))
    }
    fn Revert(&self) -> windows_core::Result<()> {
        Err(failure())
    }
    fn LockRegion(&self, _: u64, _: u64, _: &LOCKTYPE) -> windows_core::Result<()> {
        Err(failure())
    }
    fn UnlockRegion(&self, _: u64, _: u64, _: u32) -> windows_core::Result<()> {
        Err(failure())
    }
    fn Clone(&self) -> windows_core::Result<IStream> {
        Err(failure())
    }
    fn Stat(&self, info: *mut STATSTG, _: &STATFLAG) -> windows_core::Result<()> {
        if info.is_null() {
            return Err(failure());
        }
        let size = self.access(|o| Ok(o.print_length()))?;
        unsafe {
            *info = STATSTG {
                r#type: STGTY_STREAM.0 as u32,
                cbSize: size,
                grfMode: STGM_READWRITE,
                ..Default::default()
            };
        }
        Ok(())
    }
}

pub(crate) fn print_file(
    printer: &str,
    text: &str,
    output: LocalDeliverable,
    live: Arc<dyn Fn() -> bool + Send + Sync>,
    authorize: &dyn Fn() -> Result<(), &'static str>,
) -> Result<LocalDeliverable, &'static str> {
    use windows::Win32::Graphics::{
        Direct2D::Common::*, Direct2D::*, Direct3D::*, Direct3D11::*, DirectWrite::*, Dxgi::*,
        Imaging::*,
    };
    use windows::Win32::Storage::Xps::Printing::*;
    use windows_core::{PCWSTR, w};
    if text.contains('\0') || text.len() > 65536 || !live() {
        return Err(FAILED);
    }
    let init = unsafe { CoInitializeEx(None, COINIT_MULTITHREADED) };
    if init.is_err() && init != HRESULT(0x80010106u32 as i32) {
        return Err(FAILED);
    }
    struct Apartment(bool);
    impl Drop for Apartment {
        fn drop(&mut self) {
            if self.0 {
                unsafe {
                    CoUninitialize();
                }
            }
        }
    }
    let _apartment = Apartment(init.is_ok());
    let state = Arc::new(Mutex::new(StreamState {
        output: Some(output),
        sealed: false,
    }));
    let stream: IStream = HeldPrintStream {
        state: Arc::clone(&state),
        live: Arc::clone(&live),
        #[cfg(test)]
        barrier: PRINT_TEST_BARRIER.with(|b| b.borrow().clone()),
    }
    .into();
    let result = (|| -> windows_core::Result<()> {
        unsafe {
            let factory: IPrintDocumentPackageTargetFactory = CoCreateInstance(
                &PrintDocumentPackageTargetFactory,
                None,
                CLSCTX_INPROC_SERVER,
            )?;
            let name = crate::viewer_export::wide(printer).map_err(|_| failure())?;
            let target = factory.CreateDocumentPackageTargetForPrintJob(
                PCWSTR(name.as_ptr()),
                w!("Research Observatory permitted quotation"),
                &stream,
                None::<&IStream>,
            )?;
            let result = (|| -> windows_core::Result<()> {
                let mut device = None;
                D3D11CreateDevice(
                    None::<&IDXGIAdapter>,
                    D3D_DRIVER_TYPE_WARP,
                    Default::default(),
                    D3D11_CREATE_DEVICE_BGRA_SUPPORT,
                    None,
                    D3D11_SDK_VERSION,
                    Some(&mut device),
                    None,
                    None,
                )?;
                let dxgi: IDXGIDevice = device.ok_or_else(failure)?.cast()?;
                let d2d = D2D1CreateDevice(&dxgi, None)?;
                let wic: IWICImagingFactory =
                    CoCreateInstance(&CLSID_WICImagingFactory, None, CLSCTX_INPROC_SERVER)?;
                let control = d2d.CreatePrintControl(&wic, &target, None)?;
                // Job setup can block. No source text has entered the printer;
                // resolve exact current Core permission again before AddPage.
                authorize().map_err(|_| failure())?;
                let write: IDWriteFactory = DWriteCreateFactory(DWRITE_FACTORY_TYPE_SHARED)?;
                let format = write.CreateTextFormat(
                    w!("Consolas"),
                    None::<&IDWriteFontCollection>,
                    DWRITE_FONT_WEIGHT_NORMAL,
                    DWRITE_FONT_STYLE_NORMAL,
                    DWRITE_FONT_STRETCH_NORMAL,
                    12.0,
                    w!("en-US"),
                )?;
                let value: Vec<u16> = text.encode_utf16().collect();
                let layout = write.CreateTextLayout(&value, &format, 720.0, 64512.0)?;
                let mut metrics = DWRITE_TEXT_METRICS::default();
                layout.GetMetrics(&mut metrics)?;
                let pages = (metrics.height / 1008.0).ceil().max(1.0) as u32;
                if pages > 64 || metrics.height > 64512.0 || !metrics.height.is_finite() {
                    return Err(failure());
                }
                let context = d2d.CreateDeviceContext(D2D1_DEVICE_CONTEXT_OPTIONS_NONE)?;
                let brush = context.CreateSolidColorBrush(
                    &D2D1_COLOR_F {
                        r: 0.0,
                        g: 0.0,
                        b: 0.0,
                        a: 1.0,
                    },
                    None,
                )?;
                for page in 0..pages {
                    if !live() {
                        target.Cancel()?;
                        return Err(failure());
                    }
                    let list = context.CreateCommandList()?;
                    context.SetTarget(&list);
                    context.BeginDraw();
                    let clip = D2D_RECT_F {
                        left: 48.0,
                        top: 48.0,
                        right: 768.0,
                        bottom: 1056.0,
                    };
                    context.PushAxisAlignedClip(&clip, D2D1_ANTIALIAS_MODE_ALIASED);
                    context.DrawTextLayout(
                        windows_numerics::Vector2 {
                            X: 48.0,
                            Y: 48.0 - page as f32 * 1008.0,
                        },
                        &layout,
                        &brush,
                        D2D1_DRAW_TEXT_OPTIONS_NONE,
                    );
                    context.PopAxisAlignedClip();
                    context.EndDraw(None, None)?;
                    context.SetTarget(None::<&ID2D1Image>);
                    list.Close()?;
                    // Output only enters the unpublished held stream. Final
                    // source revalidation and file publication happen later.
                    control.AddPage(
                        &list,
                        D2D_SIZE_F {
                            width: 816.0,
                            height: 1104.0,
                        },
                        None::<&IStream>,
                        None,
                        None,
                    )?;
                }
                if !live() {
                    target.Cancel()?;
                    return Err(failure());
                }
                control.Close()?;
                Ok(())
            })();
            if result.is_err() {
                let _ = target.Cancel();
            }
            result
        }
    })();
    drop(stream);
    // The mutex waits for any actual Read/Write callback to close. Sealing
    // rejects late callbacks; it is not inferred from a cancellation flag.
    let mut state = state.lock().map_err(|_| FAILED)?;
    state.sealed = true;
    let mut output = state.output.take().ok_or(FAILED)?;
    #[cfg(test)]
    if let Err(error) = &result {
        eprintln!("held-print HRESULT: {:08x}", error.code().0 as u32);
    }
    result.map_err(|_| FAILED)?;
    output.finish_print(&*live)?;
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "requires the installed Windows PDF printer; owned authored synthetic fixture only"]
    fn actual_windows_pdf_print_uses_held_stream_and_retains_source_identity() {
        let operation = "01a123ff-0000-7000-8000-000000000001";
        let directory = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../artifacts/tmp")
            .join(format!(
                "directory-dialog-print-stream-{}",
                std::process::id()
            ));
        std::fs::create_dir(&directory).unwrap();
        let directory = dunce::canonicalize(directory).unwrap();
        let output = LocalDeliverable::create(&directory, operation, "pdf").unwrap();
        let text = "SYNTHETIC permitted quotation — unverified\nSource document revision 01a123ff-0000-7000-8000-000000000002\nAnchor 01a123ff-0000-7000-8000-000000000003\nAuthored test data only.";
        let mut output = print_file(
            "Microsoft Print to PDF",
            text,
            output,
            Arc::new(|| true),
            &|| Ok(()),
        )
        .unwrap();
        output.publish(&|| true).unwrap();
        drop(output);
        let bytes = std::fs::read(directory.join(format!("reader-{operation}.pdf"))).unwrap();
        assert!(bytes.starts_with(b"%PDF-") && bytes.len() < 16_777_216);
        println!(
            "RO-OWNED-PRINT-OUTPUT:{}",
            directory.join(format!("reader-{operation}.pdf")).display()
        );
    }

    #[test]
    #[ignore = "actual Windows PDF callbacks; authored output and lock/cancellation fixture only"]
    fn actual_pdf_stream_lock_and_cancel_reject_delivery_and_keep_callback_ownership() {
        use crate::application_lock::{ApplicationLockManager, ApplicationLockReason};
        use std::sync::atomic::{AtomicBool, Ordering};
        for cancel in [false, true] {
            let directory = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../../artifacts/tmp")
                .join(format!(
                    "directory-dialog-print-interrupted-{}-{cancel}",
                    std::process::id()
                ));
            std::fs::create_dir(&directory).unwrap();
            let directory = dunce::canonicalize(directory).unwrap();
            let policy_root = directory.join("native-policy");
            let store = crate::application_sign_in_policy::PolicyStore::new(&policy_root);
            let loaded = store.initialize();
            let policy = crate::application_sign_in_policy::SignInPolicy::normalized_target(
                2,
                crate::application_lock::SignInMode::WindowsPassword,
                None,
                0,
            )
            .unwrap();
            {
                let _guard = store.lock().unwrap();
                let staged = store.stage(&policy).unwrap();
                store.publish(staged, &loaded.source).unwrap();
            }
            let gate = ApplicationLockManager::new(&policy_root);
            let ticket = gate.begin_protected_action().unwrap();
            let cancelled = Arc::new(AtomicBool::new(false));
            let cancel_flag = Arc::clone(&cancelled);
            let live_gate = gate.clone();
            let live: Arc<dyn Fn() -> bool + Send + Sync> = Arc::new(move || {
                !cancel_flag.load(Ordering::Acquire)
                    && live_gate.finish_protected_action(ticket).is_ok()
            });
            let (entered, ready) = std::sync::mpsc::channel();
            let (release, resume) = std::sync::mpsc::channel();
            let barrier = Arc::new(WriteBarrier {
                entered,
                release: Mutex::new(resume),
                once: AtomicBool::new(false),
            });
            let operation = "01a123ff-0000-7000-8000-000000000005";
            let path = directory.join(format!("reader-{operation}.pdf"));
            let output = LocalDeliverable::create(&directory, operation, "pdf").unwrap();
            let (closed, observed) = std::sync::mpsc::channel();
            let thread = std::thread::spawn(move || {
                PRINT_TEST_BARRIER.with(|b| *b.borrow_mut() = Some(barrier));
                let result = print_file(
                    "Microsoft Print to PDF",
                    "SYNTHETIC revoked quotation; never published",
                    output,
                    live,
                    &|| Ok(()),
                );
                PRINT_TEST_BARRIER.with(|b| *b.borrow_mut() = None);
                assert!(result.is_err());
                closed.send(()).unwrap();
            });
            ready
                .recv_timeout(std::time::Duration::from_secs(10))
                .expect("actual driver Write callback must enter");
            assert!(path.exists());
            assert!(std::fs::OpenOptions::new().write(true).open(&path).is_err());
            if cancel {
                cancelled.store(true, Ordering::Release);
            } else {
                let started = std::time::Instant::now();
                assert!(gate.lock(ApplicationLockReason::Manual).1);
                assert!(started.elapsed() < std::time::Duration::from_secs(1));
            }
            assert!(
                observed.try_recv().is_err(),
                "a cancellation flag is not callback closure"
            );
            assert!(
                path.exists(),
                "owned incomplete output remains held during the callback"
            );
            release.send(()).unwrap();
            observed
                .recv_timeout(std::time::Duration::from_secs(10))
                .unwrap();
            thread.join().unwrap();
            assert!(
                !path.exists(),
                "physical closure deletes unpublished plaintext"
            );
        }
    }

    #[test]
    fn sealed_stream_rejects_late_callbacks_and_cannot_reopen_an_owned_output() {
        let directory = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../artifacts/tmp")
            .join(format!(
                "directory-dialog-print-sealed-{}",
                std::process::id()
            ));
        std::fs::create_dir(&directory).unwrap();
        let directory = dunce::canonicalize(directory).unwrap();
        let operation = "01a123ff-0000-7000-8000-000000000006";
        let path = directory.join(format!("reader-{operation}.pdf"));
        let state = Arc::new(Mutex::new(StreamState {
            output: Some(LocalDeliverable::create(&directory, operation, "pdf").unwrap()),
            sealed: false,
        }));
        let stream: IStream = HeldPrintStream {
            state: Arc::clone(&state),
            live: Arc::new(|| true),
            barrier: None,
        }
        .into();
        {
            let mut owner = state.lock().unwrap();
            owner.sealed = true;
            drop(owner.output.take());
        }
        let text = b"SYNTHETIC late output";
        let mut written = 99;
        assert!(
            unsafe { stream.Write(text.as_ptr() as _, text.len() as u32, Some(&mut written)) }
                .is_err()
        );
        assert_eq!(written, 0);
        assert!(!path.exists());
    }
}
