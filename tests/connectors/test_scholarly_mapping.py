"""Source semantics, hostile values and replay using explicitly synthetic data."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.contracts import ConnectorRequest  # noqa: E402
from research_observatory_core.connectors.providers import (  # noqa: E402
    ProviderProblem,
    capabilities,
    compile_request,
    map_response,
)

NOW = "2026-01-01T00:00:00.000Z"


def request(provider: str, **changes) -> ConnectorRequest:
    original = json.loads((REPO / "tests/fixtures/scholarly-metadata/connector-page.v1.json").read_text("utf-8"))
    return ConnectorRequest.model_validate(
        original["request"]
        | {
            "providerId": provider,
            "sourceApiVersion": None,
            "pageSize": 1,
            "query": {"kind": "lookup", "identifiers": [{"scheme": "doi", "value": "10.99999/synthetic-adapter"}]},
        }
        | changes
    )


def fixture(provider: str):
    return json.loads(
        (REPO / f"tests/fixtures/scholarly-metadata/{provider}-page.synthetic.v1.json").read_text("utf-8")
    )


def search(**changes):
    return {
        "kind": "search",
        "text": "synthetic topic",
        "field": "title",
        "filters": [],
        "sort": [],
        "fields": [],
    } | changes


class ScholarlyMappingTests(unittest.TestCase):
    def test_lookup_cannot_publish_an_unrequested_identifier(self):
        value = request("crossref")
        document = {"status": "ok", "message-type": "work", "message": fixture("crossref")["message"]["items"][0]}
        document["message"]["DOI"] = "10.99999/unrequested"
        with self.assertRaises(ProviderProblem):
            map_response(value, document, retrieved_at=NOW)
        document = fixture("openalex")
        document["results"][0]["doi"] = "https://doi.org/10.99999/unrequested"
        with self.assertRaises(ProviderProblem):
            map_response(request("openalex"), document, retrieved_at=NOW)

    def test_capabilities_are_explicit_and_account_optional(self):
        for provider, ceiling, schemes in (("openalex", 100, ("doi", "openalex")), ("crossref", 1000, ("doi",))):
            value = capabilities(provider)
            self.assertEqual("ready", value.configuration)
            self.assertEqual(ceiling, value.maximum_page_size)
            self.assertEqual(schemes, value.identifier_schemes)
            self.assertEqual((), value.required_settings)
            with self.assertRaises(ProviderProblem):
                compile_request(request(provider, adapterVersion="2.0.0"))

    def test_title_and_any_queries_do_not_silently_change_semantics(self):
        alex = compile_request(request("openalex", query=search()))
        cross = compile_request(request("crossref", query=search()))
        self.assertEqual("title.search:synthetic topic", dict(alex.parameters)["filter"])
        self.assertEqual("synthetic topic", dict(cross.parameters)["query.title"])
        for provider in ("openalex", "crossref"):
            result = compile_request(request(provider, query=search(field="any")))
            self.assertIn("search" if provider == "openalex" else "query", dict(result.parameters))
        with self.assertRaises(ProviderProblem) as failure:
            compile_request(request("crossref", query=search(field="abstract")))
        self.assertEqual("unsupported-operation", failure.exception.code)

    def test_filter_grammar_cannot_inject_or_invert_inclusive_years(self):
        filters = [{"field": "publication-year", "operator": "gte", "value": "2020"}]
        alex = dict(compile_request(request("openalex", query=search(filters=filters))).parameters)
        cross = dict(compile_request(request("crossref", query=search(filters=filters))).parameters)
        self.assertIn("from_publication_date:2020-01-01", alex["filter"])
        self.assertEqual("from-pub-date:2020-01-01", cross["filter"])
        for value in ("2020,doi:evil", "true|false", "!article", "1", "2020\n"):
            with self.subTest(value=value), self.assertRaises(ProviderProblem):
                compile_request(request("openalex", query=search(filters=[filters[0] | {"value": value}])))
        for text in ("safe,doi:other", "safe|other", "safe\x00"):
            with self.subTest(text=text), self.assertRaises(ProviderProblem):
                compile_request(request("openalex", query=search(text=text)))

    def test_unsupported_sort_is_not_replaced_by_another_order(self):
        order = [{"field": "publication-date", "direction": "descending"}]
        self.assertEqual(
            "publication_date:desc",
            dict(compile_request(request("openalex", query=search(sort=order))).parameters)["sort"],
        )
        # Crossref documents that published/issued sorts cannot combine with cursors.
        with self.assertRaises(ProviderProblem):
            compile_request(request("crossref", query=search(sort=order)))

    def test_lookup_compiles_only_fixed_destinations_and_preserves_doi_punctuation(self):
        lookup = {"kind": "lookup", "identifiers": [{"scheme": "doi", "value": "https://doi.org/10.99999/A.(B)/C"}]}
        cross = compile_request(request("crossref", query=lookup))
        self.assertEqual("api.crossref.org", cross.host)
        self.assertEqual("/works/10.99999%2Fa.%28b%29%2Fc", cross.path)
        self.assertEqual((), cross.parameters)
        alex = compile_request(request("openalex", query=lookup))
        self.assertEqual("api.openalex.org", alex.host)
        self.assertEqual("doi:https://doi.org/10.99999/a.(b)/c", dict(alex.parameters)["filter"])
        for value in ("https://internal.invalid/x", "10.99999/a|b", "10.99999/a,b"):
            bad = {"kind": "lookup", "identifiers": [{"scheme": "doi", "value": value}]}
            with self.subTest(value=value), self.assertRaises(ProviderProblem):
                compile_request(request("openalex", query=bad))

    def test_bounded_batch_projection_and_resume_bindings(self):
        ids = [{"scheme": "openalex", "value": "W999999999901"}, {"scheme": "openalex", "value": "W999999999902"}]
        alex = compile_request(request("openalex", pageSize=2, query={"kind": "lookup", "identifiers": ids}))
        self.assertEqual("openalex:W999999999901|W999999999902", dict(alex.parameters)["filter"])
        selected = compile_request(request("crossref", query=search(fields=["title", "authors"])))
        self.assertEqual("DOI,title,author,license", dict(selected.parameters)["select"])
        original = request("openalex", query=search())
        page = map_response(original, fixture("openalex"), retrieved_at=NOW)
        resumed = ConnectorRequest.model_validate(original.model_dump() | {"cursor": page.next_cursor})
        self.assertEqual("synthetic-page-2", dict(compile_request(resumed).parameters)["cursor"])
        self.assertEqual(original.scientific_sha256(), resumed.scientific_sha256())
        self.assertNotEqual(original.page_sha256(), resumed.page_sha256())

    def test_known_items_preserve_source_assertions_and_candidates(self):
        for provider in ("openalex", "crossref"):
            page = map_response(request(provider, query=search()), fixture(provider), retrieved_at=NOW)
            self.assertEqual(1, len(page.records))
            item = page.records[0]
            self.assertEqual(provider, item.provider_id)
            self.assertIn(("doi", "10.99999/synthetic-adapter"), {(x.scheme, x.value) for x in item.identifiers})
            fields = {x.name: x for x in item.fields}
            self.assertIn("candidate.title", fields)
            self.assertIn("candidate.authors", fields)
            self.assertIn("candidate.date", fields)
            self.assertIn("candidate.venue", fields)
            self.assertIn("candidate.references", fields)
            self.assertIn("future_field" if provider == "openalex" else "future-field", fields)
            self.assertEqual(NOW, item.retrieved_at)
            self.assertEqual("reported", item.terms.license.state)
            self.assertEqual("reported", page.terms.terms.state)
            self.assertFalse(hasattr(item, "work_id"))
            self.assertIsNotNone(page.next_cursor)
        cross = map_response(request("crossref", query=search()), fixture("crossref"), retrieved_at=NOW)
        self.assertEqual("unknown", cross.records[0].terms.access)  # license does not prove OA
        assert cross.next_cursor is not None
        self.assertIsNone(cross.next_cursor.expires_at)
        self.assertIn("non-snapshot-pagination", cross.warnings)

    def test_empty_missing_and_malformed_are_distinct(self):
        for provider in ("openalex", "crossref"):
            document = fixture(provider)
            container = document if provider == "openalex" else document["message"]
            key = "results" if provider == "openalex" else "items"
            container[key] = []
            if provider == "openalex":
                document["meta"]["next_cursor"] = None
            page = map_response(request(provider, query=search()), document, retrieved_at=NOW)
            self.assertEqual((), page.records)
            self.assertIsNone(page.next_cursor)
            del container[key]
            with self.assertRaises(ProviderProblem) as failure:
                map_response(request(provider, query=search()), document, retrieved_at=NOW)
            self.assertEqual("incompatible-response", failure.exception.code)

    def test_singleton_crossref_and_malformed_record_are_not_invented_success(self):
        source = fixture("crossref")
        single = {"status": "ok", "message-type": "work", "message": source["message"]["items"][0]}
        result = map_response(request("crossref"), single, retrieved_at=NOW)
        self.assertEqual(1, len(result.records))
        self.assertIsNone(result.next_cursor)
        for mutate in (lambda x: x.pop("DOI"), lambda x: x.update({"author": "not-a-list"})):
            bad = copy.deepcopy(single)
            mutate(bad["message"])
            with self.assertRaises(ProviderProblem):
                map_response(request("crossref"), bad, retrieved_at=NOW)

    def test_repeated_cursor_duplicate_records_and_oversized_fields_fail_closed(self):
        original = request("openalex", query=search())
        document = fixture("openalex")
        page = map_response(original, document, retrieved_at=NOW)
        resumed = ConnectorRequest.model_validate(original.model_dump() | {"cursor": page.next_cursor})
        with self.assertRaises(ProviderProblem):
            map_response(resumed, document, retrieved_at=NOW)
        document["results"] *= 2
        with self.assertRaises(ProviderProblem):
            map_response(request("openalex", query=search(), pageSize=2), document, retrieved_at=NOW)
        document = fixture("openalex")
        document["results"][0]["title"] = "x" * 65537
        with self.assertRaises(ProviderProblem):
            map_response(original, document, retrieved_at=NOW)


if __name__ == "__main__":
    unittest.main()
