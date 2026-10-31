"""Regression coverage for explicit, source-independent behavior compilation."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile
from io import BytesIO

from poc.behavior_compiler import compile_behavior, validate_behavior_mappings, BEHAVIOR_JS
from poc.engine import normalize, build
from poc.mapping import build_target, render_target, validate_profile
from poc.validation import ir_to_html
from studio.service import ProjectStore

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / 'poc/samples/modern-interactions-synthetic.json'
PROFILE = json.loads((ROOT / 'poc/profiles/client-behavior-demo.json').read_text())


class BehaviorMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = json.loads(SAMPLE.read_text())
        cls.ir = normalize(source, asset_map=source['_assetMap'])

    def test_explicit_accordion_and_tabs_preserve_content_and_ir(self):
        original = json.dumps(self.ir, sort_keys=True)
        html, css, report = render_target(self.ir, PROFILE)
        self.assertEqual([c['interaction'] for c in report['behavior']['compiled']], ['accordion','tabs'])
        self.assertEqual([c['panels'] for c in report['behavior']['compiled']], [3, 3])
        self.assertEqual(report['behavior']['scriptAssets'], ['behavior.js'])
        self.assertFalse(report['behavior']['sourceRuntimeCopied'])
        self.assertIn('<details class="mig-accordion-item" open>', html)
        self.assertIn('role="tablist"', html)
        self.assertIn('behavior.js', html)
        self.assertIn('.mig-tabs-list[hidden]', css)
        self.assertEqual(json.dumps(self.ir, sort_keys=True), original)
        result = ir_to_html(self.ir, html, PROFILE)
        self.assertTrue(result['passed'], result)

    def test_no_behavior_by_default_no_scripts(self):
        no_behavior = {k:v for k,v in PROFILE.items() if k != 'behaviorMappings'}
        html, css, report = render_target(self.ir, no_behavior)
        self.assertNotIn('behavior.js', html)
        self.assertNotIn('mig-tabs-list', css)
        self.assertFalse(report['behavior']['compiled'])

    def test_accordion_emits_no_script_when_alone(self):
        p = copy.deepcopy(PROFILE)
        p['behaviorMappings'] = p['behaviorMappings'][:1]
        html, _, report = render_target(self.ir, p)
        self.assertNotIn('<script', html)
        self.assertEqual(report['behavior']['scriptAssets'], [])

    def test_invalid_mapping_contract_rejected(self):
        variants = [
            'hello', [None], [{'nodeId':'n','interaction':'eval'}],
            [{'nodeId':'n','interaction':'tabs', 'initialIndex':True}],
            [{'nodeId':'n','interaction':'tabs', 'headingLevel':4}],
            [{'nodeId':'n','interaction':'tabs','constructor':'alert(1)'}],
            [{'nodeId':'n','interaction':'tabs'}]*2,
            [{'nodeId':'bad id','interaction':'tabs'}],
        ]
        for variant in variants:
            with self.subTest(variant=variant),self.assertRaises(ValueError):
                validate_behavior_mappings(variant)

    def test_invalid_node_and_structure_fail_closed(self):
        for invalid in ['not-here', 'intro-image']:
            p = copy.deepcopy(PROFILE)
            p['behaviorMappings'] = [{'nodeId': invalid,'interaction':'tabs'}]
            with self.subTest(node=invalid), self.assertRaisesRegex(ValueError,'BEHAVIOR_INVALID_PLAN'):
                render_target(self.ir,p)
        p = copy.deepcopy(PROFILE)
        p['behaviorMappings'] = [{'nodeId':'intro-text','interaction':'tabs','headingLevel':3}]
        with self.assertRaisesRegex(ValueError,'BEHAVIOR_UNSUPPORTED_STRUCTURE'):
            render_target(self.ir,p)
        p['behaviorMappings'][0]['initialIndex']=10
        p['behaviorMappings'][0]['headingLevel']=2
        with self.assertRaisesRegex(ValueError,'BEHAVIOR_INVALID_PLAN'):
            render_target(self.ir,p)

    def test_unexpected_malformed_heading_markup_does_not_guess(self):
        for fragment in ['<p>Preface</p><h2>One</h2><p>A</p><h2>Two</h2><p>B</p>',
                         '<h2>One</h2><p>A</p><h2>Two</h2>',
                         '<h2>One</h2><div><h2>Two</h2><p>Nested</p></div>',
                         '<h2>One</h2><p>Broken</div><h2>Two</h2><p>Other</p>']:
            with self.subTest(fragment=fragment),self.assertRaisesRegex(ValueError, 'BEHAVIOR_UNSUPPORTED_STRUCTURE'):
                compile_behavior('x',fragment,{'interaction':'accordion','headingLevel':2})

    def test_bundle_and_strict_content_accounting(self):
        with TemporaryDirectory() as temp:
            t=Path(temp)
            build(SAMPLE,t/'source',ROOT/'poc/assets')
            profile=t/'profile.json';profile.write_text(json.dumps(PROFILE))
            report=build_target(t/'source/page.ir.json',profile,t/'target',strict=True)
            self.assertTrue((t/'target/behavior.js').is_file())
            self.assertIn('document.addEventListener', (t/'target/behavior.js').read_text())
            self.assertTrue((t/'target/quality-report.json').is_file())
            self.assertTrue(json.loads((t/'target/quality-report.json').read_text())['passed'])
            self.assertEqual((t/'source/page.ir.json').read_bytes(),(t/'target/page.ir.json').read_bytes())
            self.assertEqual(len(report['behavior']['compiled']),2)

    def test_studio_export_and_preview_are_not_executable_source_js(self):
        studio=ProjectStore()
        result=studio.analyze(sample_id='modern-interactions')
        output=studio.render(result['projectId'],mode='client',profile=PROFILE)
        self.assertIn('behavior.js',output['files'])
        self.assertEqual(len(output['quality']['behavior']['compiled']),2)
        with ZipFile(BytesIO(studio.export(result['projectId'],'client'))) as z:
            self.assertIn('behavior.js',z.namelist())
            self.assertIn('data-behavior="tabs"',z.read('index.html').decode())
            self.assertIn('review-required',z.read('quality-report.json').decode())

    def test_js_is_fixed_and_no_eval_or_remote_code(self):
        self.assertNotIn('eval(',BEHAVIOR_JS)
        self.assertNotIn('innerHTML',BEHAVIOR_JS)
        self.assertNotIn('fetch(',BEHAVIOR_JS)
        self.assertNotIn('http://',BEHAVIOR_JS)


if __name__ == '__main__':unittest.main()
