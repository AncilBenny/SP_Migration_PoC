import json
from pathlib import Path
import tempfile
import unittest

from poc.engine import build
from poc.mapping import build_target, render_target, validate_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / 'poc/profiles/client-example.json').read_text())


class DestinationMappingTests(unittest.TestCase):
    def test_profile_and_independent_renderer(self):
        self.assertEqual(validate_profile(PROFILE)['id'], 'client-resource-portal')
        with tempfile.TemporaryDirectory() as tmp:
            default = Path(tmp) / 'default'
            target = Path(tmp) / 'target'
            build(ROOT / 'poc/samples/modern-demo.json', default, ROOT / 'poc/assets')
            report = build_target(default / 'page.ir.json', ROOT / 'poc/profiles/client-example.json', target)
            html = (target / 'index.html').read_text()
            self.assertIn('Useful resources', html)
            self.assertIn('target-resource', html)
            self.assertNotIn('CIR / Page migration', html)
            self.assertNotIn('<script', html)
            self.assertTrue((target / 'assets/health.svg').is_file())
            self.assertIn('src="assets/health.svg"', html)
            self.assertNotIn('src="https://example.org/sites/demo/SitePages/assets/', html)
            self.assertEqual((default / 'page.ir.json').read_bytes(), (target / 'page.ir.json').read_bytes())
            self.assertFalse(report['sharePointSourceReaderUsed'])
            self.assertIn('linkList:resourceCards', report['mappedComponents'])
            self.assertEqual(report['sourceFidelity'], 'not-evaluated-target-redesign-intent')
            self.assertEqual(len(report['irSha256']), 64)

    def test_two_target_profiles_same_ir_different_html(self):
        from poc.engine import normalize
        source = json.loads((ROOT / 'poc/samples/modern-demo.json').read_text())
        ir = normalize(source, asset_map=source['_assetMap'])
        cards_html, cards_css, _ = render_target(ir, PROFILE)
        other = json.loads(json.dumps(PROFILE))
        other['id'] = 'client-simple'
        other['components']['linkList'] = 'simpleLinks'
        other['colors']['primary'] = '#123456'
        links_html, links_css, _ = render_target(ir, other)
        self.assertIn('target-resource', cards_html)
        self.assertIn('target-links', links_html)
        self.assertNotEqual(cards_html, links_html)
        self.assertNotEqual(cards_css, links_css)

    def test_rejects_css_injection_and_unknown_components(self):
        for changes in [
            {'colors': {'primary': 'red;body{display:none}'}},
            {'components': {'linkList': 'scriptTag'}},
            {'components': {'notAKind': 'pageHeader'}},
            {'layout': {'maxWidthPx': '-100'}},
            {'font': 'url(//evil)'},
        ]:
            profile = json.loads(json.dumps(PROFILE))
            profile.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_profile(profile)

    def test_unsupported_component_diagnostic_preserved(self):
        from poc.engine import normalize
        source = json.loads((ROOT / 'poc/samples/modern-demo.json').read_text())
        ir = normalize(source, asset_map=source['_assetMap'])
        html, _, report = render_target(ir, PROFILE)
        self.assertIn('requires manual mapping', html)
        self.assertTrue(any(x['code'] == 'TARGET_UNKNOWN_CONTROL' for x in report['mappingWarnings']))

    def test_modified_ir_is_re_sanitized(self):
        from poc.engine import normalize
        source = json.loads((ROOT / 'poc/samples/modern-demo.json').read_text())
        ir = normalize(source, asset_map=source['_assetMap'])
        node = ir['tree']['children'][1]['children'][0]['children'][0]['children'][0]
        node['props']['safeHtml'] = '<p>Safe</p><script>bad()</script><a href="javascript:bad()">No</a>'
        html, _, _ = render_target(ir, PROFILE)
        self.assertNotIn('<script>', html)
        self.assertNotIn('javascript:', html)
        self.assertNotIn('bad()', html)


if __name__ == '__main__':
    unittest.main()
