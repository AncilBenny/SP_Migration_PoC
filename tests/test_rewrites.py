import json
from pathlib import Path
import unittest

from poc.engine import normalize
from poc.mapping import render_target, validate_profile
from poc.rewrites import rewrite_url, rewrite_rich_html, validate_url_mappings

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / 'poc/profiles/client-example.json').read_text())


class URLRewriteTests(unittest.TestCase):
    def test_source_url_stays_in_ir_but_mapping_changes_destination(self):
        source = json.loads((ROOT / 'poc/samples/modern-demo.json').read_text())
        ir = normalize(source, asset_map=source['_assetMap'])
        raw = json.dumps(ir)
        html, css, report = render_target(ir, PROFILE)
        self.assertEqual(raw, json.dumps(ir))
        self.assertIn('nodeMappings', report)
        self.assertEqual(len(report['nodeMappings']), 5)
        self.assertIn('sourceRef', report['nodeMappings'][0])
        self.assertEqual(report['assetRewrites'][0]['targetPath'], 'media/health.svg')

    def test_exact_source_origin_and_path_boundary(self):
        rules = validate_url_mappings(PROFILE['urlMappings'])
        history = []
        original = 'https://example.org/sites/demo/SitePages/doc.aspx?x=1#top'
        result = rewrite_url(original, '', rules, history, node_id='x')
        self.assertEqual(result, '/knowledge/doc.aspx?x=1#top')
        self.assertEqual(history[0]['nodeId'], 'x')
        self.assertEqual(rewrite_url('https://example.org.attacker.test/sites/demo/SitePages/doc.aspx', '', rules, history, node_id='x'), 'https://example.org.attacker.test/sites/demo/SitePages/doc.aspx')
        self.assertEqual(rewrite_url('https://example.org/sites/demolition/doc.aspx', '', rules, history, node_id='x'), 'https://example.org/sites/demolition/doc.aspx')

    def test_rich_html_rewrites_inline_anchor_and_remains_safe(self):
        history = []
        html = rewrite_rich_html('<p>Read <a href="/sites/demo/SitePages/info.aspx" onclick="x()">details</a><script>alert(1)</script></p>', 'https://example.org/sites/demo/', PROFILE['urlMappings'], history, node_id='intro')
        self.assertIn('href="/knowledge/info.aspx"', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('onclick', html)
        self.assertEqual(history[0]['nodeId'], 'intro')

    def test_bad_rules_rejected(self):
        for src, target in [('https://example.org/', 'javascript:alert(1)/'), ('https://example.org/', '//attacker/'), ('https://example.org', '/ok/'), ('https://example.org/', 'relative/')]:
            with self.subTest(src=src, target=target), self.assertRaises(ValueError):
                validate_profile({**PROFILE, 'urlMappings': [{'sourcePrefix': src, 'targetPrefix': target}]})


if __name__ == '__main__':
    unittest.main()
