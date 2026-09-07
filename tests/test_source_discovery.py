import json
import io
import unittest
from datetime import date
from pathlib import Path

from urllib.parse import parse_qs, urlparse

from spikes.source_discovery.discovery import (
    DiscoveryError,
    build_collection_url,
    discover,
    fetch_live,
    load_json,
    normalize_meeting,
)
from pypdf import PdfWriter

from spikes.source_discovery.pdf_inspection import classify_link, inspect_pdf_bytes, merge_evidence

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "source_discovery"


class SourceDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = load_json(FIXTURES / "meetings.json")
        cls.evidence = load_json(FIXTURES / "evidence_index.json")
        cls.manifest = discover(
            cls.payload["value"],
            date(2025, 11, 3),
            date(2026, 8, 11),
            cls.evidence,
            cls.payload["retrieved_at"],
        )

    def by_id(self, source_id):
        return next(item for item in self.manifest["meetings"] if item["source_meeting_id"] == source_id)

    def test_six_varied_meetings_are_normalized(self):
        self.assertEqual(6, self.manifest["meeting_count"])
        self.assertEqual(
            {
                "council",
                "community_affairs_and_planning_committee",
                "general_government_committee",
                "special_council",
                "committee_of_adjustment",
            },
            {item["normalized_type"] for item in self.manifest["meetings"]},
        )

    def test_mislabeled_document_fields_are_not_silently_trusted(self):
        meeting = self.by_id("0fa51ad4-5576-f111-ab0e-3833c5fa4def")
        self.assertEqual(["minutes", "minutes"], [item["kind"] for item in meeting["documents"]])
        self.assertEqual(["adopted", "draft"], [item["status"] for item in meeting["documents"]])
        self.assertTrue(any("agenda field" in warning for warning in meeting["warnings"]))

    def test_pdf_quality_and_linked_documents_are_recorded(self):
        mixed = self.by_id("f96faf0b-5876-f111-ab0e-3833c5fa4def")
        self.assertEqual("mixed", mixed["documents"][0]["pdf_inspection"]["pdf_quality"])
        special = self.by_id("35ceda6a-c291-f111-8077-3833c5fa4def")
        kinds = [item["kind"] for item in special["documents"]]
        self.assertIn("report", kinds)
        self.assertIn("attachment", kinds)

    def test_missing_documents_and_uninspected_links_are_explicit(self):
        raw = {
            "crf6e_cityconnectionsmeetingsid": "missing-documents",
            "crf6e_title": "01-02-2026 Example Committee",
            "crf6e_meetingtype": "Example Committee",
            "crf6e_meetingdate": "2026-01-02T18:00:00Z",
            "crf6e_meetingstatus": "Completed",
        }
        meeting = normalize_meeting(raw, discovered_at="2026-01-03T00:00:00Z")
        self.assertEqual([], meeting["documents"])
        self.assertIn("No agenda document was discovered.", meeting["warnings"])
        self.assertIn("No minutes document was discovered.", meeting["warnings"])

        raw["crf6e_agendalink"] = "https://example.test/agenda.pdf"
        raw["crf6e_meetingagenda_name"] = "Agenda.pdf"
        meeting = normalize_meeting(raw, discovered_at="2026-01-03T00:00:00Z")
        self.assertTrue(any("links were not inspected" in warning for warning in meeting["warnings"]))

    def test_wrong_portal_title_date_is_visible(self):
        meeting = self.by_id("db736fcf-5976-f111-ab0e-70a8a50cc0b4")
        self.assertTrue(any("title date conflicts" in warning for warning in meeting["warnings"]))

    def test_unavailable_video_and_transcript_are_explicit(self):
        meeting = self.by_id("db736fcf-5976-f111-ab0e-70a8a50cc0b4")
        self.assertEqual("unavailable", meeting["video"]["availability"])
        self.assertEqual("unavailable", meeting["video"]["transcript_status"])
        self.assertTrue(any("manual review" in warning for warning in meeting["warnings"]))

    def test_combined_stream_is_not_exclusive(self):
        meeting = self.by_id("4db4ae62-5876-f111-ab0e-70a8a50cc0b4")
        self.assertEqual("BZAPz7ryBKE", meeting["video"]["youtube_id"])
        self.assertEqual(["97342862-5876-f111-ab0e-3833c5fa4def"], meeting["video"]["shared_with_source_ids"])

    def test_synthetic_identity_is_stable(self):
        raw = {
            "crf6e_title": "Example Committee",
            "crf6e_meetingtype": "Example Committee",
            "crf6e_meetingdate": "2026-01-02T18:00:00Z",
            "crf6e_meetingstatus": "Scheduled",
        }
        first = normalize_meeting(raw, discovered_at="2026-01-01T00:00:00Z")
        second = normalize_meeting(raw, discovered_at="2026-01-01T00:00:00Z")
        self.assertEqual(first["local_id"], second["local_id"])
        self.assertTrue(first["local_id"].startswith("ajax:synthetic:"))

    def test_repeated_fixture_run_is_idempotent(self):
        second = discover(
            self.payload["value"], date(2025, 11, 3), date(2026, 8, 11), self.evidence, self.payload["retrieved_at"]
        )
        self.assertEqual(self.manifest, second)

    def test_committed_sample_manifest_is_reproducible(self):
        expected = load_json(FIXTURES / "sample_manifest.json")
        self.assertEqual(expected, self.manifest)

    def test_live_query_uses_ajax_local_date_boundaries(self):
        winter = parse_qs(urlparse(build_collection_url(date(2025, 11, 3), date(2025, 11, 3))).query)["$filter"][0]
        summer = parse_qs(urlparse(build_collection_url(date(2026, 5, 19), date(2026, 5, 19))).query)["$filter"][0]
        self.assertIn("2025-11-03T05:00:00Z", winter)
        self.assertIn("2025-11-04T05:00:00Z", winter)
        self.assertIn("2026-05-19T04:00:00Z", summer)
        self.assertIn("2026-05-20T04:00:00Z", summer)

    def test_live_fetch_follows_odata_pagination(self):
        class Client:
            def __init__(self):
                self.calls = []

            def get(self, url):
                self.calls.append(url)
                if len(self.calls) == 1:
                    return {"value": [{"id": 1}], "@odata.nextLink": "https://example.test/next"}
                return {"value": [{"id": 2}]}

        client = Client()
        self.assertEqual([{"id": 1}, {"id": 2}], fetch_live(date(2026, 1, 1), date(2026, 1, 2), client))
        self.assertEqual(2, len(client.calls))

    def test_document_link_classifier_rejects_navigation_links(self):
        self.assertIsNone(classify_link("https://www.ajax.ca/live"))
        attachment = classify_link("https://example.test/Reference%20Documents/ATT-1%20-%20DRAFT%20Policy.pdf")
        self.assertEqual("attachment", attachment["kind"])
        self.assertEqual("draft", attachment["status"])

    def test_in_memory_pdf_inspection_is_deterministic(self):
        output = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.write(output)
        first = inspect_pdf_bytes(output.getvalue())
        second = inspect_pdf_bytes(output.getvalue())
        self.assertEqual(first, second)
        self.assertEqual("scanned", first["pdf_quality"])
        self.assertTrue(first["content_hash"].startswith("sha256:"))

    def test_failed_pdf_refresh_removes_stale_inspection_evidence(self):
        base = {
            "meetings": {
                "meeting-1": {
                    "document_overrides": {
                        "agenda": {
                            "kind": "agenda_package",
                            "content_hash": "sha256:old",
                            "pdf_inspection": {"pdf_quality": "text"},
                        }
                    }
                }
            }
        }
        failed = {
            "meetings": {
                "meeting-1": {"document_overrides": {"agenda": {"inspection_error": "timeout"}}}
            }
        }
        agenda = merge_evidence(base, failed)["meetings"]["meeting-1"]["document_overrides"]["agenda"]
        self.assertEqual("agenda_package", agenda["kind"])
        self.assertEqual("timeout", agenda["inspection_error"])
        self.assertNotIn("content_hash", agenda)
        self.assertNotIn("pdf_inspection", agenda)

    def test_date_range_filters_fixture(self):
        result = discover(
            self.payload["value"], date(2026, 5, 19), date(2026, 5, 19), self.evidence, self.payload["retrieved_at"]
        )
        self.assertEqual(1, result["meeting_count"])

    def test_invalid_range_fails(self):
        with self.assertRaises(DiscoveryError):
            discover([], date(2026, 2, 1), date(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
