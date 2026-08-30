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

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum VerificationAvailability {
    Checking,
    Available,
    NotPresent,
    NotConfigured,
    PolicyDisabled,
    Busy,
    Unavailable,
    Failed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct VerificationAvailabilitySnapshot {
    pub schema_version: &'static str,
    pub provider: &'static str,
    pub availability: VerificationAvailability,
}

pub trait NativeVerificationProvider: Send + Sync {
    fn availability(&self) -> VerificationAvailability {
        VerificationAvailability::Available
    }

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
    fn availability(&self) -> VerificationAvailability {
        if cfg!(windows) {
            VerificationAvailability::Available
        } else {
            VerificationAvailability::Unavailable
        }
    }

    fn verify(&self) -> VerificationOutcome {
        verify_current_windows_user()
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct WindowsHelloVerificationProvider {
    window_handle: isize,
}

impl WindowsHelloVerificationProvider {
    pub fn for_window(window_handle: isize) -> Result<Self, &'static str> {
        if window_handle == 0 {
            return Err("RO-LOCK-HELLO-WINDOW-UNAVAILABLE");
        }
        Ok(Self { window_handle })
    }
}

impl NativeVerificationProvider for WindowsHelloVerificationProvider {
    fn availability(&self) -> VerificationAvailability {
        windows_hello_availability()
    }

    fn verify(&self) -> VerificationOutcome {
        verify_windows_hello_for_window(self.window_handle)
    }
}

pub fn windows_hello_availability() -> VerificationAvailability {
    hello_availability_with(&SystemWindowsHelloBoundary)
}

pub fn windows_hello_availability_snapshot() -> VerificationAvailabilitySnapshot {
    VerificationAvailabilitySnapshot {
        schema_version: "1.0",
        provider: "windows-hello",
        availability: windows_hello_availability(),
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum HelloBoundaryError {
    Unavailable,
    Failed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum HelloOsAvailability {
    Available,
    NotPresent,
    NotConfigured,
    PolicyDisabled,
    Busy,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum HelloOsVerification {
    Verified,
    NotPresent,
    NotConfigured,
    PolicyDisabled,
    Busy,
    RetriesExhausted,
    Cancelled,
}

trait WindowsHelloBoundary {
    fn availability(&self) -> Result<HelloOsAvailability, HelloBoundaryError>;

    fn verify_for_window(
        &self,
        window_handle: isize,
    ) -> Result<HelloOsVerification, HelloBoundaryError>;
}

#[derive(Clone, Copy, Debug, Default)]
struct SystemWindowsHelloBoundary;

#[cfg(windows)]
struct WindowsRuntimeApartment;

#[cfg(windows)]
impl WindowsRuntimeApartment {
    fn initialize() -> Result<Self, HelloBoundaryError> {
        use windows::Win32::System::WinRT::{RO_INIT_MULTITHREADED, RoInitialize};

        unsafe { RoInitialize(RO_INIT_MULTITHREADED) }
            .map(|()| Self)
            .map_err(|_| HelloBoundaryError::Failed)
    }
}

#[cfg(windows)]
impl Drop for WindowsRuntimeApartment {
    fn drop(&mut self) {
        unsafe { windows::Win32::System::WinRT::RoUninitialize() };
    }
}

fn hello_availability_with(boundary: &impl WindowsHelloBoundary) -> VerificationAvailability {
    match boundary.availability() {
        Ok(HelloOsAvailability::Available) => VerificationAvailability::Available,
        Ok(HelloOsAvailability::NotPresent) => VerificationAvailability::NotPresent,
        Ok(HelloOsAvailability::NotConfigured) => VerificationAvailability::NotConfigured,
        Ok(HelloOsAvailability::PolicyDisabled) => VerificationAvailability::PolicyDisabled,
        Ok(HelloOsAvailability::Busy) => VerificationAvailability::Busy,
        Err(HelloBoundaryError::Unavailable) => VerificationAvailability::Unavailable,
        Err(HelloBoundaryError::Failed) => VerificationAvailability::Failed,
    }
}

fn verify_windows_hello_for_window(window_handle: isize) -> VerificationOutcome {
    verify_windows_hello_with(&SystemWindowsHelloBoundary, window_handle)
}

fn verify_windows_hello_with(
    boundary: &impl WindowsHelloBoundary,
    window_handle: isize,
) -> VerificationOutcome {
    if window_handle == 0 {
        return VerificationOutcome::Failed;
    }
    match hello_availability_with(boundary) {
        VerificationAvailability::Available => {}
        VerificationAvailability::Busy => return VerificationOutcome::Busy,
        VerificationAvailability::Failed => return VerificationOutcome::Failed,
        VerificationAvailability::Checking
        | VerificationAvailability::NotPresent
        | VerificationAvailability::NotConfigured
        | VerificationAvailability::PolicyDisabled
        | VerificationAvailability::Unavailable => return VerificationOutcome::Unavailable,
    }
    match boundary.verify_for_window(window_handle) {
        Ok(HelloOsVerification::Verified) => VerificationOutcome::Succeeded,
        Ok(HelloOsVerification::Busy) => VerificationOutcome::Busy,
        Ok(HelloOsVerification::RetriesExhausted) => VerificationOutcome::Denied,
        Ok(HelloOsVerification::Cancelled) => VerificationOutcome::Cancelled,
        Ok(HelloOsVerification::NotPresent)
        | Ok(HelloOsVerification::NotConfigured)
        | Ok(HelloOsVerification::PolicyDisabled)
        | Err(HelloBoundaryError::Unavailable) => VerificationOutcome::Unavailable,
        Err(HelloBoundaryError::Failed) => VerificationOutcome::Failed,
    }
}

#[cfg(windows)]
impl WindowsHelloBoundary for SystemWindowsHelloBoundary {
    fn availability(&self) -> Result<HelloOsAvailability, HelloBoundaryError> {
        use windows::Security::Credentials::UI::{
            UserConsentVerifier, UserConsentVerifierAvailability,
        };
        use windows::Win32::System::WinRT::IUserConsentVerifierInterop;

        let _apartment = WindowsRuntimeApartment::initialize()?;
        let result = UserConsentVerifier::CheckAvailabilityAsync()
            .and_then(|operation| operation.get())
            .map_err(|_| HelloBoundaryError::Failed)?;
        if result == UserConsentVerifierAvailability::Available {
            let _: IUserConsentVerifierInterop =
                windows::core::factory::<UserConsentVerifier, IUserConsentVerifierInterop>()
                    .map_err(|_| HelloBoundaryError::Unavailable)?;
            Ok(HelloOsAvailability::Available)
        } else if result == UserConsentVerifierAvailability::DeviceNotPresent {
            Ok(HelloOsAvailability::NotPresent)
        } else if result == UserConsentVerifierAvailability::NotConfiguredForUser {
            Ok(HelloOsAvailability::NotConfigured)
        } else if result == UserConsentVerifierAvailability::DisabledByPolicy {
            Ok(HelloOsAvailability::PolicyDisabled)
        } else if result == UserConsentVerifierAvailability::DeviceBusy {
            Ok(HelloOsAvailability::Busy)
        } else {
            Err(HelloBoundaryError::Failed)
        }
    }

    fn verify_for_window(
        &self,
        window_handle: isize,
    ) -> Result<HelloOsVerification, HelloBoundaryError> {
        use windows::Security::Credentials::UI::{
            UserConsentVerificationResult, UserConsentVerifier,
        };
        use windows::Win32::Foundation::HWND;
        use windows::Win32::System::WinRT::IUserConsentVerifierInterop;

        let _apartment = WindowsRuntimeApartment::initialize()?;
        let interop = windows::core::factory::<UserConsentVerifier, IUserConsentVerifierInterop>()
            .map_err(|_| HelloBoundaryError::Unavailable)?;
        let message = windows::core::HSTRING::from("Unlock Research Observatory");
        let operation = unsafe {
            interop.RequestVerificationForWindowAsync::<
                windows_future::IAsyncOperation<UserConsentVerificationResult>,
            >(HWND(window_handle as *mut std::ffi::c_void), &message)
        }
        .map_err(|_| HelloBoundaryError::Failed)?;
        let result = operation.get().map_err(|_| HelloBoundaryError::Failed)?;
        if result == UserConsentVerificationResult::Verified {
            Ok(HelloOsVerification::Verified)
        } else if result == UserConsentVerificationResult::DeviceNotPresent {
            Ok(HelloOsVerification::NotPresent)
        } else if result == UserConsentVerificationResult::NotConfiguredForUser {
            Ok(HelloOsVerification::NotConfigured)
        } else if result == UserConsentVerificationResult::DisabledByPolicy {
            Ok(HelloOsVerification::PolicyDisabled)
        } else if result == UserConsentVerificationResult::DeviceBusy {
            Ok(HelloOsVerification::Busy)
        } else if result == UserConsentVerificationResult::RetriesExhausted {
            Ok(HelloOsVerification::RetriesExhausted)
        } else if result == UserConsentVerificationResult::Canceled {
            Ok(HelloOsVerification::Cancelled)
        } else {
            Err(HelloBoundaryError::Failed)
        }
    }
}

#[cfg(not(windows))]
impl WindowsHelloBoundary for SystemWindowsHelloBoundary {
    fn availability(&self) -> Result<HelloOsAvailability, HelloBoundaryError> {
        Err(HelloBoundaryError::Unavailable)
    }

    fn verify_for_window(
        &self,
        _window_handle: isize,
    ) -> Result<HelloOsVerification, HelloBoundaryError> {
        Err(HelloBoundaryError::Unavailable)
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
    use std::sync::atomic::{AtomicUsize, Ordering};

    struct FakeHelloBoundary {
        availability: Result<HelloOsAvailability, HelloBoundaryError>,
        verification: Result<HelloOsVerification, HelloBoundaryError>,
        verification_calls: AtomicUsize,
    }

    impl FakeHelloBoundary {
        fn new(
            availability: Result<HelloOsAvailability, HelloBoundaryError>,
            verification: Result<HelloOsVerification, HelloBoundaryError>,
        ) -> Self {
            Self {
                availability,
                verification,
                verification_calls: AtomicUsize::new(0),
            }
        }
    }

    impl WindowsHelloBoundary for FakeHelloBoundary {
        fn availability(&self) -> Result<HelloOsAvailability, HelloBoundaryError> {
            self.availability
        }

        fn verify_for_window(
            &self,
            _window_handle: isize,
        ) -> Result<HelloOsVerification, HelloBoundaryError> {
            self.verification_calls.fetch_add(1, Ordering::SeqCst);
            self.verification
        }
    }

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

    #[test]
    fn windows_hello_availability_contract_has_every_approved_state() {
        for (availability, serialized) in [
            (VerificationAvailability::Checking, "\"checking\""),
            (VerificationAvailability::Available, "\"available\""),
            (VerificationAvailability::NotPresent, "\"not-present\""),
            (
                VerificationAvailability::NotConfigured,
                "\"not-configured\"",
            ),
            (
                VerificationAvailability::PolicyDisabled,
                "\"policy-disabled\"",
            ),
            (VerificationAvailability::Busy, "\"busy\""),
            (VerificationAvailability::Unavailable, "\"unavailable\""),
            (VerificationAvailability::Failed, "\"failed\""),
        ] {
            assert_eq!(
                serde_json::to_string(&availability).expect("serialize"),
                serialized
            );
        }
        assert_eq!(
            serde_json::to_value(VerificationAvailabilitySnapshot {
                schema_version: "1.0",
                provider: "windows-hello",
                availability: VerificationAvailability::Available,
            })
            .expect("serialize snapshot"),
            serde_json::json!({
                "schemaVersion": "1.0",
                "provider": "windows-hello",
                "availability": "available"
            })
        );
    }

    #[test]
    fn windows_hello_availability_maps_every_os_state_without_prompting() {
        for (os_state, expected) in [
            (
                Ok(HelloOsAvailability::Available),
                VerificationAvailability::Available,
            ),
            (
                Ok(HelloOsAvailability::NotPresent),
                VerificationAvailability::NotPresent,
            ),
            (
                Ok(HelloOsAvailability::NotConfigured),
                VerificationAvailability::NotConfigured,
            ),
            (
                Ok(HelloOsAvailability::PolicyDisabled),
                VerificationAvailability::PolicyDisabled,
            ),
            (
                Ok(HelloOsAvailability::Busy),
                VerificationAvailability::Busy,
            ),
            (
                Err(HelloBoundaryError::Unavailable),
                VerificationAvailability::Unavailable,
            ),
            (
                Err(HelloBoundaryError::Failed),
                VerificationAvailability::Failed,
            ),
        ] {
            let boundary = FakeHelloBoundary::new(os_state, Ok(HelloOsVerification::Verified));
            assert_eq!(hello_availability_with(&boundary), expected);
            assert_eq!(boundary.verification_calls.load(Ordering::SeqCst), 0);
        }
    }

    #[test]
    fn windows_hello_verification_maps_every_result_and_never_falls_back() {
        for (os_result, expected) in [
            (
                Ok(HelloOsVerification::Verified),
                VerificationOutcome::Succeeded,
            ),
            (
                Ok(HelloOsVerification::NotPresent),
                VerificationOutcome::Unavailable,
            ),
            (
                Ok(HelloOsVerification::NotConfigured),
                VerificationOutcome::Unavailable,
            ),
            (
                Ok(HelloOsVerification::PolicyDisabled),
                VerificationOutcome::Unavailable,
            ),
            (Ok(HelloOsVerification::Busy), VerificationOutcome::Busy),
            (
                Ok(HelloOsVerification::RetriesExhausted),
                VerificationOutcome::Denied,
            ),
            (
                Ok(HelloOsVerification::Cancelled),
                VerificationOutcome::Cancelled,
            ),
            (
                Err(HelloBoundaryError::Unavailable),
                VerificationOutcome::Unavailable,
            ),
            (Err(HelloBoundaryError::Failed), VerificationOutcome::Failed),
        ] {
            let boundary = FakeHelloBoundary::new(Ok(HelloOsAvailability::Available), os_result);
            assert_eq!(verify_windows_hello_with(&boundary, 1), expected);
            assert_eq!(boundary.verification_calls.load(Ordering::SeqCst), 1);
        }
    }

    #[test]
    fn windows_hello_never_prompts_when_unavailable_or_missing_a_window() {
        for (availability, expected) in [
            (
                Ok(HelloOsAvailability::NotPresent),
                VerificationOutcome::Unavailable,
            ),
            (
                Ok(HelloOsAvailability::NotConfigured),
                VerificationOutcome::Unavailable,
            ),
            (
                Ok(HelloOsAvailability::PolicyDisabled),
                VerificationOutcome::Unavailable,
            ),
            (Ok(HelloOsAvailability::Busy), VerificationOutcome::Busy),
            (
                Err(HelloBoundaryError::Unavailable),
                VerificationOutcome::Unavailable,
            ),
            (Err(HelloBoundaryError::Failed), VerificationOutcome::Failed),
        ] {
            let boundary = FakeHelloBoundary::new(availability, Ok(HelloOsVerification::Verified));
            assert_eq!(verify_windows_hello_with(&boundary, 1), expected);
            assert_eq!(boundary.verification_calls.load(Ordering::SeqCst), 0);
        }
        let boundary = FakeHelloBoundary::new(
            Ok(HelloOsAvailability::Available),
            Ok(HelloOsVerification::Verified),
        );
        assert_eq!(
            verify_windows_hello_with(&boundary, 0),
            VerificationOutcome::Failed
        );
        assert_eq!(boundary.verification_calls.load(Ordering::SeqCst), 0);
        assert_eq!(
            WindowsHelloVerificationProvider::for_window(0),
            Err("RO-LOCK-HELLO-WINDOW-UNAVAILABLE")
        );
    }

    #[cfg(windows)]
    #[test]
    fn windows_hello_availability_is_truthful_on_release_platform() {
        let availability = windows_hello_availability();
        assert!(matches!(
            availability,
            VerificationAvailability::Available
                | VerificationAvailability::NotPresent
                | VerificationAvailability::NotConfigured
                | VerificationAvailability::PolicyDisabled
                | VerificationAvailability::Busy
                | VerificationAvailability::Unavailable
                | VerificationAvailability::Failed
        ));
    }

    #[cfg(not(windows))]
    #[test]
    fn password_provider_is_truthfully_unavailable_off_windows() {
        assert_eq!(
            WindowsPasswordVerificationProvider.verify(),
            VerificationOutcome::Unavailable
        );
        let hello = WindowsHelloVerificationProvider::for_window(1).expect("nonzero window");
        assert_eq!(hello.availability(), VerificationAvailability::Unavailable);
        assert_eq!(hello.verify(), VerificationOutcome::Unavailable);
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
