"""Actual Windows owned-tree lockdown and exact restoration, without inference."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


@unittest.skipUnless(os.name == "nt", "Windows DACL boundary")
class ParserAclTests(unittest.TestCase):
    def test_sdk_profile_nested_runtime_exact_restoration_on_success_and_failure(self):
        from workers.windows import lpac_launcher as win
        from workers.windows import no_write_acl as acl
        from workers.windows.recovery_guardian import start_guardian

        kernel, advapi, _userenv, _ole = win._api()
        acl._security_api(kernel, advapi)
        user = win._current_user_sid(advapi, kernel)
        for inject_failure in (False, True):
            with self.subTest(inject_failure=inject_failure):
                guardian = start_guardian()
                saved = []
                status = acl.AclRestoration()
                try:
                    nested = guardian.runtime / "image/_internal/models/layout"
                    nested.mkdir(parents=True)
                    for index in range(16):
                        (nested / f"synthetic-{index}.dat").write_bytes(b"synthetic runtime bytes")
                    saved = [
                        acl._open_saved(kernel, advapi, path, user)
                        for root in (guardian.profile.parent, guardian.runtime)
                        for path in acl._tree(root)
                    ]
                    guardian.seal()
                    try:
                        with acl.no_write_lpac_acl(
                            guardian.profile,
                            guardian.temp,
                            guardian.runtime,
                            guardian.sid_text,
                            kernel,
                            advapi,
                            native=True,
                            restoration=status,
                        ):
                            self.assertEqual((nested / "synthetic-0.dat").read_bytes(), b"synthetic runtime bytes")
                            for folder in (nested, guardian.temp):
                                with self.assertRaises(PermissionError):
                                    (folder / "new-plaintext.dat").write_bytes(b"denied")
                            if inject_failure:
                                raise RuntimeError("synthetic parser failure")
                    except RuntimeError as error:
                        self.assertTrue(inject_failure)
                        self.assertEqual(str(error), "synthetic parser failure")
                    self.assertTrue(status.restored)
                    for item in saved:
                        self.assertEqual(acl._sddl(kernel, advapi, item.handle), item.sddl)
                    (nested / "synthetic-0.dat").write_bytes(b"restored")
                finally:
                    for item in saved:
                        win._close(kernel, item.handle)
                        kernel.LocalFree(item.descriptor)
                    self.assertTrue(guardian.finish(restored=status.restored))
                self.assertFalse(guardian.profile.parent.exists())
                self.assertFalse(guardian.runtime.exists())

    def test_owned_runtime_and_profile_deny_write_then_restore_on_failure(self):
        from workers.windows import lpac_launcher as win
        from workers.windows.no_write_acl import no_write_lpac_acl

        kernel, advapi, _userenv, _ole = win._api()
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            runtime = root / "runtime"
            profile = root / "profile/AC"
            temp = profile / "Temp"
            runtime.mkdir()
            temp.mkdir(parents=True)
            for folder in (runtime, temp):
                (folder / "synthetic.dat").write_bytes(b"synthetic bytes")
            sid = "S-1-15-2-1-2-3-4-5-6-7"
            with (
                self.assertRaisesRegex(RuntimeError, "injected failure"),
                no_write_lpac_acl(profile, temp, runtime, sid, kernel, advapi, native=True),
            ):
                for folder in (runtime, temp):
                    self.assertEqual((folder / "synthetic.dat").read_bytes(), b"synthetic bytes")
                    with self.assertRaises(PermissionError):
                        (folder / "synthetic.dat").write_bytes(b"substitution")
                    with self.assertRaises(PermissionError):
                        (folder / "new.dat").write_bytes(b"plaintext")
                raise RuntimeError("injected failure")
            for folder in (runtime, temp):
                self.assertEqual((folder / "synthetic.dat").read_bytes(), b"synthetic bytes")
                (folder / "synthetic.dat").write_bytes(b"restored")


if __name__ == "__main__":
    unittest.main()
