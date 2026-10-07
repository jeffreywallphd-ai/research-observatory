"""Native DLL compatibility must never discard assembly dependencies or elevation."""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools")]
from parser_pe_variant import inert_dll_manifest  # noqa: E402

INERT = b"""<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
<trustInfo xmlns="urn:schemas-microsoft-com:asm.v3"><security><requestedPrivileges>
<requestedExecutionLevel level="asInvoker" uiAccess="false"/>
</requestedPrivileges></security></trustInfo></assembly>"""


class ParserManifestTests(unittest.TestCase):
    def test_dependency_elevation_ui_access_and_entities_are_not_removable(self):
        self.assertTrue(inert_dll_manifest(INERT))
        for data in (
            INERT.replace(b"asInvoker", b"requireAdministrator"),
            INERT.replace(b'uiAccess="false"', b'uiAccess="true"'),
            INERT.replace(b"</assembly>", b"<dependency/></assembly>"),
            INERT.replace(b"manifestVersion=", b"unknown="),
            b'<!DOCTYPE assembly [<!ENTITY x "expanded">]>' + INERT,
            INERT.replace(b"<security>", b"<security>unrecognized policy"),
        ):
            with self.subTest(data=data):
                self.assertFalse(inert_dll_manifest(data))


if __name__ == "__main__":
    unittest.main()
