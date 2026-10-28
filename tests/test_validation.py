"""Intentional mutations must fail accounting; review placeholders remain visible."""
import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy

from poc.engine import build, normalize
from poc.mapping import build_target
from poc.validation import ir_to_html, source_to_ir, validate_target_file

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'poc/samples/modern-internal-links.json'
PROFILE = ROOT / 'poc/profiles/client-example.json'


class QualityTests(unittest.TestCase):
    def build_pages(self, root):
        structural = root / 'structural'
        client = root / 'client'
        build(SOURCE, structural, ROOT / 'poc/assets')
        build_target(structural / 'page.ir.json', PROFILE, client, strict=True)
        return structural, client

    def test_both_outputs_keep_every_supported_item_and_unknown_is_review(self):
        with tempfile.TemporaryDirectory() as t:
            structural, client = self.build_pages(Path(t))
            ir = (structural / 'page.ir.json').read_bytes()
            self.assertEqual(ir, (client / 'page.ir.json').read_bytes())
            for d in [structural, client]:
                quality = json.loads((d / 'quality-report.json').read_text())
                self.assertTrue(quality['passed'])
                self.assertEqual(quality['sourceToIr']['summary'], {'preserved': 4, 'needs-review': 1})
                self.assertEqual(quality['irToHtml']['summary'], {'preserved': 4, 'needs-review': 1})
                self.assertEqual(quality['visualFidelity'].startswith('unverified'), d == structural)
            self.assertIn('href="/knowledge/service.aspx"', (client / 'index.html').read_text())
            self.assertIn('src="media/health.svg"', (client / 'index.html').read_text())
            self.assertTrue((client / 'media/health.svg').is_file())

    def test_deleting_link_is_detected_from_actual_output(self):
        with tempfile.TemporaryDirectory() as t:
            structural, client = self.build_pages(Path(t))
            page = client / 'index.html'
            original = page.read_text()
            self.assertIn('href="/knowledge/service.aspx"', original)
            page.write_text(original.replace('href="/knowledge/service.aspx"', 'href="/wrong"'))
            quality = validate_target_file(structural / 'page.ir.json', page, PROFILE)
            self.assertFalse(quality['passed'])
            self.assertIn('links', next(x['reason'] for x in quality['irToHtml']['items'] if x['nodeId'] == 'links-part'))
            self.assertTrue((client / 'quality-check.json').is_file())

    def test_deleting_text_and_heading_is_detected(self):
        with tempfile.TemporaryDirectory() as t:
            structural, client = self.build_pages(Path(t))
            page = client / 'index.html'
            page.write_text(page.read_text().replace('<h2>Find information you can use</h2>', '<p>Find information you can use</p>'))
            checked = validate_target_file(structural / 'page.ir.json', page, PROFILE)
            self.assertFalse(checked['passed'])
            self.assertIn('headings', next(x['reason'] for x in checked['irToHtml']['items'] if x['nodeId'] == 'intro-text'))

    def test_missing_asset_is_detected_even_with_correct_image_html(self):
        with tempfile.TemporaryDirectory() as t:
            structural, client = self.build_pages(Path(t))
            (client / 'media/health.svg').unlink()
            result = validate_target_file(structural / 'page.ir.json', client / 'index.html', PROFILE)
            self.assertFalse(result['passed'])
            self.assertIn('bundled asset', next(x['reason'] for x in result['irToHtml']['items'] if x['nodeId'] == 'intro-image'))

    def test_missing_node_marker_is_detected(self):
        with tempfile.TemporaryDirectory() as t:
            structural, client = self.build_pages(Path(t))
            page = client / 'index.html'
            page.write_text(page.read_text().replace('data-ir-id="intro-text"', 'data-ir-id="removed"'))
            result = validate_target_file(structural / 'page.ir.json', page, PROFILE)
            self.assertFalse(result['passed'])
            self.assertIn('No matching', next(x['reason'] for x in result['irToHtml']['items'] if x['nodeId'] == 'intro-text'))

    def test_source_to_ir_detects_deleted_control(self):
        source = json.loads(SOURCE.read_text())
        ir = normalize(source, asset_map=source['_assetMap'])
        bad = deepcopy(ir)
        column = bad['tree']['children'][1]['children'][0]['children'][0]
        column['children'].clear()
        evidence = source_to_ir(source, bad)
        self.assertFalse(evidence['passed'])
        self.assertTrue(any(x['status'] == 'lost' and x['nodeId'] == 'intro-text' for x in evidence['items']))

    def test_unsafe_source_href_not_falsely_declared_preserved(self):
        source = json.loads(SOURCE.read_text())
        first = source['canvasLayout']['horizontalSections'][0]['columns'][0]['webparts'][0]
        first['innerHtml'] += '<p><a href="javascript:alert(1)">Unsafe</a></p>'
        ir = normalize(source, asset_map=source['_assetMap'])
        result = source_to_ir(source, ir)
        row = next(x for x in result['items'] if x['nodeId'] == first['id'])
        self.assertEqual(row['status'], 'needs-review')
        self.assertIn('Unsafe hyperlink', row['reason'])

    def test_public_pnp_canvas_unknown_not_counted_as_migrated(self):
        path = ROOT / 'poc/samples/pnp-canvas-public.json'
        with tempfile.TemporaryDirectory() as t:
            build(path, Path(t))
            quality = json.loads((Path(t) / 'quality-report.json').read_text())
            self.assertGreater(quality['sourceToIr']['summary'].get('needs-review', 0), 0)
            self.assertGreater(quality['irToHtml']['summary'].get('needs-review', 0), 0)

if __name__ == '__main__':
    unittest.main()
