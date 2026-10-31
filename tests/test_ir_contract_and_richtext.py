"""CIR 0.2.0 contract, rich text safety, semantic fidelity and boundary tests."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from poc.contracts import CIR_VERSION, validate_ir
from poc.engine import build, normalize, safe_url, sanitize_html
from poc.mapping import render_target, build_target
from poc.richtext import sanitize_with_audit
from poc.validation import ir_to_html
from studio.service import ProjectStore

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / 'poc/profiles/client-example.json').read_text())
SOURCE = json.loads((ROOT / 'poc/samples/modern-rich-layout-public-adapted.json').read_text())


def with_rich_text(raw):
    source = copy.deepcopy(SOURCE)
    source['canvasLayout']['horizontalSections'][0]['columns'][0]['webparts'][0]['innerHtml'] = raw
    return source


class RichTextAndContractTests(unittest.TestCase):
    def test_versioned_ir_on_each_modern_graph_sample(self):
        for path in sorted((ROOT / 'poc/samples').glob('*.json')):
            doc = json.loads(path.read_text())
            if 'ListItemAllFields' in doc:
                continue
            with self.subTest(path=path.name):
                ir = normalize(doc, asset_map=doc.get('_assetMap'))
                self.assertEqual(ir['schemaVersion'], CIR_VERSION)
                self.assertIs(validate_ir(ir), ir)

    def test_json_schema_draft_2020_12_matches_generated_documents(self):
        try:
            import jsonschema
        except ImportError:
            import os
            if os.environ.get('MIGRATION_REQUIRE_SCHEMA_VALIDATION') == '1':
                self.fail('jsonschema is required in CI: pip install -r requirements-dev.txt')
            self.skipTest('pip install jsonschema for authoritative Draft 2020-12 validation')
        schema = json.loads((ROOT / 'schema/page.ir.v0.2.schema.json').read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        for path in (ROOT / 'poc/samples').glob('modern-*.json'):
            with self.subTest(sample=path.name):
                doc = json.loads(path.read_text())
                self.assertEqual(list(validator.iter_errors(normalize(doc, asset_map=doc.get('_assetMap')))), [])

    def test_fails_closed_for_wrong_version_duplicate_and_bad_geometry(self):
        ir = normalize(SOURCE)
        cases = []
        old = copy.deepcopy(ir); old['schemaVersion'] = '0.1.0'; cases.append(old)
        dupe = copy.deepcopy(ir); dupe['tree']['children'][0]['id'] = dupe['tree']['id']; cases.append(dupe)
        badwidth = copy.deepcopy(ir); badwidth['tree']['children'][1]['children'][0]['children'][0]['layout']['widthFraction'] = float('nan'); cases.append(badwidth)
        badpath = copy.deepcopy(ir); badpath['assets'][0]['resolvedUrl'] = 'assets/../etc/passwd'; cases.append(badpath)
        badkind = copy.deepcopy(ir); badkind['tree']['kind'] = 'execScript'; cases.append(badkind)
        for case in cases:
            with self.subTest(case=case['tree']['kind'], version=case['schemaVersion']):
                with self.assertRaisesRegex(ValueError, 'CIR_CONTRACT_INVALID'):
                    validate_ir(case)
                with self.assertRaisesRegex(ValueError, 'CIR_CONTRACT_INVALID'):
                    render_target(case, PROFILE)

    def test_safe_urls_reject_unicode_controls_credentials_and_backslash(self):
        for url in ('java\tscript:alert(1)', '\u200bjavascript:alert(1)',
                    'https://u:p@example.org/x', 'https://example.org\\@evil.test/',
                    'https:///not-a-host', '//attacker.test/page', 'data:text/html,abc'):
            with self.subTest(url=url):
                self.assertEqual(safe_url(url, 'https://example.org/sites/'), '')
        self.assertEqual(safe_url('/test', 'https://example.org/path/'), 'https://example.org/test')

    def test_semantic_table_and_inline_image_survive_both_renderers(self):
        raw = ('<table><thead><tr><th scope="col" colspan="2">Period</th></tr></thead>'
               '<tbody><tr><td rowspan="2">2026</td><td>Q4</td></tr></tbody></table>'
               '<figure><img src="/assets/chart.png" alt="Growth &amp; results"><figcaption>Chart</figcaption></figure>')
        ir = normalize(with_rich_text(raw))
        rich = ir['tree']['children'][1]['children'][0]['children'][0]['children'][0]
        html = rich['props']['safeHtml']
        for fragment in ('scope="col"', 'colspan="2"', 'rowspan="2"', 'alt="Growth &amp; results"', '<figcaption>'):
            self.assertIn(fragment, html)
        self.assertIn('INLINE_IMAGE_ASSET_REVIEW', [d['code'] for d in ir['diagnostics']])
        from poc.engine import render_node
        structural = render_node(ir['tree'])
        target, _, _ = render_target(ir, PROFILE)
        self.assertIn('src="https://example.org/assets/chart.png"', structural)
        self.assertIn('src="https://example.org/assets/chart.png"', target)
        self.assertTrue(ir_to_html(ir, '<main>'+structural+'</main>', {})['passed'])
        self.assertTrue(ir_to_html(ir, target, PROFILE)['passed'])

    def test_audits_removal_of_events_scripts_and_unsafe_images(self):
        raw = ('<p onclick="alert(1)">Safe <strong>text</strong><script>steal()</script>'
               '<img src="data:image/svg+xml,<svg/>" onerror="evil()">'
               '<img src="/images/good.png" alt="Good">'
               '<a href="javascript:alert(1)">do not execute</a></p>')
        report = sanitize_with_audit(raw, 'https://example.org/page')
        self.assertNotIn('<script', report.html)
        self.assertNotIn('steal()', report.html)
        self.assertNotIn('javascript:', report.html)
        self.assertNotIn('onerror', report.html)
        self.assertIn('Safe <strong>text</strong>', report.html)
        self.assertIn('src="https://example.org/images/good.png"', report.html)
        self.assertEqual(report.kept_inline_images, 1)
        self.assertGreaterEqual(report.rejected_urls, 2)
        ir = normalize(with_rich_text(raw))
        self.assertIn('RICH_TEXT_CLEANUP_REVIEW', [d['code'] for d in ir['diagnostics']])

    def test_sanitize_is_idempotent_on_its_own_output(self):
        raw = '<p><a href="/internal">X &amp; Y</a><img src="/asset.png" alt="chart"><br/><br></p><table><tr><td rowspan="2">Cell</td></tr></table>'
        clean = sanitize_html(raw, 'https://example.org/a')
        self.assertEqual(sanitize_html(clean, 'https://example.org/a'), clean)

    def test_malformed_tags_and_blocked_subtree_do_not_emit_script(self):
        raw = '<p>Before</p><svg><a href="javascript:alert(1)">trap</a></svg><script/> <p>After</p>'
        clean = sanitize_html(raw)
        self.assertIn('Before', clean)
        self.assertIn('After', clean)
        self.assertNotIn('trap', clean)
        self.assertNotIn('<svg', clean)

    def test_target_rewrites_inline_image_and_validator_accepts_rewrite(self):
        source = with_rich_text('<p><img src="https://example.org/sites/demo/SiteAssets/graph.png" alt="Graph"></p>')
        source['webUrl'] = 'https://example.org/sites/demo/SitePages/start.aspx'
        ir = normalize(source)
        profile = copy.deepcopy(PROFILE)
        profile['urlMappings'] = [{'sourcePrefix':'https://example.org/sites/demo/SiteAssets/', 'targetPrefix':'/media/'}]
        target, css, mapping = render_target(ir, profile)
        self.assertIn('src="/media/graph.png"', target)
        self.assertTrue(ir_to_html(ir, target, profile)['passed'])
        self.assertGreater(len(mapping['urlRewrites']), 0)

    def test_cli_build_requires_valid_ir_boundary(self):
        with TemporaryDirectory() as t:
            output = Path(t)/'site'
            report=build(ROOT/'poc/samples/modern-rich-layout-public-adapted.json', output)
            self.assertEqual(json.loads((output/'page.ir.json').read_text())['schemaVersion'], CIR_VERSION)
            self.assertTrue(report['contentAccounting']['passed'])

    def test_studio_contract_preserved_on_analyze_and_render(self):
        project=ProjectStore()
        p=project.analyze(sample_id='modern-rich-layout')
        self.assertEqual(p['ir']['schemaVersion'], CIR_VERSION)
        mapped=project.render(p['projectId'], mode='client')
        self.assertIn('quality', mapped)

if __name__ == '__main__':
    unittest.main()
