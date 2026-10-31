"""Navigation/filtering preservation and fail-closed destination compilation tests."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from poc.behavior_compiler import BEHAVIOR_JS, compile_behavior, validate_behavior_mappings
from poc.engine import normalize
from poc.mapping import render_target, build_target
from poc.validation import ir_to_html
from studio.service import ProjectStore

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / 'poc/samples/modern-interactions-synthetic.json'
PROFILE = ROOT / 'poc/profiles/client-navigation-filter-demo.json'


class NavigationFilteringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = json.loads(SAMPLE.read_text(encoding='utf-8'))
        cls.ir = normalize(source, asset_map=source['_assetMap'])
        cls.profile = json.loads(PROFILE.read_text(encoding='utf-8'))

    def test_navigation_filter_and_tabs_from_unchanged_ir(self):
        before = json.dumps(self.ir, sort_keys=True)
        html, css, report = render_target(self.ir, self.profile)
        self.assertEqual(before, json.dumps(self.ir, sort_keys=True))
        self.assertEqual([x['interaction'] for x in report['behavior']['compiled']],
                         ['toc', 'tabs', 'filterLinks'])
        self.assertIn('<nav aria-label="On this page">', html)
        self.assertIn('href="#mig-section-', html)
        self.assertIn('data-behavior="filterLinks"', html)
        self.assertIn('data-filter-item', html)
        self.assertIn('role="status" aria-live="polite" hidden', html)
        self.assertIn('mig-filter-controls" hidden', html)
        self.assertIn('.mig-filter-status', css)
        self.assertEqual(report['behavior']['scriptAssets'], ['behavior.js'])
        self.assertTrue(ir_to_html(self.ir, html, self.profile)['passed'])

    def test_navigation_alone_emits_no_script(self):
        profile = deepcopy(self.profile)
        profile['behaviorMappings'] = [profile['behaviorMappings'][0]]
        html, _, report = render_target(self.ir, profile)
        self.assertNotIn('behavior.js', html)
        self.assertEqual(report['behavior']['scriptAssets'], [])
        self.assertEqual(report['behavior']['compiled'][0]['panels'], 3)

    def test_simple_links_filter_and_unfiltered_links_preserved(self):
        profile = deepcopy(self.profile)
        profile['components']['linkList'] = 'simpleLinks'
        profile['behaviorMappings'] = [profile['behaviorMappings'][-1]]
        html, _, report = render_target(self.ir, profile)
        self.assertIn('<li data-filter-item>', html)
        self.assertEqual(report['behavior']['compiled'][0]['interaction'], 'filterLinks')
        self.assertTrue(ir_to_html(self.ir, html, profile)['passed'])

    def test_wrong_source_kind_rejected(self):
        for node_id, interaction in [('intro-text', 'filterLinks'), ('links-part', 'toc'),
                                     ('links-part', 'tabs'), ('intro-image', 'filterLinks')]:
            profile = deepcopy(self.profile)
            profile['behaviorMappings'] = [{'nodeId': node_id, 'interaction': interaction}]
            with self.subTest(node_id=node_id, interaction=interaction):
                with self.assertRaisesRegex(ValueError, 'BEHAVIOR_INVALID_PLAN'):
                    render_target(self.ir, profile)

    def test_unsupported_structures_rejected(self):
        with self.assertRaisesRegex(ValueError, 'BEHAVIOR_UNSUPPORTED_STRUCTURE'):
            compile_behavior('foo',
                             '<p>Intro</p><h2>First</h2><p>Body</p><h2>Second</h2><p>Body</p>',
                             {'interaction': 'toc'})
        for entry in [
            {'nodeId': 'links-part', 'interaction': 'autoFromScript'},
            {'nodeId': 'links-part', 'interaction': 'filterLinks', 'initialIndex': 1},
            {'nodeId': 'intro-text', 'interaction': 'toc', 'initialIndex': 1}
        ]:
            with self.subTest(entry=entry), self.assertRaisesRegex(ValueError, 'BEHAVIOR_INVALID_PLAN'):
                validate_behavior_mappings([entry])

    def test_empty_link_list_cannot_create_filter(self):
        ir = deepcopy(self.ir)
        def clear(node):
            if node['id'] == 'links-part':
                node['props']['items'] = []
            for child in node.get('children', []):
                clear(child)
        clear(ir['tree'])
        profile = deepcopy(self.profile)
        profile['behaviorMappings'] = [profile['behaviorMappings'][-1]]
        with self.assertRaisesRegex(ValueError, 'BEHAVIOR_UNSUPPORTED_STRUCTURE'):
            render_target(ir, profile)

    def test_export_has_script_and_unchanged_ir(self):
        with TemporaryDirectory() as temp:
            original = Path(temp) / 'page.ir.json'
            original.write_text(json.dumps(self.ir, indent=2), encoding='utf-8')
            output = Path(temp) / 'target'
            result = build_target(original, PROFILE, output)
            self.assertEqual(result['behavior']['scriptAssets'], ['behavior.js'])
            self.assertEqual((output / 'page.ir.json').read_bytes(), original.read_bytes())
            self.assertEqual((output / 'behavior.js').read_text(), BEHAVIOR_JS)

    def test_studio_export_has_quality_and_filter(self):
        store = ProjectStore()
        project = store.analyze(sample_id='modern-interactions')
        result = store.render(project['projectId'], mode='client', profile=self.profile)
        self.assertEqual(len(result['mappingReport']['behavior']['compiled']), 3)
        with ZipFile(BytesIO(store.export(project['projectId'], 'client'))) as bundle:
            self.assertIn('behavior.js', bundle.namelist())
            self.assertIn('quality-report.json', bundle.namelist())
            self.assertIn('data-behavior="filterLinks"', bundle.read('index.html').decode())


if __name__ == '__main__':
    unittest.main()
