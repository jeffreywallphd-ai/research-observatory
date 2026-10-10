//! Explicit local deliverables. Incomplete plaintext is deleted by the held
//! Windows handle, including process termination. No hidden Reader cache.

use sha2::{Digest, Sha256};
use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::windows::fs::OpenOptionsExt;
use std::os::windows::io::AsRawHandle;
use std::path::{Path, PathBuf};
use windows_sys::Win32::Foundation::{GENERIC_READ, GENERIC_WRITE};
use windows_sys::Win32::Storage::FileSystem::{
    DELETE, FILE_DISPOSITION_INFO, FILE_FLAG_OPEN_REPARSE_POINT, FileDispositionInfo,
    SetFileInformationByHandle,
};

pub(crate) const FAILED: &str = "RO-VIEWER-ACTION-UNAVAILABLE";

pub(crate) fn wide(value: &str) -> Result<Vec<u16>, &'static str> {
    if value.contains('\0') {
        return Err(FAILED);
    }
    Ok(value.encode_utf16().chain(Some(0)).collect())
}

pub(crate) struct LocalDeliverable {
    file: File,
    _directories: Vec<File>,
    path: PathBuf,
    digest: Sha256,
    bytes: u64,
    verified: bool,
    published: bool,
}

impl LocalDeliverable {
    pub(crate) fn create(
        directory: &Path,
        operation: &str,
        extension: &str,
    ) -> Result<Self, &'static str> {
        if !crate::supervisor::canonical_uuid_v7(operation)
            || !matches!(extension, "json" | "pdf" | "txt" | "xml" | "html" | "docx")
        {
            return Err(FAILED);
        }
        let directories = crate::import_source::pin_directory(directory).map_err(|_| FAILED)?;
        let path = directory.join(format!("reader-{operation}.{extension}"));
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .access_mode(GENERIC_READ | GENERIC_WRITE | DELETE)
            .share_mode(0)
            .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
            .open(&path)
            .map_err(|_| FAILED)?;
        let mut result = Self {
            file,
            _directories: directories,
            path,
            digest: Sha256::new(),
            bytes: 0,
            verified: false,
            published: false,
        };
        // This is deliberately NOT FILE_FLAG_DELETE_ON_CLOSE: that flag cannot
        // be cleared at the explicit publication boundary.
        if result.disposition(true).is_err() {
            drop(result);
            // No content has been written. The newly created empty file may
            // remain when Windows refuses disposition; never write into it.
            return Err(FAILED);
        }
        Ok(result)
    }

    fn disposition(&mut self, delete: bool) -> Result<(), &'static str> {
        let info = FILE_DISPOSITION_INFO { DeleteFile: delete };
        let ok = unsafe {
            SetFileInformationByHandle(
                self.file.as_raw_handle(),
                FileDispositionInfo,
                &info as *const _ as *const _,
                std::mem::size_of_val(&info) as u32,
            )
        };
        (ok != 0).then_some(()).ok_or(FAILED)
    }

    pub(crate) fn append(
        &mut self,
        bytes: &[u8],
        current: &dyn Fn() -> bool,
    ) -> Result<(), &'static str> {
        if self.published
            || !current()
            || bytes.len() > 1_048_576
            || self.bytes + bytes.len() as u64 > 134_217_728
        {
            return Err(FAILED);
        }
        self.verified = false;
        self.file.write_all(bytes).map_err(|_| FAILED)?;
        self.digest.update(bytes);
        self.bytes += bytes.len() as u64;
        Ok(())
    }

    pub(crate) fn verify(
        &mut self,
        expected: &str,
        length: u64,
        current: &dyn Fn() -> bool,
    ) -> Result<(), &'static str> {
        if self.published
            || !current()
            || length != self.bytes
            || length == 0
            || format!("{:x}", self.digest.clone().finalize()) != expected
        {
            return Err(FAILED);
        }
        self.file.flush().map_err(|_| FAILED)?;
        self.file.sync_all().map_err(|_| FAILED)?;
        self.file.seek(SeekFrom::Start(0)).map_err(|_| FAILED)?;
        let mut digest = Sha256::new();
        let mut bytes = [0u8; 65536];
        let mut count = 0u64;
        loop {
            if !current() {
                return Err(FAILED);
            }
            let read = self.file.read(&mut bytes).map_err(|_| FAILED)?;
            if read == 0 {
                break;
            }
            count += read as u64;
            if count > length {
                return Err(FAILED);
            }
            digest.update(&bytes[..read]);
        }
        if count != length || format!("{:x}", digest.finalize()) != expected {
            return Err(FAILED);
        }
        self.verified = true;
        Ok(())
    }

    pub(crate) fn publish(&mut self, current: &dyn Fn() -> bool) -> Result<(), &'static str> {
        if self.published || !self.verified || !current() {
            return Err(FAILED);
        }
        self.disposition(false)?;
        self.published = true;
        Ok(())
    }

    pub(crate) fn into_external_file(self) -> Result<(File, Vec<File>, PathBuf), &'static str> {
        if !self.published {
            return Err(FAILED);
        }
        let path = self.path.clone();
        let guards = self._directories;
        // Close the exclusive writer, then reopen only for read. Directory pins
        // and a digest check protect dispatch; the authorized local deliverable
        // remains outside the project after handoff.
        drop(self.file);
        let file = OpenOptions::new()
            .read(true)
            .share_mode(1)
            .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
            .open(&path)
            .map_err(|_| FAILED)?;
        let metadata = file.metadata().map_err(|_| FAILED)?;
        if !metadata.is_file()
            || metadata.len() != self.bytes
            || crate::directory_picker::is_reparse(&metadata)
        {
            return Err(FAILED);
        }
        Ok((file, guards, path))
    }

    // The print subsystem receives this held stream, never a pathname. Its
    // bounded seek/write interface cannot overwrite a researcher-owned file.
    pub(crate) fn print_write(&mut self, bytes: &[u8]) -> Result<(), &'static str> {
        if self.published || bytes.len() > 1_048_576 {
            return Err(FAILED);
        }
        let position = self.file.stream_position().map_err(|_| FAILED)?;
        if position + bytes.len() as u64 > 16_777_216 {
            return Err(FAILED);
        }
        self.file.write_all(bytes).map_err(|_| FAILED)?;
        self.bytes = self.bytes.max(position + bytes.len() as u64);
        self.verified = false;
        Ok(())
    }
    pub(crate) fn print_seek(&mut self, offset: i64, origin: u32) -> Result<u64, &'static str> {
        let position = match origin {
            0 => u64::try_from(offset).ok(),
            1 => self
                .file
                .stream_position()
                .ok()
                .and_then(|p| p.checked_add_signed(offset)),
            2 => self.bytes.checked_add_signed(offset),
            _ => None,
        }
        .filter(|p| *p <= 16_777_216)
        .ok_or(FAILED)?;
        self.file
            .seek(SeekFrom::Start(position))
            .map_err(|_| FAILED)
    }
    pub(crate) fn print_size(&mut self, size: u64) -> Result<(), &'static str> {
        if self.published || size > 16_777_216 {
            return Err(FAILED);
        }
        self.file.set_len(size).map_err(|_| FAILED)?;
        self.bytes = size;
        self.verified = false;
        Ok(())
    }
    pub(crate) fn print_read(&mut self, bytes: &mut [u8]) -> Result<usize, &'static str> {
        if bytes.len() > 1_048_576 {
            return Err(FAILED);
        }
        self.file.read(bytes).map_err(|_| FAILED)
    }
    pub(crate) fn print_length(&self) -> u64 {
        self.bytes
    }
    pub(crate) fn finish_print(&mut self, current: &dyn Fn() -> bool) -> Result<(), &'static str> {
        self.file.flush().map_err(|_| FAILED)?;
        self.file.sync_all().map_err(|_| FAILED)?;
        if self.bytes < 16
            || self.bytes > 16_777_216
            || self.file.metadata().map_err(|_| FAILED)?.len() != self.bytes
        {
            return Err(FAILED);
        }
        self.file.seek(SeekFrom::Start(0)).map_err(|_| FAILED)?;
        let mut head = [0u8; 5];
        self.file.read_exact(&mut head).map_err(|_| FAILED)?;
        if &head != b"%PDF-" {
            return Err(FAILED);
        }
        self.file
            .seek(SeekFrom::End(-((self.bytes.min(1024)) as i64)))
            .map_err(|_| FAILED)?;
        let mut tail = vec![0u8; self.bytes.min(1024) as usize];
        self.file.read_exact(&mut tail).map_err(|_| FAILED)?;
        if !tail.windows(5).any(|w| w == b"%%EOF") {
            return Err(FAILED);
        }
        self.file.seek(SeekFrom::Start(0)).map_err(|_| FAILED)?;
        let mut sha = Sha256::new();
        let mut buffer = [0u8; 65536];
        let mut count = 0u64;
        loop {
            if !current() {
                return Err(FAILED);
            }
            let n = self.file.read(&mut buffer).map_err(|_| FAILED)?;
            if n == 0 {
                break;
            }
            count += n as u64;
            if count > self.bytes {
                return Err(FAILED);
            }
            sha.update(&buffer[..n]);
        }
        if count != self.bytes {
            return Err(FAILED);
        }
        self.digest = sha;
        self.verified = true;
        Ok(())
    }
}

pub(crate) fn copy_quotation(
    owner: isize,
    text: &str,
    current: &dyn Fn() -> bool,
) -> Result<(), &'static str> {
    use windows_sys::Win32::Foundation::GlobalFree;
    use windows_sys::Win32::System::DataExchange::{
        CloseClipboard, EmptyClipboard, OpenClipboard, RegisterClipboardFormatW, SetClipboardData,
    };
    use windows_sys::Win32::System::Memory::{
        GMEM_MOVEABLE, GlobalAlloc, GlobalLock, GlobalUnlock,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::IsWindow;
    let content = wide(text)?;
    if content.len() > 32768 || !current() || unsafe { IsWindow(owner as _) } == 0 {
        return Err(FAILED);
    }
    unsafe {
        if OpenClipboard(owner as _) == 0 {
            return Err(FAILED);
        }
        struct Close;
        impl Drop for Close {
            fn drop(&mut self) {
                unsafe {
                    CloseClipboard();
                }
            }
        }
        let _close = Close;
        // No researcher clipboard is read, retained or restored. Windows owns
        // successful allocations; failed allocations are released locally.
        let set = |format, bytes: &[u8]| -> Result<(), &'static str> {
            let memory = GlobalAlloc(GMEM_MOVEABLE, bytes.len());
            if memory.is_null() {
                return Err(FAILED);
            }
            let target = GlobalLock(memory);
            if target.is_null() {
                GlobalFree(memory);
                return Err(FAILED);
            }
            std::ptr::copy_nonoverlapping(bytes.as_ptr(), target as *mut u8, bytes.len());
            GlobalUnlock(memory);
            if SetClipboardData(format, memory).is_null() {
                GlobalFree(memory);
                return Err(FAILED);
            }
            Ok(())
        };
        if !current() || EmptyClipboard() == 0 {
            return Err(FAILED);
        }
        for name in [
            "ExcludeClipboardContentFromMonitorProcessing",
            "CanIncludeInClipboardHistory",
            "CanUploadToCloudClipboard",
        ] {
            let name = wide(name)?;
            let format = RegisterClipboardFormatW(name.as_ptr());
            if format == 0 {
                return Err(FAILED);
            }
            set(format, &0u32.to_le_bytes())?;
        }
        if !current() {
            return Err(FAILED);
        }
        let bytes = std::slice::from_raw_parts(content.as_ptr() as *const u8, content.len() * 2);
        set(13, bytes) // CF_UNICODETEXT, after every privacy marker succeeds.
    }
}

/// A local executable is chosen by the researcher in an owned Native dialog.
/// Paths never arrive from, or return to, the renderer.
pub(crate) struct HeldApplication {
    path: PathBuf,
    _file: File,
    _directories: Vec<File>,
}

impl HeldApplication {
    pub(crate) fn hold(path: PathBuf) -> Result<Self, &'static str> {
        if !crate::directory_picker::local_path_syntax(path.to_str().ok_or(FAILED)?)
            || path
                .extension()
                .is_none_or(|e| !e.eq_ignore_ascii_case("exe"))
        {
            return Err(FAILED);
        }
        let directories = crate::import_source::pin_directory(path.parent().ok_or(FAILED)?)
            .map_err(|_| FAILED)?;
        let file = OpenOptions::new()
            .read(true)
            .share_mode(1)
            .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
            .open(&path)
            .map_err(|_| FAILED)?;
        let metadata = file.metadata().map_err(|_| FAILED)?;
        if !metadata.is_file() || crate::directory_picker::is_reparse(&metadata) {
            return Err(FAILED);
        }
        Ok(Self {
            path,
            _file: file,
            _directories: directories,
        })
    }
}

pub(crate) fn choose_application(
    owner: isize,
    current: &dyn Fn() -> bool,
) -> Result<HeldApplication, &'static str> {
    use windows_sys::Win32::UI::Controls::Dialogs::{
        GetOpenFileNameW, OFN_DONTADDTORECENT, OFN_ENABLEHOOK, OFN_FILEMUSTEXIST, OFN_NOCHANGEDIR,
        OFN_PATHMUSTEXIST, OPENFILENAMEW,
    };
    let lifetime = DialogLifetime { current };
    let title = wide("Choose a local application to open the retained original")?;
    let filter: Vec<u16> = "Local applications\0*.exe\0\0".encode_utf16().collect();
    let mut path = [0u16; 4096];
    let mut dialog: OPENFILENAMEW = unsafe { std::mem::zeroed() };
    dialog.lStructSize = std::mem::size_of_val(&dialog) as u32;
    dialog.hwndOwner = owner as _;
    dialog.lpstrTitle = title.as_ptr();
    dialog.lpstrFilter = filter.as_ptr();
    dialog.lpstrFile = path.as_mut_ptr();
    dialog.nMaxFile = path.len() as u32;
    dialog.Flags = OFN_FILEMUSTEXIST
        | OFN_PATHMUSTEXIST
        | OFN_DONTADDTORECENT
        | OFN_NOCHANGEDIR
        | OFN_ENABLEHOOK;
    dialog.lCustData = &lifetime as *const _ as isize;
    dialog.lpfnHook = Some(application_hook);
    if !current() || unsafe { GetOpenFileNameW(&mut dialog) } == 0 || !current() {
        return Err("RO-VIEWER-ACTION-CANCELLED");
    }
    let length = path.iter().position(|c| *c == 0).ok_or(FAILED)?;
    let path = PathBuf::from(String::from_utf16(&path[..length]).map_err(|_| FAILED)?);
    HeldApplication::hold(path)
}

pub(crate) fn open_original(
    application: &HeldApplication,
    output: &Path,
    current: &dyn Fn() -> bool,
) -> Result<(), &'static str> {
    use std::os::windows::process::CommandExt;
    // Explicit application + an OS-escaped argument. Never interpret a source
    // path as a command, URL, shell verb or default-association query.
    if !current() {
        return Err(FAILED);
    }
    let mut command = std::process::Command::new(&application.path);
    command.arg(output).creation_flags(0x08000000).env_clear();
    // External applications receive no inherited Core/harness capability or
    // other application-private environment. Retain only normal Windows app
    // locations needed by the explicitly selected local consumer.
    for name in [
        "SystemRoot",
        "WINDIR",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
    ] {
        if let Some(value) = std::env::var_os(name) {
            command.env(name, value);
        }
    }
    command
        .current_dir(application.path.parent().ok_or(FAILED)?)
        .spawn()
        .map_err(|_| FAILED)?;
    Ok(())
}

struct DialogLifetime<'a> {
    current: &'a dyn Fn() -> bool,
}

unsafe fn dialog_message(
    window: windows_sys::Win32::Foundation::HWND,
    message: u32,
    data: Option<*const DialogLifetime<'_>>,
) -> usize {
    use windows_sys::Win32::UI::WindowsAndMessaging::*;
    if message == WM_INITDIALOG {
        if let Some(data) = data {
            unsafe {
                SetWindowLongPtrW(window, GWLP_USERDATA, data as isize);
                SetTimer(window, 71, 50, None);
            }
        }
    } else if message == WM_TIMER {
        let data = unsafe { GetWindowLongPtrW(window, GWLP_USERDATA) } as *const DialogLifetime<'_>;
        if !data.is_null() && !(unsafe { &*data }.current)() {
            unsafe {
                PostMessageW(window, WM_COMMAND, 2, 0);
            }
        }
    } else if message == WM_DESTROY {
        unsafe {
            KillTimer(window, 71);
            SetWindowLongPtrW(window, GWLP_USERDATA, 0);
        }
    }
    0
}

unsafe extern "system" fn application_hook(
    window: windows_sys::Win32::Foundation::HWND,
    message: u32,
    _w: usize,
    l: isize,
) -> usize {
    use windows_sys::Win32::UI::Controls::Dialogs::OPENFILENAMEW;
    let data = (message == 0x0110 && l != 0)
        .then(|| unsafe { (*(l as *const OPENFILENAMEW)).lCustData as *const DialogLifetime<'_> });
    unsafe { dialog_message(window, message, data) }
}

unsafe extern "system" fn printer_hook(
    window: windows_sys::Win32::Foundation::HWND,
    message: u32,
    _w: usize,
    l: isize,
) -> usize {
    use windows_sys::Win32::UI::Controls::Dialogs::PRINTDLGW;
    let data = (message == 0x0110 && l != 0)
        .then(|| unsafe { (*(l as *const PRINTDLGW)).lCustData as *const DialogLifetime<'_> });
    unsafe { dialog_message(window, message, data) }
}

pub(crate) struct LocalPrinter {
    dc: windows_sys::Win32::Graphics::Gdi::HDC,
    file_printer: Option<String>,
}
impl Drop for LocalPrinter {
    fn drop(&mut self) {
        unsafe {
            windows_sys::Win32::Graphics::Gdi::DeleteDC(self.dc);
        }
    }
}

pub(crate) fn choose_printer(
    owner: isize,
    current: &dyn Fn() -> bool,
) -> Result<LocalPrinter, &'static str> {
    use windows_sys::Win32::Foundation::GlobalFree;
    use windows_sys::Win32::System::Memory::{GlobalLock, GlobalSize, GlobalUnlock};
    use windows_sys::Win32::UI::Controls::Dialogs::*;
    let lifetime = DialogLifetime { current };
    let mut dialog: PRINTDLGW = unsafe { std::mem::zeroed() };
    dialog.lStructSize = std::mem::size_of_val(&dialog) as u32;
    dialog.hwndOwner = owner as _;
    dialog.Flags = PD_RETURNDC
        | PD_NOSELECTION
        | PD_NOPAGENUMS
        | PD_ENABLEPRINTHOOK
        | PD_USEDEVMODECOPIESANDCOLLATE;
    dialog.nCopies = 1;
    dialog.nMinPage = 1;
    dialog.nMaxPage = 500;
    dialog.lCustData = &lifetime as *const _ as isize;
    dialog.lpfnPrintHook = Some(printer_hook);
    let printed = current() && unsafe { PrintDlgW(&mut dialog) } != 0;
    let selected = (|| -> Option<Option<String>> {
        if !printed || !current() || dialog.hDC.is_null() || dialog.hDevNames.is_null() {
            return None;
        }
        unsafe {
            let size = GlobalSize(dialog.hDevNames);
            let pointer = GlobalLock(dialog.hDevNames);
            if pointer.is_null() {
                return None;
            }
            let result = (|| {
                if size < std::mem::size_of::<DEVNAMES>() || size > 65536 || size % 2 != 0 {
                    return None;
                }
                let names = &*(pointer as *const DEVNAMES);
                let values = std::slice::from_raw_parts(pointer as *const u16, size / 2);
                let field = |offset: u16| {
                    let offset = offset as usize;
                    if offset < 4 || offset >= values.len() {
                        return None;
                    }
                    let length = values[offset..].iter().position(|c| *c == 0)?;
                    if length == 0 || length > 512 {
                        return None;
                    }
                    String::from_utf16(&values[offset..offset + length]).ok()
                };
                let port = field(names.wOutputOffset)?;
                let device = field(names.wDeviceOffset)?;
                let port = port.to_ascii_uppercase();
                // Locally installed TCP/IP and UNC printers still send content
                // away. The initial local Wave deliberately rejects those.
                if matches!(port.as_str(), "FILE:" | "PORTPROMPT:") {
                    // Only the qualified Windows PDF stream target is admitted.
                    // No driver-managed save dialog or arbitrary file monitor.
                    return qualified_pdf_printer(&device).then_some(Some(device));
                }
                None
            })();
            GlobalUnlock(dialog.hDevNames);
            result
        }
    })();
    unsafe {
        if !dialog.hDevNames.is_null() {
            GlobalFree(dialog.hDevNames);
        }
        if !dialog.hDevMode.is_null() {
            GlobalFree(dialog.hDevMode);
        }
        if selected.is_none() && !dialog.hDC.is_null() {
            windows_sys::Win32::Graphics::Gdi::DeleteDC(dialog.hDC);
        }
    }
    if let Some(file_printer) = selected {
        Ok(LocalPrinter {
            dc: dialog.hDC,
            file_printer,
        })
    } else if printed {
        Err(FAILED)
    } else {
        Err("RO-VIEWER-ACTION-CANCELLED")
    }
}

fn qualified_pdf_printer(device: &str) -> bool {
    use windows_sys::Win32::Graphics::Printing::{
        ClosePrinter, GetPrinterW, OpenPrinterW, PRINTER_HANDLE, PRINTER_INFO_2W,
    };
    let Ok(mut name) = wide(device) else {
        return false;
    };
    unsafe {
        let mut printer = PRINTER_HANDLE {
            Value: std::ptr::null_mut(),
        };
        if OpenPrinterW(name.as_mut_ptr(), &mut printer, std::ptr::null()) == 0 {
            return false;
        }
        let mut needed = 0;
        GetPrinterW(printer, 2, std::ptr::null_mut(), 0, &mut needed);
        let result = if needed >= std::mem::size_of::<PRINTER_INFO_2W>() as u32 && needed <= 65536 {
            // u64 storage supplies alignment for the returned pointer-bearing record.
            let mut storage = vec![0u64; (needed as usize).div_ceil(8)];
            if GetPrinterW(printer, 2, storage.as_mut_ptr() as _, needed, &mut needed) == 0 {
                false
            } else {
                let info = &*(storage.as_ptr() as *const PRINTER_INFO_2W);
                let field = |p: *const u16| -> Option<String> {
                    let start = p as usize;
                    let base = storage.as_ptr() as usize;
                    let end = base + storage.len() * 8;
                    if start < base || start >= end || start % 2 != 0 {
                        return None;
                    }
                    let values = std::slice::from_raw_parts(p, (end - start) / 2);
                    let length = values.iter().position(|v| *v == 0)?;
                    (length <= 512)
                        .then(|| String::from_utf16(&values[..length]).ok())
                        .flatten()
                };
                field(info.pDriverName)
                    .is_some_and(|v| v.eq_ignore_ascii_case("Microsoft Print To PDF"))
                    && field(info.pPortName).is_some_and(|v| {
                        matches!(v.to_ascii_uppercase().as_str(), "PORTPROMPT:" | "FILE:")
                    })
                    && (info.pServerName.is_null()
                        || field(info.pServerName).is_some_and(|v| v.is_empty()))
            }
        } else {
            false
        };
        ClosePrinter(printer);
        result
    }
}

impl LocalPrinter {
    pub(crate) fn file_printer(&self) -> Option<&str> {
        self.file_printer.as_deref()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    const OPERATION: &str = "01a123ff-0000-7000-8000-000000000001";
    fn fixture() -> PathBuf {
        static NEXT: AtomicUsize = AtomicUsize::new(0);
        let directory = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../artifacts/tmp")
            .join(format!(
                "directory-dialog-viewer-export-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
        std::fs::create_dir(&directory).unwrap();
        dunce::canonicalize(directory).unwrap()
    }
    #[test]
    fn create_new_preserves_existing_files_and_failed_or_revoked_output_is_deleted() {
        let directory = fixture();
        let path = directory.join(format!("reader-{OPERATION}.json"));
        let bytes = b"SYNTHETIC original researcher-owned output";
        std::fs::write(&path, bytes).unwrap();
        assert!(LocalDeliverable::create(&directory, OPERATION, "json").is_err());
        assert_eq!(std::fs::read(&path).unwrap(), bytes);
        let directory = fixture();
        let path = directory.join(format!("reader-{OPERATION}.json"));
        let mut output = LocalDeliverable::create(&directory, OPERATION, "json").unwrap();
        output.append(bytes, &|| true).unwrap();
        assert!(std::fs::rename(&path, directory.join("replacement.json")).is_err());
        assert!(OpenOptions::new().write(true).open(&path).is_err());
        assert!(
            output
                .verify(&"f".repeat(64), bytes.len() as u64, &|| true)
                .is_err()
        );
        drop(output);
        assert!(!path.exists());
        let mut output = LocalDeliverable::create(&directory, OPERATION, "json").unwrap();
        output.append(bytes, &|| true).unwrap();
        output
            .verify(
                &format!("{:x}", Sha256::digest(bytes)),
                bytes.len() as u64,
                &|| true,
            )
            .unwrap();
        assert!(output.publish(&|| false).is_err());
        drop(output);
        assert!(!path.exists());
    }
    #[test]
    fn explicit_verified_publication_survives_close_and_selected_application_cannot_be_replaced() {
        let directory = fixture();
        let path = directory.join(format!("reader-{OPERATION}.json"));
        let bytes = b"SYNTHETIC quotation with source and anchor identifiers";
        let mut output = LocalDeliverable::create(&directory, OPERATION, "json").unwrap();
        output.append(bytes, &|| true).unwrap();
        output
            .verify(
                &format!("{:x}", Sha256::digest(bytes)),
                bytes.len() as u64,
                &|| true,
            )
            .unwrap();
        output.publish(&|| true).unwrap();
        drop(output);
        assert_eq!(std::fs::read(&path).unwrap(), bytes);
        let executable = directory.join("owned-inert.exe");
        std::fs::copy(std::env::current_exe().unwrap(), &executable).unwrap();
        let selected = HeldApplication::hold(executable.clone()).unwrap();
        assert!(std::fs::rename(&executable, directory.join("substituted.exe")).is_err());
        assert!(OpenOptions::new().write(true).open(&executable).is_err());
        drop(selected);
        std::fs::rename(&executable, directory.join("substituted.exe")).unwrap();
    }
    #[test]
    fn print_stream_is_bounded_and_rejects_reparse_destinations() {
        let directory = fixture();
        let path = directory.join(format!("reader-{OPERATION}.pdf"));
        let mut output = LocalDeliverable::create(&directory, OPERATION, "pdf").unwrap();
        assert!(output.print_seek(16_777_217, 0).is_err());
        assert!(output.print_size(16_777_217).is_err());
        assert!(output.print_write(&vec![0; 1_048_577]).is_err());
        drop(output);
        assert!(!path.exists());
        let real = directory.join("real");
        std::fs::create_dir(&real).unwrap();
        let link = directory.join("junction");
        use std::os::windows::process::CommandExt;
        let status = std::process::Command::new("cmd.exe")
            .args(["/d", "/c", "mklink", "/J"])
            .arg(&link)
            .arg(&real)
            .creation_flags(0x08000000)
            .output()
            .unwrap();
        assert!(
            status.status.success(),
            "owned junction fixture creation must succeed"
        );
        assert!(LocalDeliverable::create(&link, OPERATION, "json").is_err());
    }
    #[test]
    #[ignore = "bounded owned child; termination is controlled by the task proof producer"]
    fn owned_incomplete_file_child() {
        let directory = std::env::var_os("RO_VIEWER_HELD_OUTPUT_FIXTURE")
            .map(PathBuf::from)
            .unwrap();
        let root = dunce::canonicalize(
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../artifacts/tmp"),
        )
        .unwrap();
        let directory = dunce::canonicalize(directory).unwrap();
        assert!(
            directory.starts_with(&root)
                && directory
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("directory-dialog-viewer-held-child-")
        );
        let mut output = LocalDeliverable::create(&directory, OPERATION, "json").unwrap();
        output
            .append(
                b"SYNTHETIC incomplete plaintext; owned termination test",
                &|| true,
            )
            .unwrap();
        use std::io::Write;
        println!("RO-OWNED-HELD-FILE-READY");
        std::io::stdout().flush().unwrap();
        std::thread::sleep(std::time::Duration::from_secs(40));
        panic!("the bounded parent must terminate this owned child before timeout");
    }
    #[test]
    #[ignore = "runs alone in an owned child and an isolated window station; never the researcher's clipboard"]
    fn actual_isolated_clipboard_contains_only_authored_identified_quotation_and_privacy_markers() {
        // This exact ignored OS test can require UAC. Bound the elevated child
        // itself, so a clipboard/driver stall cannot outlive the authorized run.
        let (completed, closing) = std::sync::mpsc::sync_channel::<()>(1);
        let watchdog = std::thread::spawn(move || {
            if matches!(
                closing.recv_timeout(std::time::Duration::from_secs(30)),
                Err(std::sync::mpsc::RecvTimeoutError::Timeout)
            ) {
                std::process::abort();
            }
        });
        use windows_sys::Win32::System::{
            DataExchange::*,
            Memory::{GlobalLock, GlobalSize, GlobalUnlock},
            StationsAndDesktops::*,
            Threading::GetCurrentThreadId,
        };
        use windows_sys::Win32::UI::WindowsAndMessaging::*;
        unsafe {
            let previous_station = GetProcessWindowStation();
            let previous_desktop = GetThreadDesktop(GetCurrentThreadId());
            // Request only the station-specific rights, without owner/DACL
            // modification. CWF_CREATE_ONLY rejects any existing station.
            let requested = format!("RO-Viewer-Clipboard-{}", std::process::id());
            let station_name = wide(&requested).unwrap();
            let station =
                CreateWindowStationW(station_name.as_ptr(), 1, 0x0000037f, std::ptr::null());
            assert!(
                !station.is_null(),
                "owned station creation error {}",
                windows_sys::Win32::Foundation::GetLastError()
            );
            assert_ne!(SetProcessWindowStation(station), 0);
            let desktop_name = wide("owned").unwrap();
            let desktop = CreateDesktopW(
                desktop_name.as_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                0,
                0x000f01ff,
                std::ptr::null(),
            );
            assert!(!desktop.is_null());
            assert_ne!(SetThreadDesktop(desktop), 0);
            let object_name = |handle| {
                let mut name = [0u16; 256];
                let mut required = 0;
                assert_ne!(
                    GetUserObjectInformationW(
                        handle,
                        UOI_NAME,
                        name.as_mut_ptr() as _,
                        512,
                        &mut required
                    ),
                    0
                );
                let length = name.iter().position(|v| *v == 0).unwrap();
                String::from_utf16(&name[..length]).unwrap()
            };
            let name = object_name(station);
            assert_eq!(
                name, requested,
                "clipboard station must be the fresh owned station"
            );
            assert_ne!(name.to_ascii_lowercase(), "winsta0");
            assert_ne!(name, object_name(previous_station));
            assert_eq!(object_name(GetProcessWindowStation()), name);
            assert_eq!(object_name(GetThreadDesktop(GetCurrentThreadId())), "owned");
            let class = wide("STATIC").unwrap();
            let title = wide("Owned isolated quotation test").unwrap();
            let window = CreateWindowExW(
                0,
                class.as_ptr(),
                title.as_ptr(),
                WS_OVERLAPPED,
                0,
                0,
                1,
                1,
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null(),
            );
            assert!(!window.is_null());
            let text = "{\"text\":\"SYNTHETIC quotation\",\"documentRevisionId\":\"01a123ff-0000-7000-8000-000000000002\",\"anchorId\":\"01a123ff-0000-7000-8000-000000000003\",\"scholarlyVerification\":\"unverified\"}";
            copy_quotation(window as isize, text, &|| true).unwrap();
            // Only this newly created private station may be inspected.
            assert_eq!(object_name(GetProcessWindowStation()), name);
            assert_ne!(OpenClipboard(window), 0);
            for name in [
                "ExcludeClipboardContentFromMonitorProcessing",
                "CanIncludeInClipboardHistory",
                "CanUploadToCloudClipboard",
            ] {
                let name = wide(name).unwrap();
                let format = RegisterClipboardFormatW(name.as_ptr());
                let handle = GetClipboardData(format);
                assert!(!handle.is_null());
                let value = GlobalLock(handle);
                assert!(!value.is_null());
                assert!(GlobalSize(handle) >= 4);
                assert_eq!(*(value as *const u32), 0);
                GlobalUnlock(handle);
            }
            let handle = GetClipboardData(13);
            assert!(!handle.is_null());
            let value = GlobalLock(handle);
            assert!(!value.is_null());
            let size = GlobalSize(handle);
            assert!(size <= 65536 && size % 2 == 0);
            let values = std::slice::from_raw_parts(value as *const u16, size / 2);
            let length = values.iter().position(|v| *v == 0).unwrap();
            assert_eq!(String::from_utf16(&values[..length]).unwrap(), text);
            GlobalUnlock(handle);
            assert_ne!(CloseClipboard(), 0);
            assert_ne!(DestroyWindow(window), 0);
            assert_ne!(SetProcessWindowStation(previous_station), 0);
            assert_ne!(SetThreadDesktop(previous_desktop), 0);
            assert_eq!(GetProcessWindowStation(), previous_station);
            assert_eq!(GetThreadDesktop(GetCurrentThreadId()), previous_desktop);
            assert_ne!(CloseDesktop(desktop), 0);
            assert_ne!(CloseWindowStation(station), 0);
            let root = dunce::canonicalize(
                PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../artifacts/tmp"),
            )
            .unwrap();
            let path = root.join(format!(
                "CAP-05.S04.T03.private-clipboard-{}.json",
                std::process::id()
            ));
            let mut receipt = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(path)
                .unwrap();
            let record = serde_json::json!({"kind":"owned-private-clipboard", "status":"PASS",
                "freshPrivateWindowStation":true,"researcherClipboardAccessed":false,
                "exactAuthoredQuotationAndIdentifiers":true,"allThreePrivacyMarkers":true,
                "ownedDesktopAndWindowClosed":true});
            receipt.write_all(record.to_string().as_bytes()).unwrap();
            receipt.sync_all().unwrap();
        }
        completed.send(()).unwrap();
        watchdog.join().unwrap();
    }
    #[test]
    #[ignore = "requires the installed local Microsoft PDF driver"]
    fn actual_pdf_driver_selection_is_local_and_qualified() {
        assert!(qualified_pdf_printer("Microsoft Print to PDF"));
        assert!(!qualified_pdf_printer("missing-synthetic-printer"));
    }

    #[test]
    #[ignore = "requires the bounded task-owned inert local consumer executable"]
    fn actual_inert_consumer_reads_verified_original_without_private_environment() {
        let root = dunce::canonicalize(
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../artifacts/tmp"),
        )
        .unwrap();
        let input = std::env::var_os("RO_VIEWER_INERT_CONSUMER")
            .map(PathBuf::from)
            .unwrap();
        let input = dunce::canonicalize(input).unwrap();
        assert!(
            input.starts_with(&root) && input.file_name().unwrap() == "owned-reader-consumer.exe"
        );
        let directory = fixture();
        let executable = directory.join("owned-reader-consumer.exe");
        std::fs::copy(input, &executable).unwrap();
        let app = HeldApplication::hold(executable).unwrap();
        let bytes = b"SYNTHETIC authorized external original";
        let mut output = LocalDeliverable::create(&directory, OPERATION, "txt").unwrap();
        output.append(bytes, &|| true).unwrap();
        output
            .verify(
                &format!("{:x}", Sha256::digest(bytes)),
                bytes.len() as u64,
                &|| true,
            )
            .unwrap();
        output.publish(&|| true).unwrap();
        let (held, _parents, path) = output.into_external_file().unwrap();
        open_original(&app, &path, &|| true).unwrap();
        let receipt = path.with_extension("consumer-receipt");
        let started = std::time::Instant::now();
        while !receipt.exists() {
            assert!(started.elapsed() < std::time::Duration::from_secs(5));
            std::thread::sleep(std::time::Duration::from_millis(20));
        }
        assert_eq!(
            std::fs::read(&receipt).unwrap(),
            b"SYNTHETIC verified consumer read and isolated environment"
        );
        assert!(OpenOptions::new().write(true).open(&path).is_err());
        drop(held);
    }
}
