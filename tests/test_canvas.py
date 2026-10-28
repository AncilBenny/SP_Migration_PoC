import json
from pathlib import Path
import tempfile
import unittest
from html import escape

from poc.canvas import decode_modern_canvas
from poc.engine import build, normalize


def sample_canvas():
    control = {"controlType": 3, "id": "control-42", "webPartId": "vendor-doc-part",
               "position": {"sectionIndex": 1, "zoneIndex": 1, "sectionFactor": 12,
                            "controlIndex": 1}}
    data = {"id": "vendor-doc-part", "properties": {"previewState": "Show"},
            "serverProcessedContent": {"htmlStrings": {"html": "<p>Example content</p>"}}}
    html = '<div><div data-sp-canvascontrol="" data-sp-controldata="' + escape(json.dumps(control), quote=True) + '"><div data-sp-webpartdata="' + escape(json.dumps(data), quote=True) + '"></div></div><div data-sp-canvascontrol="" data-sp-controldata="' + escape(json.dumps({"controlType": 0, "pageSettingsSlice": {"isDefaultDescription": True}}), quote=True) + '"></div></div>'
    return {"ListItemAllFields": {"Title": "Source test", "Description": "", "ClientSideApplicationId": "modern", "CanvasContent1": html}, "webUrl": "https://example.org/SitePages/test.aspx"}


class CanvasTests(unittest.TestCase):
    def test_pnp_encoded_control_is_an_explicit_unknown(self):
        page, diags = decode_modern_canvas(sample_canvas())
        part = page['canvasLayout']['horizontalSections'][0]['columns'][0]['webparts'][0]
        self.assertEqual(part['id'], 'control-42')
        self.assertEqual(part['_capturePointer'], 'ListItemAllFields.CanvasContent1/control[0]')
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0]['code'], 'CANVAS_UNRECOGNIZED_PART')
        ir = normalize(page)
        unknown = ir['tree']['children'][1]['children'][0]['children'][0]['children'][0]
        self.assertEqual(unknown['kind'], 'unknown')
        self.assertIn('capturePointer', unknown['sourceRef'])

    def test_pnp_fixture_stays_a_public_fixture_not_live(self):
        fixture = Path(__file__).resolve().parents[1] / 'poc/samples/pnp-canvas-public.json'
        page, diags = decode_modern_canvas(json.loads(fixture.read_text()))
        self.assertGreaterEqual(len(diags), 1)
        self.assertEqual(page['_captureConfidence'], 'synthetic')
        self.assertTrue(page['canvasLayout']['horizontalSections'])
        with tempfile.TemporaryDirectory() as tmp:
            report = build(fixture, Path(tmp))
            self.assertGreaterEqual(report['unmappedParts'], 1)
            self.assertIn('CANVAS_UNRECOGNIZED_PART', [d['code'] for d in report['warnings']])

    def test_bad_attribute_json_does_not_get_executed(self):
        s = sample_canvas()
        s['ListItemAllFields']['CanvasContent1'] = '<div data-sp-controldata="alert(1)"></div>'
        with self.assertRaises(ValueError):
            decode_modern_canvas(s)

    def test_incomplete_modern_signature_refused(self):
        s = sample_canvas()
        s['ListItemAllFields'].pop('ClientSideApplicationId')
        with self.assertRaises(ValueError):
            decode_modern_canvas(s)

    def test_bad_span_rejected(self):
        s = sample_canvas()
        s['ListItemAllFields']['CanvasContent1'] = s['ListItemAllFields']['CanvasContent1'].replace('sectionFactor&quot;: 12', 'sectionFactor&quot;: 99')
        with self.assertRaises(ValueError):
            decode_modern_canvas(s)


if __name__ == '__main__':
    unittest.main()
