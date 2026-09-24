//! Owned Windows dialog. All entered values remain in native process memory.
use crate::connector_configuration::{ConnectionStatus, Edit, PrivateBytes, Provider};
use std::cell::RefCell;
use std::ptr::null;
use windows_sys::Win32::Foundation::{HWND, LPARAM, WPARAM};
use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
use windows_sys::Win32::UI::Input::KeyboardAndMouse::EnableWindow;
use windows_sys::Win32::UI::WindowsAndMessaging::*;

const CONTACT: i32 = 101;
const KEY: i32 = 102;
const KEEP_CONTACT: i32 = 201;
const KEEP_KEY: i32 = 202;
const ERROR: i32 = 301;
const BM_GETCHECK_MESSAGE: u32 = 0x00f0;
const BM_SETCHECK_MESSAGE: u32 = 0x00f1;
const EM_LIMITTEXT_MESSAGE: u32 = 0x00c5;
// Windows SDK DWLP_USER = DWLP_DLGPROC + sizeof(DLGPROC), pointer-width aware.
const DIALOG_USER: i32 = (2 * std::mem::size_of::<isize>()) as i32;

struct Template(Vec<u16>, u16);
impl Template {
    fn word(&mut self, value: u16) {
        self.0.push(value);
    }
    fn dword(&mut self, value: u32) {
        self.word(value as u16);
        self.word((value >> 16) as u16);
    }
    fn text(&mut self, text: &str) {
        self.0.extend(text.encode_utf16());
        self.word(0);
    }
    fn control(&mut self, id: i32, class: u16, style: u32, bounds: [u16; 4], text: &str) {
        if self.0.len() % 2 != 0 {
            self.word(0);
        }
        self.dword(WS_CHILD | WS_VISIBLE | style);
        self.dword(0);
        for value in bounds {
            self.word(value);
        }
        self.word(id as u16);
        self.word(0xffff);
        self.word(class);
        self.text(text);
        self.word(0);
        self.1 += 1;
    }
    fn build(provider: Provider) -> Vec<u32> {
        let mut t = Self(Vec::new(), 0);
        t.dword(
            WS_POPUP
                | WS_CAPTION
                | WS_SYSMENU
                | DS_MODALFRAME as u32
                | DS_SETFONT as u32
                | DS_CENTER as u32,
        );
        t.dword(0);
        t.word(0); // cdit is patched after controls.
        for value in [0, 0, 350, 245] {
            t.word(value);
        }
        t.word(0);
        t.word(0);
        t.text(provider.title());
        t.word(9);
        t.text("Segoe UI");
        t.control(-1, 0x82, 0, [12, 10, 326, 34], "Stored privately on this computer for your Windows user. Saving does not test a connection or permit project data to leave.");
        let mut y = 49;
        if provider.has_contact() {
            t.control(
                -1,
                0x82,
                0,
                [12, y, 326, 12],
                if provider == Provider::Unpaywall {
                    "&Contact email (required for Unpaywall requests)"
                } else {
                    "&Contact email (optional)"
                },
            );
            t.control(
                CONTACT,
                0x81,
                WS_TABSTOP | WS_BORDER | ES_AUTOHSCROLL as u32,
                [12, y + 14, 326, 16],
                "",
            );
            t.control(
                KEEP_CONTACT,
                0x80,
                WS_TABSTOP | BS_AUTOCHECKBOX as u32,
                [12, y + 33, 326, 14],
                "&Keep existing contact email (not displayed)",
            );
            y += 56;
        }
        if provider.has_key() {
            t.control(
                -1,
                0x82,
                0,
                [12, y, 326, 12],
                "&API key (optional; hidden while typing)",
            );
            t.control(
                KEY,
                0x81,
                WS_TABSTOP | WS_BORDER | ES_AUTOHSCROLL as u32 | ES_PASSWORD as u32,
                [12, y + 14, 326, 16],
                "",
            );
            t.control(
                KEEP_KEY,
                0x80,
                WS_TABSTOP | BS_AUTOCHECKBOX as u32,
                [12, y + 33, 326, 14],
                "Keep e&xisting API key (not displayed)",
            );
        }
        t.control(-1, 0x82, 0, [12, 164, 326, 24], "To replace a saved value, uncheck Keep and enter its replacement. Leave blank to clear it. Cancel makes no changes.");
        t.control(ERROR, 0x82, 0, [12, 191, 326, 23], "");
        t.control(
            IDOK,
            0x80,
            WS_TABSTOP | BS_DEFPUSHBUTTON as u32,
            [180, 219, 76, 16],
            "&Save locally",
        );
        t.control(
            IDCANCEL,
            0x80,
            WS_TABSTOP | BS_PUSHBUTTON as u32,
            [262, 219, 76, 16],
            "Cancel",
        );
        t.0[4] = t.1;
        if t.0.len() % 2 != 0 {
            t.word(0);
        }
        // DLGTEMPLATE must be DWORD aligned, including each DLGITEMTEMPLATE.
        t.0.chunks_exact(2)
            .map(|pair| u32::from(pair[0]) | (u32::from(pair[1]) << 16))
            .collect()
    }
}

struct State<'a> {
    status: &'a ConnectionStatus,
    current: &'a dyn Fn() -> bool,
    result: Option<Edit>,
    failed: bool,
}

fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain([0]).collect()
}

unsafe fn set_text(window: HWND, id: i32, value: &str) {
    unsafe {
        SetDlgItemTextW(window, id, wide(value).as_ptr());
    }
}

unsafe fn clear(window: HWND) {
    for id in [CONTACT, KEY] {
        unsafe {
            set_text(window, id, "");
        }
    }
}

unsafe fn checked(window: HWND, id: i32) -> bool {
    unsafe { SendDlgItemMessageW(window, id, BM_GETCHECK_MESSAGE, 0, 0) == 1 }
}

unsafe fn read(window: HWND, id: i32) -> Result<Option<PrivateBytes>, ()> {
    let field = unsafe { GetDlgItem(window, id) };
    if field.is_null() {
        return Ok(None);
    }
    let length = unsafe { GetWindowTextLengthW(field) };
    if !(0..=1024).contains(&length) {
        return Err(());
    }
    let mut buffer = [0_u16; 1025];
    let copied = unsafe { GetDlgItemTextW(window, id, buffer.as_mut_ptr(), buffer.len() as i32) };
    let valid = copied == length as u32
        && buffer[..length as usize]
            .iter()
            .all(|c| (33..=126).contains(c));
    let value = if valid && length != 0 {
        Some(PrivateBytes(
            buffer[..length as usize].iter().map(|c| *c as u8).collect(),
        ))
    } else {
        None
    };
    for word in &mut buffer {
        unsafe {
            std::ptr::write_volatile(word, 0);
        }
    }
    std::sync::atomic::compiler_fence(std::sync::atomic::Ordering::SeqCst);
    if valid && (length == 0 || length >= 3) {
        Ok(value)
    } else {
        Err(())
    }
}

unsafe fn finish(window: HWND, code: i32) {
    unsafe {
        clear(window);
        KillTimer(window, 1);
        EndDialog(window, code as isize);
    }
}

unsafe fn handle(window: HWND, message: u32, wparam: WPARAM, lparam: LPARAM) -> isize {
    if message == WM_INITDIALOG {
        unsafe {
            SetWindowLongPtrW(window, DIALOG_USER, lparam);
        }
    }
    let state = unsafe { GetWindowLongPtrW(window, DIALOG_USER) as *const RefCell<State<'_>> };
    let Some(state) = (unsafe { state.as_ref() }) else {
        return 0;
    };
    // Setting native control text can synchronously re-enter the dialog
    // procedure. Never create aliased mutable references to its private state.
    let Ok(mut state) = state.try_borrow_mut() else {
        return 0;
    };
    match message {
        WM_INITDIALOG => {
            for (field, keep, present) in [
                (CONTACT, KEEP_CONTACT, state.status.contact_configured),
                (KEY, KEEP_KEY, state.status.key_configured),
            ] {
                let control = unsafe { GetDlgItem(window, field) };
                if control.is_null() {
                    continue;
                }
                unsafe {
                    SendMessageW(control, EM_LIMITTEXT_MESSAGE, 1024, 0);
                    SendDlgItemMessageW(window, keep, BM_SETCHECK_MESSAGE, usize::from(present), 0);
                    EnableWindow(GetDlgItem(window, keep), i32::from(present));
                    EnableWindow(control, i32::from(!present));
                }
            }
            if unsafe { SetTimer(window, 1, 100, None) } == 0 {
                state.failed = true;
                unsafe {
                    finish(window, IDCANCEL);
                }
            }
            1
        }
        WM_TIMER if wparam == 1 => {
            if !(state.current)() {
                unsafe {
                    finish(window, IDCANCEL);
                }
            }
            1
        }
        WM_CLOSE => {
            unsafe {
                finish(window, IDCANCEL);
            }
            1
        }
        WM_COMMAND => {
            let id = (wparam & 0xffff) as i32;
            if id == IDCANCEL {
                unsafe {
                    finish(window, IDCANCEL);
                }
                return 1;
            }
            if matches!(id, KEEP_CONTACT | KEEP_KEY) && (wparam >> 16) == BN_CLICKED as usize {
                let field = if id == KEEP_CONTACT { CONTACT } else { KEY };
                let keep = unsafe { checked(window, id) };
                unsafe {
                    if keep {
                        set_text(window, field, "");
                    }
                    EnableWindow(GetDlgItem(window, field), i32::from(!keep));
                }
                return 1;
            }
            if id != IDOK {
                return 0;
            }
            if !(state.current)() {
                unsafe {
                    finish(window, IDCANCEL);
                }
                return 1;
            }
            let preserve_key = state.status.key_configured && unsafe { checked(window, KEEP_KEY) };
            let preserve_contact =
                state.status.contact_configured && unsafe { checked(window, KEEP_CONTACT) };
            let key = if preserve_key {
                Ok(None)
            } else {
                unsafe { read(window, KEY) }
            };
            let contact = if preserve_contact {
                Ok(None)
            } else {
                unsafe { read(window, CONTACT) }
            };
            let (Ok(key), Ok(contact)) = (key, contact) else {
                unsafe {
                    set_text(
                        window,
                        ERROR,
                        "Use 3-1024 printable characters with no spaces, or leave the field blank to clear it.",
                    );
                }
                return 1;
            };
            if contact.as_ref().is_some_and(|value| {
                let mut parts = value.text().split('@');
                let local = parts.next().unwrap_or("");
                let host = parts.next().unwrap_or("");
                local.is_empty()
                    || !host.contains('.')
                    || host.starts_with('.')
                    || host.ends_with('.')
                    || parts.next().is_some()
            }) {
                unsafe {
                    set_text(
                        window,
                        ERROR,
                        "Enter a contact email address, or leave it blank to clear it.",
                    );
                }
                return 1;
            }
            // Clearing required contact is allowed; it explicitly disables
            // Unpaywall requests until a contact is supplied again.
            state.result = Some(Edit {
                key,
                contact,
                preserve_key,
                preserve_contact,
            });
            unsafe {
                finish(window, IDOK);
            }
            1
        }
        WM_DESTROY => {
            unsafe {
                clear(window);
                SetWindowLongPtrW(window, DIALOG_USER, 0);
            }
            0
        }
        _ => 0,
    }
}

unsafe extern "system" fn procedure(
    window: HWND,
    message: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> isize {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| unsafe {
        handle(window, message, wparam, lparam)
    })) {
        Ok(result) => result,
        Err(_) => {
            unsafe {
                finish(window, IDCANCEL);
            }
            1
        }
    }
}

pub(crate) fn show(
    owner: isize,
    provider: Provider,
    status: &ConnectionStatus,
    current: &dyn Fn() -> bool,
) -> Result<Option<Edit>, ()> {
    if !crate::directory_picker::valid_owner(owner) || !current() {
        return Ok(None);
    }
    let template = Template::build(provider);
    let state = RefCell::new(State {
        status,
        current,
        result: None,
        failed: false,
    });
    let result = unsafe {
        DialogBoxIndirectParamW(
            GetModuleHandleW(null()),
            template.as_ptr().cast(),
            owner as HWND,
            Some(procedure),
            (&state as *const RefCell<State<'_>>) as isize,
        )
    };
    let state = state.into_inner();
    if result == -1 || result == 0 || state.failed {
        Err(())
    } else if result == IDOK as isize && current() {
        Ok(state.result)
    } else {
        Ok(None)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_templates_are_aligned_bounded_and_provider_specific() {
        for provider in [
            Provider::Openalex,
            Provider::Crossref,
            Provider::Unpaywall,
            Provider::SemanticScholar,
        ] {
            let template = Template::build(provider);
            assert!(template.len() < 2048);
            let words: Vec<u16> = template
                .iter()
                .flat_map(|value| [*value as u16, (*value >> 16) as u16])
                .collect();
            assert_eq!(
                words[4],
                5 + 3 * (provider.has_key() as u16 + provider.has_contact() as u16)
            );
            let text = String::from_utf16_lossy(&words);
            assert!(text.contains("Save locally"));
            assert_eq!(text.contains("API key (optional"), provider.has_key());
            assert_eq!(text.contains("Contact email"), provider.has_contact());
        }
    }
}
