"""Contract-level regression tests adapted from Microsoft's public Graph docs."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from poc.engine import normalize, build
from poc.mapping import render_target
from poc.validation import source_to_ir, ir_to_html
from studio.service import ProjectStore

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = json.loads((ROOT / 'poc/samples/modern-rich-layout-public-adapted.json').read_text())
PROFILE = json.loads((ROOT / 'poc/profiles/client-example.json').read_text())

class GraphUpgradeTests(unittest.TestCase):
    def test_title_image_and_visibility_options_survive_ir(self):
        ir = normalize(SAMPLE)
        hero = ir['tree']['children'][0]
        self.assertEqual(hero['kind'], 'hero')
        self.assertEqual(hero['props']['variant'], 'imageAndTitle')
        self.assertEqual(hero['props']['alignment'], 'center')
        self.assertTrue(hero['props']['gradientEnabled'])
        self.assertEqual(hero['props']['eyebrow'], '')
        self.assertEqual(hero['props']['sourceTextAboveTitle'], 'HIDDEN TOPIC')
        self.assertEqual(hero['props']['imageAlt'], 'Illustrative field guide cover')
        self.assertTrue(hero['props']['imageUrl'].startswith('https://example.org/'))
        self.assertEqual(ir['assets'][0]['originalUrl'], hero['props']['imageUrl'])

    def test_vertical_content_is_not_dropped_and_is_marked_approximate(self):
        ir = normalize(SAMPLE)
        sidebar = ir['tree']['children'][2]
        self.assertEqual(sidebar['props']['placement'], 'sidebar')
        children = sidebar['children'][0]['children'][0]['children']
        self.assertEqual([x['kind'] for x in children], ['richText','unknown'])
        self.assertEqual(children[1]['sourceRef']['path'], 'inline-of:sidebar-text')
        self.assertEqual([x['id'] for x in children], ['sidebar-text', 'inline-uncertain'])
        codes = [d['code'] for d in ir['diagnostics']]
        self.assertIn('VERTICAL_LAYOUT_APPROXIMATE', codes)
        self.assertIn('INLINE_WEBPART_PLACEMENT_UNVERIFIED', codes)
        summary = source_to_ir(SAMPLE, ir)
        self.assertTrue(summary['passed'])
        self.assertTrue(any(x['nodeId']=='sidebar-text' and x['status']=='preserved' for x in summary['items']))
        self.assertTrue(any(x['kind']=='layout' and x['status']=='needs-review' for x in summary['items']))

    def test_both_targets_render_hero_and_vertical_content(self):
        ir = normalize(SAMPLE)
        with TemporaryDirectory() as tmp:
            report = build(ROOT/'poc/samples/modern-rich-layout-public-adapted.json', Path(tmp)/'out')
            structural = (Path(tmp)/'out/index.html').read_text()
            self.assertEqual(report['webPartsFound'],4)
            self.assertIn('class="hero-image"', structural)
            self.assertIn('class="section vertical-section"', structural)
            self.assertIn('Contact the project office.', structural)
            self.assertTrue(ir_to_html(ir, structural, {})['passed'])
        html, css, mapping = render_target(ir,PROFILE)
        self.assertIn('target-hero-image', html)
        self.assertIn('target-sidebar', html)
        self.assertIn('Contact the project office.', html)
        self.assertEqual(mapping['mappedComponents']['richText:contentBody'],2)
        self.assertTrue(ir_to_html(ir, html, PROFILE)['passed'])

    def test_missing_expansion_reports_uncertainty(self):
        sample = copy.deepcopy(SAMPLE)
        del sample['canvasLayout']['horizontalSections'][0]['columns'][0]['webparts']
        ir = normalize(sample)
        self.assertIn('WEBPART_RELATIONSHIP_NOT_EXPANDED', [d['code'] for d in ir['diagnostics']])

    def test_missing_relationship_requires_review_in_source_audit(self):
        sample = copy.deepcopy(SAMPLE)
        del sample['canvasLayout']['horizontalSections'][0]['columns'][0]['webparts']
        check = source_to_ir(sample, normalize(sample))
        self.assertTrue(any(x['kind']=='sourceCompleteness' and x['status']=='needs-review' for x in check['items']))

    def test_sanitizer_self_closing_blocked_tag_does_not_hide_text(self):
        from poc.engine import sanitize_html
        self.assertEqual(sanitize_html('<script/><p>Keep me</p>'), '<p>Keep me</p>')

    def test_malformed_width_fails_closed(self):
        for width in (0, 13, '8', True, None):
            sample=copy.deepcopy(SAMPLE)
            sample['canvasLayout']['horizontalSections'][0]['columns'][0]['width']=width
            with self.subTest(width=width), self.assertRaises(ValueError):
                normalize(sample)

    def test_duplicate_ids_are_error_diagnostics(self):
        sample=copy.deepcopy(SAMPLE)
        sample['canvasLayout']['verticalSection']['webparts'][0]['id']='body-1'
        ir=normalize(sample)
        self.assertTrue(any(d['code']=='DUPLICATE_WEBPART_ID' and d['severity']=='error' for d in ir['diagnostics']))

    def test_studio_accepts_new_sample_and_returns_review_required(self):
        store=ProjectStore()
        project=store.analyze(sample_id='modern-rich-layout')
        self.assertEqual(project['inventory']['richText'],2)
        result=store.render(project['projectId'],mode='client')
        self.assertEqual(result['quality']['releaseDecision']['status'],'review-required')
        self.assertFalse(result['quality']['releaseDecision']['readyForProduction'])

if __name__=='__main__': unittest.main()
