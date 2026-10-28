"""Integrity checks for the derived, public-only research inventory.

No network calls, SharePoint auth, or copying of remote source files.
This does NOT prove that an actual site has been migrated.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "examples/research/public-evidence-derived.json"


class PublicEvidenceResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        cls.items = cls.inventory["items"]

    def test_all_three_supported_families_have_public_structural_evidence(self):
        structural = {"published_test_fixture", "open_source_template",
                      "open_source_page_layout", "public_source_page_file"}
        families = {x["family"] for x in self.items if x["kind"] in structural}
        self.assertTrue({"modern", "classic-content", "classic-publishing"}.issubset(families))

    def test_public_websites_are_not_labeled_as_sharepoint(self):
        for item in self.items:
            if item["kind"] == "live_public_rendered_page":
                with self.subTest(item=item["id"]):
                    self.assertEqual(item["family"], "unclassified")
                    self.assertEqual(item["confidence"], "visible-content-observed-only")
                    self.assertNotIn("pageType", item["facts"])

    def test_public_repository_evidence_is_reproducible(self):
        for item in self.items:
            if item["source"].get("repository"):
                with self.subTest(item=item["id"]):
                    self.assertTrue(item["source"]["url"].startswith("https://github.com/"))
                    self.assertEqual(len(item["source"]["blobSha"]), 40)
                    self.assertIn("/", item["source"]["repository"])
                    self.assertTrue(item["source"]["path"])

    def test_publishing_instance_and_template_are_not_misjoined(self):
        instance = next(x for x in self.items if x["id"] == "public-publishing-page-instance")
        template = next(x for x in self.items if x["id"] == "public-publishing-template-pnp")
        self.assertNotEqual(instance["source"]["repository"], template["source"]["repository"])
        self.assertTrue(any("DO NOT join" in s for s in template["limitations"]))

    def test_classic_wiki_placeholder_evidence_and_zones(self):
        wiki = next(x for x in self.items if x["id"] == "public-classic-wiki-pnp")
        zoned = next(x for x in self.items if x["id"] == "public-classic-zoned-template")
        self.assertEqual(wiki["facts"]["embeddedWebPartPlaceholderCount"], 3)
        self.assertEqual(zoned["facts"]["webPartZoneIds"], ["LeftColumn", "RightColumn"])

    def test_failed_cdph_fetch_remains_unknown(self):
        item = next(x for x in self.items if x["id"] == "public-cdph-main-site")
        self.assertEqual(item["kind"], "public_site_fetch_failure")
        self.assertEqual(item["family"], "unknown")
        self.assertEqual(item["facts"]["directFetchFailedWithStatus"], 502)


if __name__ == "__main__":
    unittest.main()
