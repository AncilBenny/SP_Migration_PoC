"""Unit tests using synthetic, non-tenant SharePoint evidence."""
import unittest
from research_spike.classify import classify


class ClassifierResearchTests(unittest.TestCase):
    def test_graph_modern(self):
        e = {"deployment": "online",
             "graphSitePage": {"@odata.type": "#microsoft.graph.sitePage",
                               "canvasLayout": {"horizontalSections": []}}}
        r = classify(e)
        self.assertEqual((r["status"], r["pageFamily"], r["adapter"]),
                         ("confirmed", "modern", "modern-graph"))

    def test_modern_blank_canvas_is_not_empty_page_claim(self):
        r = classify({"graphSitePage": {"@odata.type": "#microsoft.graph.sitePage"}})
        self.assertEqual(r["pageFamily"], "modern")
        self.assertIn("MODERN_CANVAS_ABSENT_VERIFY_HOMEPAGE", r["warnings"])

    def test_verified_wiki_assessment(self):
        r = classify({"assessmentCoverageVerified": True,
                      "assessmentPageType": "WikiPage"})
        self.assertEqual((r["status"], r["pageFamily"]),
                         ("confirmed", "classic-wiki"))

    def test_verified_webpart_assessment(self):
        r = classify({"assessmentCoverageVerified": True,
                      "assessmentPageType": "WebPartPage"})
        self.assertEqual(r["adapter"], "classic-webpart")

    def test_publishing_field_inference(self):
        r = classify({"authenticatedFieldsVerified": True,
                      "fields": {"PublishingPageLayout": "source-layout-ref"}})
        self.assertEqual((r["status"], r["pageFamily"]),
                         ("tentative", "classic-publishing"))

    def test_verified_assessment_overrides_compatible_embedded_parts(self):
        r = classify({"assessmentCoverageVerified": True,
                      "assessmentPageType": "PublishingPage",
                      "authenticatedFieldsVerified": True,
                      "fields": {"PublishingPageLayout": "x"},
                      "classicZonesPresent": True})
        self.assertEqual(r["pageFamily"], "classic-publishing")

    def test_graph_classic_conflict(self):
        r = classify({"graphSitePage": {"@odata.type": "#microsoft.graph.sitePage",
                                       "canvasLayout": {}},
                      "assessmentCoverageVerified": True,
                      "assessmentPageType": "WikiPage"})
        self.assertEqual(r["status"], "needs-review")
        self.assertIsNone(r["adapter"])

    def test_unknown_custom_aspx_is_not_webpart_page(self):
        r = classify({"url": "https://example.org/Pages/a.aspx"})
        self.assertEqual((r["status"], r["pageFamily"], r["adapter"]),
                         ("unknown", "unknown", None))

    def test_public_dom_explicit_fallback(self):
        r = classify({"url": "https://example.org/path.aspx",
                      "publicHtmlObserved": True,
                      "allowPublicHtmlFallback": True})
        self.assertEqual(r["adapter"], "public-dom")
        self.assertEqual(r["pageFamily"], "unknown")

    def test_unverified_assessment_ignored(self):
        r = classify({"assessmentPageType": "WebPartPage",
                      "assessmentCoverageVerified": False})
        self.assertEqual(r["pageFamily"], "unknown")
        self.assertIn("ASSESSMENT_UNVERIFIED_IGNORED", r["warnings"])

    def test_blog_requires_special_adapter(self):
        r = classify({"assessmentPageType": "BlogPage",
                      "assessmentCoverageVerified": True})
        self.assertEqual(r["status"], "needs-review")
        self.assertIsNone(r["adapter"])

    def test_incompatible_deployment(self):
        r = classify({"deployment": "server-2016",
                      "graphSitePage": {"@odata.type": "#microsoft.graph.sitePage",
                                        "canvasLayout": {}}})
        self.assertEqual(r["status"], "needs-review")


if __name__ == "__main__":
    unittest.main()
