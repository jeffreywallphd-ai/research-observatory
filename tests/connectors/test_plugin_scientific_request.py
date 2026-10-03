"""Scientific requests bind an exact broker call to one consented page."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_broker import PluginBrokerCall  # noqa: E402
from research_observatory_core.connectors.plugin_scientific_request import (  # noqa: E402
    PluginScientificRequestProblem,
    parse_plugin_scientific_request,
)

PREVIOUS = "0190a000-0000-7000-8000-000000000041"


class PluginScientificRequestTests(unittest.TestCase):
    def test_first_and_next_search_pages_bind_exact_broker_parameters(self):
        first = parse_plugin_scientific_request(b'{"query":"public records","pageSize":2}', "search")
        self.assertEqual(PluginBrokerCall(operation="search", query="public records", page_size=2), first.call)
        self.assertIsNone(first.previous_invocation_id)

        next_page = parse_plugin_scientific_request(
            (
                '{"query":"public records","pageSize":2,"cursor":"page-b","previousInvocationId":"' + PREVIOUS + '"}'
            ).encode(),
            "search",
        )
        self.assertEqual(
            PluginBrokerCall(operation="search", query="public records", page_size=2, cursor="page-b"),
            next_page.call,
        )
        self.assertEqual(PREVIOUS, next_page.previous_invocation_id)

    def test_cursor_and_predecessor_must_be_paired_and_request_is_closed(self):
        invalid = (
            b'{"query":"public records","cursor":"page-b"}',
            ('{"query":"public records","previousInvocationId":"' + PREVIOUS + '"}').encode(),
            b'{"query":"public records","query":"changed"}',
            b'{"query":"public records","url":"https://example.invalid/"}',
            b'{"query":"public records","pageSize":null}',
            b'{"query":"public records","previousInvocationId":"not-a-uuid","cursor":"page-b"}',
            b'{"query":"public records","cursor":"../private","previousInvocationId":"' + PREVIOUS.encode() + b'"}',
        )
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(PluginScientificRequestProblem):
                parse_plugin_scientific_request(raw, "search")

    def test_non_search_operation_cannot_add_pagination_or_change_scientific_field(self):
        self.assertEqual(
            PluginBrokerCall(operation="repository-metadata", repository_id="archive-01"),
            parse_plugin_scientific_request(b'{"repositoryId":"archive-01"}', "repository-metadata").call,
        )
        with self.assertRaises(PluginScientificRequestProblem):
            parse_plugin_scientific_request(b'{"repositoryId":"archive-01","cursor":"page-b"}', "repository-metadata")
