from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


class ApplicationLockSourceBoundaryTests(unittest.TestCase):
    def test_windows_hello_uses_window_bound_os_consent_without_secret_capture_or_fallback(self) -> None:
        source = (REPO / "apps" / "desktop" / "src-tauri" / "src" / "application_lock_verification.rs").read_text(
            encoding="utf-8"
        )
        hello_start = source.index("pub struct WindowsHelloVerificationProvider")
        hello_end = source.index("const CREDENTIAL_PROMPT_FLAGS", hello_start)
        hello_source = source[hello_start:hello_end]
        for required in (
            "UserConsentVerifier",
            "IUserConsentVerifierInterop",
            "RequestVerificationForWindowAsync",
            "CheckAvailabilityAsync",
            "HWND(window_handle",
            "UserConsentVerificationResult::Verified",
            "UserConsentVerificationResult::Canceled",
            "UserConsentVerificationResult::RetriesExhausted",
            "VerificationAvailability::PolicyDisabled",
        ):
            self.assertIn(required, hello_source)
        for forbidden in (
            "CredUIPromptForCredentialsW",
            "LogonUserW",
            "WindowsPasswordVerificationProvider",
            "password.0",
            "UserConsentVerifier::RequestVerificationAsync",
        ):
            self.assertNotIn(forbidden, hello_source)

        bridge_source = (REPO / "apps" / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
        status_start = bridge_source.index("fn application_lock_hello_availability(")
        status_end = bridge_source.index("#[tauri::command]", status_start + 1)
        status_bridge = bridge_source[status_start:status_end]
        status_signature = status_bridge[: status_bridge.index(") ->")]
        self.assertNotIn("provider:", status_signature)
        self.assertNotIn("outcome:", status_signature)
        self.assertIn("windows_hello_availability", status_bridge)
        primary_start = bridge_source.index("fn application_lock_unlock(")
        recovery_marker = "fn application_sign_in_password_recovery_prepare("
        recovery_start = bridge_source.index(recovery_marker, primary_start)
        primary_bridge = bridge_source[primary_start:recovery_start]
        self.assertNotIn("WindowsHelloVerificationProvider", primary_bridge)
        recovery_end = bridge_source.index("fn application_sign_in_transition_commit", recovery_start)
        recovery_bridge = bridge_source[recovery_start:recovery_end]
        self.assertIn("prepare_password_recovery_reset", recovery_bridge)
        self.assertNotIn("WindowsHelloVerificationProvider", recovery_bridge)
        transition_start = bridge_source.index("fn application_sign_in_transition_prepare(")
        transition_end = bridge_source.index("#[tauri::command]", transition_start + 1)
        transition_signature = bridge_source[transition_start:transition_end]
        self.assertNotIn("provider:", transition_signature)
        self.assertNotIn("outcome:", transition_signature)
        self.assertNotIn("window_handle:", transition_signature)

    def test_native_lock_uses_non_persisting_same_sid_windows_reauthentication(self) -> None:
        source = (REPO / "apps" / "desktop" / "src-tauri" / "src" / "application_lock_verification.rs").read_text(
            encoding="utf-8"
        )
        for required in (
            "CredUIPromptForCredentialsW",
            "CREDUI_FLAGS_ALWAYS_SHOW_UI",
            "CREDUI_FLAGS_GENERIC_CREDENTIALS",
            "CREDUI_FLAGS_DO_NOT_PERSIST",
            "CREDUI_FLAGS_VALIDATE_USERNAME",
            "GetUserNameExW",
            "NameSamCompatible",
            "LogonUserW",
            "OpenProcessToken",
            "GetTokenInformation",
            "EqualSid",
            "CloseHandle",
            "write_volatile",
        ):
            self.assertIn(required, source)
        self.assertIsNone(re.search(r"\bCREDUI_FLAGS_PERSIST\b", source))
        self.assertIn("let domain_pointer = optional_wide_pointer(&domain);", source)
        self.assertNotIn("| CREDUI_FLAGS_COMPLETE_USERNAME,", source)
        self.assertNotIn("CryptProtectData", source)

        lock_source = (REPO / "apps" / "desktop" / "src-tauri" / "src" / "application_lock.rs").read_text(
            encoding="utf-8"
        )
        bridge_source = (REPO / "apps" / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
        self.assertIn("WindowsPasswordVerificationProvider", lock_source)
        self.assertIn("NativeVerificationProvider", lock_source)
        self.assertIn("reservation.generation", lock_source)
        self.assertIn("stop_for_application_lock", lock_source)
        unlock_start = bridge_source.index("fn application_lock_unlock(")
        unlock_end = bridge_source.index("pub async fn dispatch_runtime_start", unlock_start)
        unlock_bridge = bridge_source[unlock_start:unlock_end]
        self.assertNotIn("provider:", unlock_bridge)
        self.assertNotIn("outcome:", unlock_bridge)

    def test_every_sensitive_native_bridge_checks_or_commits_under_the_lock_generation(self) -> None:
        source = (REPO / "apps" / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
        for command in ("core_runtime_start", "core_runtime_retry", "core_api_request"):
            start = source.index(f"fn {command}(")
            next_command = source.find("#[tauri::command]", start + 1)
            body = source[start : next_command if next_command >= 0 else len(source)]
            self.assertIn("begin_protected_action", body, command)
            self.assertIn("finish_protected_action", body, command)
        for command in ("support_bundle_preview", "support_bundle_export"):
            start = source.index(f"fn {command}(")
            next_command = source.find("#[tauri::command]", start + 1)
            body = source[start : next_command if next_command >= 0 else len(source)]
            self.assertIn("begin_protected_action", body, command)
            self.assertIn("commit_protected_action", body, command)
        lock_source = (REPO / "apps" / "desktop" / "src-tauri" / "src" / "application_lock.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("self.policy_store.stage(&pending.target)", lock_source)
        self.assertIn("self.policy_store.publish(staged, &pending.source)", lock_source)
        self.assertIn("inner.generation != pending.generation", lock_source)
        self.assertIn("inner.policy_source != pending.source", lock_source)
        self.assertIn("reauthentication_in_progress", lock_source)
        self.assertIn("TransitionProofClass::SameSidPasswordRecovery", lock_source)
        self.assertIn("sha256_hex(handle.as_bytes())", lock_source)
        self.assertIn('Err("RO-SIGN-IN-TRANSITION-REQUIRED")', source)
        self.assertIn("stop_for_application_lock", source)
        self.assertIn("support.clear_pending()", source)
        self.assertIn("lock.lock_if_idle()", source)
        self.assertIn('emit("application-lock-changed"', source)


if __name__ == "__main__":
    unittest.main()
