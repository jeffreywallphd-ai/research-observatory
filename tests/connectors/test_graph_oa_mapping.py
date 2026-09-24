"""Fabricated OA/graph observations, never assertions about real scholarship."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.contracts import ConnectorCursor  # noqa: E402
from research_observatory_core.connectors.providers import (  # noqa: E402
    ProviderProblem,
    capabilities,
    compile_request,
    map_response,
)

from tests.connectors.test_scholarly_mapping import NOW, request  # noqa: E402

DOI = "10.99999/synthetic-adapter"
PAPER = "a" * 40
OTHER = "b" * 40


def oa_request(**changes):
    return request(
        "unpaywall",
        sourceApiVersion="2",
        query={"kind": "oa-resolution", "identifier": {"scheme": "doi", "value": DOI}},
        **changes,
    )


def graph_request(query=None, **changes):
    return request(
        "semantic-scholar",
        sourceApiVersion="1",
        query=query or {"kind": "lookup", "identifiers": [{"scheme": "semantic-scholar", "value": PAPER}]},
        **changes,
    )


def paper(identity=PAPER):
    return {
        "paperId": identity,
        "externalIds": {"DOI": DOI},
        "title": "Synthetic graph fixture",
        "authors": [{"authorId": "123", "name": "Synthetic Author"}],
        "year": 2026,
        "publicationDate": None,
        "venue": "Synthetic Venue",
        "isOpenAccess": True,
        "openAccessPdf": {"url": "https://example.invalid/synthetic.pdf", "status": "GREEN", "license": None},
    }


def oa_document():
    location = {
        "url": "https://example.invalid/synthetic.pdf",
        "url_for_pdf": "https://example.invalid/synthetic.pdf",
        "url_for_landing_page": "https://example.invalid/record",
        "host_type": "repository",
        "license": None,
        "version": "acceptedVersion",
        "is_best": True,
    }
    return {
        "doi": DOI,
        "title": "Synthetic OA fixture",
        "is_oa": True,
        "oa_status": "green",
        "best_oa_location": location,
        "oa_locations": [location, location | {"license": "cc-by", "is_best": False}],
    }


def fields(record):
    return {field.name: json.loads(field.value) for field in record.fields}


class GraphOaMappingTests(unittest.TestCase):
    def test_provider_operations_versions_and_required_contact_are_explicit(self):
        oa, graph = capabilities("unpaywall"), capabilities("semantic-scholar")
        self.assertEqual(("oa-resolution",), oa.operations)
        self.assertEqual(("contact",), oa.required_settings)
        self.assertEqual("2", oa.source_api_version)
        self.assertEqual(("citations", "lookup", "recommendations"), graph.operations)
        self.assertEqual("1", graph.source_api_version)

    def test_oa_request_is_fixed_doi_endpoint_without_contact_in_scientific_plan(self):
        value = oa_request()
        plan = compile_request(value)
        self.assertEqual("api.unpaywall.org", plan.host)
        self.assertEqual("/v2/10.99999%2Fsynthetic-adapter", plan.path)
        self.assertEqual((), plan.parameters)
        self.assertEqual("GET", plan.method)
        self.assertIsNone(plan.body)
        with self.assertRaises(ProviderProblem):
            compile_request(request("unpaywall", sourceApiVersion="2"))

    def test_oa_locations_and_conflicting_license_observations_are_preserved(self):
        document = oa_document()
        result = map_response(oa_request(), document, retrieved_at=NOW)
        self.assertEqual(document["oa_locations"], fields(result.records[0])["candidate.oa-locations"])
        self.assertEqual("open", result.records[0].terms.access)
        self.assertEqual("not-reported", result.records[0].terms.license.state)
        self.assertIsNone(result.next_cursor)
        closed = document | {"is_oa": False, "oa_status": "closed", "best_oa_location": None, "oa_locations": []}
        self.assertEqual("closed", map_response(oa_request(), closed, retrieved_at=NOW).records[0].terms.access)
        with self.assertRaises(ProviderProblem):
            map_response(oa_request(), document | {"doi": "10.99999/unrequested"}, retrieved_at=NOW)

    def test_lookup_retains_provider_ids_and_rejects_unrequested_paper(self):
        record = map_response(graph_request(), paper(), retrieved_at=NOW).records[0]
        self.assertEqual(PAPER, record.raw_identifier.value)
        self.assertIn(("doi", DOI), [(item.scheme, item.value) for item in record.identifiers])
        with self.assertRaises(ProviderProblem):
            map_response(graph_request(), paper(OTHER), retrieved_at=NOW)

    def test_graph_direction_source_seed_and_edge_observations_survive(self):
        for direction, key in (("citations", "citingPaper"), ("references", "citedPaper")):
            with self.subTest(direction=direction):
                query = {
                    "kind": "citations",
                    "seed": {"scheme": "semantic-scholar", "value": PAPER},
                    "direction": direction,
                }
                value = graph_request(query)
                edge = {key: paper(OTHER), "contexts": ["Synthetic context"], "isInfluential": False}
                document = {
                    "offset": 0,
                    "next": 1,
                    "data": [edge],
                }
                result = map_response(value, document, retrieved_at=NOW)
                projection = fields(result.records[0])
                self.assertEqual(query, projection["candidate.discovery"])
                self.assertEqual("semantic-scholar", result.records[0].provider_id)
                self.assertEqual(edge, projection["edge"])
                self.assertIsNotNone(result.next_cursor)
                assert result.next_cursor is not None
                self.assertEqual("1", result.next_cursor.value)
                self.assertEqual(value.scientific_sha256(), result.next_cursor.request_sha256)
                for invalid in (document | {"offset": 1}, document | {"next": 0}, document | {"data": [{key: None}]}):
                    with self.assertRaises(ProviderProblem):
                        map_response(value, invalid, retrieved_at=NOW)

    def test_recommendations_preserve_positive_and_negative_seeds_in_bounded_post(self):
        query = {
            "kind": "recommendations",
            "positiveSeeds": [{"scheme": "semantic-scholar", "value": PAPER}],
            "negativeSeeds": [{"scheme": "doi", "value": DOI}],
        }
        value = graph_request(query)
        plan = compile_request(value)
        self.assertEqual("POST", plan.method)
        self.assertEqual("/recommendations/v1/papers", plan.path)
        assert plan.body is not None
        self.assertEqual({"positivePaperIds": [PAPER], "negativePaperIds": ["DOI:" + DOI]}, json.loads(plan.body))
        result = map_response(value, {"recommendedPapers": [paper(OTHER)]}, retrieved_at=NOW)
        self.assertEqual(query, fields(result.records[0])["candidate.discovery"])
        self.assertIsNone(result.next_cursor)
        overlap = copy.deepcopy(query)
        overlap["positiveSeeds"] = [{"scheme": "doi", "value": DOI.upper()}]
        with self.assertRaises(ProviderProblem):
            compile_request(graph_request(overlap))

    def test_cursor_requires_canonical_numeric_offset_and_matching_response_offset(self):
        query = {"kind": "citations", "seed": {"scheme": "semantic-scholar", "value": PAPER}, "direction": "references"}
        value = graph_request(query)
        for offset in ("-1", "+1", "01", "1.0", "https://example.invalid/", "999999999999999999999"):
            with self.subTest(offset=offset), self.assertRaises(ProviderProblem):
                cursor = ConnectorCursor(
                    provider_id=value.provider_id,
                    project_id=value.project_id,
                    request_sha256=value.scientific_sha256(),
                    page_index=1,
                    value=offset,
                    expires_at=None,
                )
                compile_request(value.model_copy(update={"cursor": cursor}))
