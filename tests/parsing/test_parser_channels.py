"""Real Windows stdout separation; synthetic conversion is not LPAC proof."""

import hashlib
import io
import mimetypes
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from workers.windows.parser_worker import _builtin_mime_types  # noqa: E402
from workers.windows.protocol import encode_frame, read_binary_frame, read_frame  # noqa: E402


class OfflineMimeTests(unittest.TestCase):
    def test_ambient_mime_authority_cannot_replace_builtin_pdf_and_docx_types(self):
        saved = {
            name: getattr(mimetypes, name)
            for name in ("inited", "_db", "suffix_map", "types_map", "encodings_map", "common_types")
        }
        try:
            # The ordinary initializer would read these ambient definitions.
            # Neither a denied registry nor known MIME files supplies authority.
            with (
                patch.object(mimetypes.MimeTypes, "read_windows_registry", side_effect=PermissionError),
                patch.object(mimetypes, "knownfiles", ["ambient-private-mime-file"]),
                patch.object(mimetypes.MimeTypes, "read", side_effect=AssertionError("ambient file read")),
            ):
                _builtin_mime_types()
                self.assertEqual(mimetypes.guess_type("declared.pdf"), ("application/pdf", None))
                self.assertEqual(
                    mimetypes.guess_type("declared.docx")[0],
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
                mimetypes.add_type("application/x-synthetic", ".synthetic")
                self.assertEqual(mimetypes.guess_type("declared.synthetic")[0], "application/x-synthetic")
        finally:
            for name, value in saved.items():
                setattr(mimetypes, name, value)


@unittest.skipUnless(sys.platform == "win32", "native Windows standard-handle boundary")
class ParserChannelTests(unittest.TestCase):
    def test_python_crt_and_win32_library_stdout_cannot_corrupt_private_frames(self):
        source = b"synthetic channel fixture"
        nonce = "a" * 32
        request = {
            "protocolVersion": "1.0",
            "jobNonce": nonce,
            "sequence": 0,
            "operation": "parse-document",
            "format": "txt",
            "inputLength": len(source),
            "inputSha256": hashlib.sha256(source).hexdigest(),
        }
        end = {"protocolVersion": "1.0", "jobNonce": nonce, "sequence": 1, "operation": "parse-end"}
        wire = encode_frame(request) + len(source).to_bytes(4, "big") + source + b"\0" * 4 + encode_frame(end)
        operator = """
import ctypes
from ctypes import wintypes
from workers.windows import parser_worker as worker
def synthetic_parse(source,kind,assets):
    print("synthetic Python stdout",flush=True)
    crt=ctypes.CDLL("ucrtbase")
    crt.__acrt_iob_func.argtypes=[ctypes.c_uint]
    crt.__acrt_iob_func.restype=ctypes.c_void_p
    crt.fwrite.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_size_t,ctypes.c_void_p]
    crt.fwrite.restype=ctypes.c_size_t
    crt.fflush.argtypes=[ctypes.c_void_p]
    crt_stdout=crt.__acrt_iob_func(1)
    text=b"synthetic CRT stdout\\n"
    assert crt.fwrite(text,1,len(text),crt_stdout)==len(text)
    assert crt.fflush(crt_stdout)==0
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.GetStdHandle.argtypes=[wintypes.DWORD]
    kernel.GetStdHandle.restype=wintypes.HANDLE
    kernel.WriteFile.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]
    count=wintypes.DWORD();text=b"synthetic Win32 stdout\\n"
    assert kernel.WriteFile(kernel.GetStdHandle(0xFFFFFFF5),text,len(text),ctypes.byref(count),None)
    return b"synthetic response"
worker.parse_document=synthetic_parse
raise SystemExit(worker.main())
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", operator],
            cwd=REPO,
            input=wire,
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        output = io.BytesIO(result.stdout)
        response = read_frame(output, expected_nonce=nonce, expected_sequence=2)
        self.assertEqual(response["operation"], "parse-result")
        self.assertEqual(read_binary_frame(output), b"synthetic response")
        self.assertEqual(read_binary_frame(output), b"")
        self.assertEqual(output.read(), b"")
        for marker in (b"synthetic Python stdout", b"synthetic CRT stdout", b"synthetic Win32 stdout"):
            self.assertIn(marker, result.stderr)
            self.assertNotIn(marker, result.stdout)


if __name__ == "__main__":
    unittest.main()
