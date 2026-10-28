import json
from pathlib import Path
import tempfile
import unittest

from poc.engine import build, normalize, processed_value, safe_url, sanitize_html, render_node

ROOT = Path(__file__).resolve().parents[1]
DEMO = json.loads((ROOT / "poc/samples/modern-demo.json").read_text())
DOC = json.loads((ROOT / "poc/samples/microsoft-graph-doc-example.json").read_text())


class EngineTests(unittest.TestCase):
    def test_documented_three_column_sample(self):
        ir = normalize(DOC)
        cols = ir["tree"]["children"][0]["children"][0]["children"]
        self.assertEqual(len(cols), 3)
        self.assertEqual([round(c["layout"]["widthFraction"], 4) for c in cols], [0.3333] * 3)
        self.assertEqual([c["children"][0]["kind"] for c in cols], ["richText"] * 3)

    def test_demo_two_column_image_links_and_unknown(self):
        ir = normalize(DEMO, asset_map=DEMO["_assetMap"])
        section = ir["tree"]["children"][1]
        cols = section["children"][0]["children"]
        self.assertAlmostEqual(cols[0]["layout"]["widthFraction"], 8 / 12)
        self.assertAlmostEqual(cols[1]["layout"]["widthFraction"], 4 / 12)
        self.assertEqual(cols[1]["children"][0]["kind"], "image")
        self.assertEqual(ir["assets"][0]["resolvedUrl"], "assets/health.svg")
        self.assertEqual(ir["tree"]["children"][2]["children"][0]["children"][0]["children"][0]["kind"], "linkList")
        self.assertTrue(any(d["code"] == "UNMAPPED_WEBPART" for d in ir["diagnostics"]))

    def test_html_sanitizes_scripts_handlers_and_urls(self):
        html = sanitize_html('<p onclick="evil()">Hi <a href="javascript:alert(1)" onmouseover="evil()">bad</a> <a href="/about">good</a><script>alert("xss")</script></p>', 'https://example.org/site/')
        self.assertNotIn('onclick', html)
        self.assertNotIn('onmouseover', html)
        self.assertNotIn('javascript:', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('xss', html)
        self.assertIn('https://example.org/about', html)

    def test_url_safety(self):
        self.assertEqual(safe_url('javascript:alert(1)', 'https://example.org'), '')
        self.assertEqual(safe_url('data:text/html,hello', 'https://example.org'), '')
        self.assertEqual(safe_url('//evil.example', 'https://example.org'), '')
        self.assertEqual(safe_url('/site/docs', 'https://example.org/path'), 'https://example.org/site/docs')

    def test_processed_image_sources_map_or_list(self):
        self.assertEqual(processed_value({'serverProcessedContent': {'imageSources': [{'key': 'imageSource', 'value': '/a.png'}]}}, 'imageSources', 'imageSource'), '/a.png')
        self.assertEqual(processed_value({'serverProcessedContent': {'imageSources': {'imageSource': '/b.png'}}}, 'imageSources', 'imageSource'), '/b.png')

    def test_non_sitepage_rejected(self):
        with self.assertRaises(ValueError):
            normalize({'@odata.type': '#microsoft.graph.list', 'canvasLayout': {}})
        with self.assertRaises(ValueError):
            normalize({'title': 'missing canvas'})

    def test_offline_build_generates_all_demo_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'out'
            report = build(ROOT / 'poc/samples/modern-demo.json', out, ROOT / 'poc/assets')
            for filename in ['index.html', 'style.css', 'page.ir.json', 'report.json', 'assets/health.svg']:
                self.assertTrue((out / filename).is_file(), filename)
            html = (out / 'index.html').read_text()
            self.assertIn('Community health resources', html)
            self.assertIn('Helpful links', html)
            self.assertIn('Component requires review', html)
            self.assertNotIn('<script', html)
            self.assertEqual(report['components']['unknown'], 1)
            self.assertEqual(report['webPartsFound'], 4)
            self.assertEqual(report['mappedParts'], 3)
            self.assertEqual(report['coveragePercent'], 75.0)

    def test_unknown_not_echoed_as_untrusted_html(self):
        html = render_node({'kind': 'unknown', 'props': {'sourceType': '<script>alert(1)</script>'}})
        self.assertNotIn('<script', html)
        self.assertIn('requires review', html)


if __name__ == '__main__':
    unittest.main()
