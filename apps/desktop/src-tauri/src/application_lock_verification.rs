#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum VerificationOutcome {
    Succeeded,
    Cancelled,
    Denied,
    Unavailable,
    Busy,
    Failed,
}

pub trait NativeVerificationProvider: Send + Sync {
    fn verify(&self) -> VerificationOutcome;
}

impl<F> NativeVerificationProvider for F
where
    F: Fn() -> VerificationOutcome + Send + Sync,
{
    fn verify(&self) -> VerificationOutcome {
        self()
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct WindowsPasswordVerificationProvider;

impl NativeVerificationProvider for WindowsPasswordVerificationProvider {
    fn verify(&self) -> VerificationOutcome {
        verify_current_windows_user()
    }
}

#[cfg(windows)]
const CREDENTIAL_PROMPT_FLAGS: u32 = {
    use windows_sys::Win32::Security::Credentials::{
        CREDUI_FLAGS_ALWAYS_SHOW_UI, CREDUI_FLAGS_DO_NOT_PERSIST,
        CREDUI_FLAGS_EXCLUDE_CERTIFICATES, CREDUI_FLAGS_GENERIC_CREDENTIALS,
        CREDUI_FLAGS_VALIDATE_USERNAME,
    };
    CREDUI_FLAGS_ALWAYS_SHOW_UI
        | CREDUI_FLAGS_DO_NOT_PERSIST
        | CREDUI_FLAGS_EXCLUDE_CERTIFICATES
        | CREDUI_FLAGS_GENERIC_CREDENTIALS
        | CREDUI_FLAGS_VALIDATE_USERNAME
};

#[cfg(windows)]
struct SecretWide(Vec<u16>);

#[cfg(windows)]
impl Drop for SecretWide {
    fn drop(&mut self) {
        for value in &mut self.0 {
            unsafe { std::ptr::write_volatile(value, 0) };
        }
    }
}

#[cfg(windows)]
fn current_sam_identity() -> Option<SecretWide> {
    use windows_sys::Win32::Security::Authentication::Identity::{
        GetUserNameExW, NameSamCompatible,
    };

    let mut length = 0_u32;
    unsafe { GetUserNameExW(NameSamCompatible, std::ptr::null_mut(), &mut length) };
    if length == 0 || length > 514 {
        return None;
    }
    let mut identity = SecretWide(vec![0_u16; length as usize]);
    if !unsafe { GetUserNameExW(NameSamCompatible, identity.0.as_mut_ptr(), &mut length) } {
        return None;
    }
    if identity.0.last().copied() != Some(0) {
        return None;
    }
    Some(identity)
}

#[cfg(windows)]
fn optional_wide_pointer(value: &SecretWide) -> *const u16 {
    if value.0.first().copied().unwrap_or(0) == 0 {
        std::ptr::null()
    } else {
        value.0.as_ptr()
    }
}

#[cfg(windows)]
fn parse_logon_identity(username: &SecretWide) -> Option<(SecretWide, SecretWide)> {
    use windows_sys::Win32::Security::Credentials::CredUIParseUserNameW;

    let mut user = SecretWide(vec![0_u16; 514]);
    let mut domain = SecretWide(vec![0_u16; 514]);
    if unsafe {
        CredUIParseUserNameW(
            username.0.as_ptr(),
            user.0.as_mut_ptr(),
            user.0.len() as u32,
            domain.0.as_mut_ptr(),
            domain.0.len() as u32,
        )
    } != 0
    {
        None
    } else {
        Some((user, domain))
    }
}

#[cfg(windows)]
fn verify_current_windows_user() -> VerificationOutcome {
    use std::ffi::c_void;
    use std::ptr::{null, null_mut};
    use windows_sys::Win32::Foundation::{CloseHandle, ERROR_CANCELLED, HANDLE};
    use windows_sys::Win32::Security::Credentials::CredUIPromptForCredentialsW;
    use windows_sys::Win32::Security::{
        EqualSid, GetTokenInformation, LOGON32_LOGON_INTERACTIVE, LOGON32_PROVIDER_DEFAULT,
        LogonUserW, TOKEN_QUERY, TOKEN_USER, TokenUser,
    };
    use windows_sys::Win32::System::Threading::{GetCurrentProcess, OpenProcessToken};

    struct OwnedHandle(HANDLE);
    impl Drop for OwnedHandle {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe { CloseHandle(self.0) };
            }
        }
    }
    fn token_sid(handle: HANDLE) -> Option<Vec<usize>> {
        let mut length = 0_u32;
        unsafe { GetTokenInformation(handle, TokenUser, null_mut(), 0, &mut length) };
        if length == 0 {
            return None;
        }
        let words = (length as usize).div_ceil(std::mem::size_of::<usize>());
        let mut buffer = vec![0_usize; words];
        if unsafe {
            GetTokenInformation(
                handle,
                TokenUser,
                buffer.as_mut_ptr().cast::<c_void>(),
                length,
                &mut length,
            )
        } == 0
        {
            return None;
        }
        Some(buffer)
    }

    let target: Vec<u16> = "ResearchObservatory/ApplicationLock\0"
        .encode_utf16()
        .collect();
    let Some(mut username) = current_sam_identity() else {
        return VerificationOutcome::Unavailable;
    };
    username.0.resize(514, 0);
    let mut password = SecretWide(vec![0_u16; 256]);
    let status = unsafe {
        CredUIPromptForCredentialsW(
            null(),
            target.as_ptr(),
            null(),
            0,
            username.0.as_mut_ptr(),
            username.0.len() as u32,
            password.0.as_mut_ptr(),
            password.0.len() as u32,
            null_mut(),
            CREDENTIAL_PROMPT_FLAGS,
        )
    };
    if status == ERROR_CANCELLED {
        return VerificationOutcome::Cancelled;
    }
    if status != 0 {
        return VerificationOutcome::Failed;
    }

    let Some((user, domain)) = parse_logon_identity(&username) else {
        return VerificationOutcome::Failed;
    };

    let mut submitted = OwnedHandle(null_mut());
    let domain_pointer = optional_wide_pointer(&domain);
    if unsafe {
        LogonUserW(
            user.0.as_ptr(),
            domain_pointer,
            password.0.as_ptr(),
            LOGON32_LOGON_INTERACTIVE,
            LOGON32_PROVIDER_DEFAULT,
            &mut submitted.0,
        )
    } == 0
    {
        return VerificationOutcome::Denied;
    }
    let mut current = OwnedHandle(null_mut());
    if unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut current.0) } == 0 {
        return VerificationOutcome::Failed;
    }
    let Some(submitted_sid) = token_sid(submitted.0) else {
        return VerificationOutcome::Failed;
    };
    let Some(current_sid) = token_sid(current.0) else {
        return VerificationOutcome::Failed;
    };
    let submitted_user = unsafe { &*(submitted_sid.as_ptr().cast::<TOKEN_USER>()) };
    let current_user = unsafe { &*(current_sid.as_ptr().cast::<TOKEN_USER>()) };
    if unsafe { EqualSid(submitted_user.User.Sid, current_user.User.Sid) } == 0 {
        VerificationOutcome::Denied
    } else {
        VerificationOutcome::Succeeded
    }
}

#[cfg(not(windows))]
fn verify_current_windows_user() -> VerificationOutcome {
    VerificationOutcome::Unavailable
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn provider_neutral_outcomes_have_stable_contract_values() {
        for (outcome, serialized) in [
            (VerificationOutcome::Succeeded, "\"succeeded\""),
            (VerificationOutcome::Cancelled, "\"cancelled\""),
            (VerificationOutcome::Denied, "\"denied\""),
            (VerificationOutcome::Unavailable, "\"unavailable\""),
            (VerificationOutcome::Busy, "\"busy\""),
            (VerificationOutcome::Failed, "\"failed\""),
        ] {
            assert_eq!(
                serde_json::to_string(&outcome).expect("serialize"),
                serialized
            );
        }
    }

    #[cfg(not(windows))]
    #[test]
    fn password_provider_is_truthfully_unavailable_off_windows() {
        assert_eq!(
            WindowsPasswordVerificationProvider.verify(),
            VerificationOutcome::Unavailable
        );
    }

    #[cfg(windows)]
    #[test]
    fn windows_prompt_flags_and_logon_domain_mapping_are_exact() {
        use windows_sys::Win32::Security::Credentials::{
            CREDUI_FLAGS_ALWAYS_SHOW_UI, CREDUI_FLAGS_COMPLETE_USERNAME,
            CREDUI_FLAGS_DO_NOT_PERSIST, CREDUI_FLAGS_EXCLUDE_CERTIFICATES,
            CREDUI_FLAGS_GENERIC_CREDENTIALS, CREDUI_FLAGS_VALIDATE_USERNAME,
        };

        assert_eq!(
            CREDENTIAL_PROMPT_FLAGS,
            CREDUI_FLAGS_ALWAYS_SHOW_UI
                | CREDUI_FLAGS_DO_NOT_PERSIST
                | CREDUI_FLAGS_EXCLUDE_CERTIFICATES
                | CREDUI_FLAGS_GENERIC_CREDENTIALS
                | CREDUI_FLAGS_VALIDATE_USERNAME
        );
        assert_eq!(CREDENTIAL_PROMPT_FLAGS & CREDUI_FLAGS_COMPLETE_USERNAME, 0);
        assert!(current_sam_identity().is_some());
        let upn = SecretWide("researcher@example.invalid\0".encode_utf16().collect());
        let (upn_user, upn_domain) = parse_logon_identity(&upn).expect("parse UPN");
        assert_eq!(
            String::from_utf16_lossy(&upn_user.0[.."researcher@example.invalid".len()]),
            "researcher@example.invalid"
        );
        assert!(optional_wide_pointer(&upn_domain).is_null());
        let down_level = SecretWide("DOMAIN\\researcher\0".encode_utf16().collect());
        let (_, down_level_domain) =
            parse_logon_identity(&down_level).expect("parse down-level identity");
        assert!(!optional_wide_pointer(&down_level_domain).is_null());
    }
}
