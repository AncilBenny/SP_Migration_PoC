"""Regression suite: explicit SharePoint CSS selectors -> approved destination components."""
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import unittest
from zipfile import ZipFile

from poc.css_workbench import compile_reviewed_css, validate_selector_map
from studio.service import ProjectStore

ROOT = Path(__file__).resolve().parents[1]
MAPPING = json.loads((ROOT/'poc/profiles/modern-selector-component-map.json').read_text())
CSS = (ROOT/'poc/samples/modern-selector-component-demo.css').read_text()
HTML = ('<header class="target-header"><h1>Overview</h1></header>'
        '<div class="target-body"><h2>Guidance</h2><p>Overview</p></div>'
        '<article class="target-resource"><a href="/example">Document</a></article>')


class SelectorMappingTests(unittest.TestCase):
    def test_compiles_safe_scoped_component_candidates(self):
        css, report = compile_reviewed_css(CSS, HTML, selector_map=MAPPING)
        self.assertIn('.target-body h2 { color: #345678; font-weight: 700; }', css)
        self.assertIn('.target-body p { line-height: 1.5; margin-bottom: 1rem; }', css)
        self.assertIn('@media (max-width: 700px)', css)
        self.assertIn('.target-header h1 { font-size: 22px; }', css)
        self.assertIn('.target-resource a { color: #195d88; }', css)
        self.assertEqual(report['selectorMapping']['configured'], 4)
        self.assertEqual(report['selectorMapping']['matched'], 4)
        self.assertEqual(report['sourceCounts']['mappedRules'], 4)
        self.assertEqual(report['result'], 'review-required')
        for bad in ('ms-rtestate', 'ms-wpheader', 'url(', 'behavior:', 'https://'):
            self.assertNotIn(bad, css.lower())
        self.assertEqual(report['blockedFeatures']['external-import-not-acquired'], 1)

    def test_target_must_exist_when_html_supplied(self):
        css, report = compile_reviewed_css(CSS, '<div class="target-body"><p>Text</p></div>', selector_map=MAPPING)
        self.assertIn('.target-body p', css)
        for bad in ('.target-body h2', '.target-header', '.target-resource'):
            self.assertNotIn(bad, css)
        self.assertEqual(report['blockedFeatures']['target-component-not-present'], 3)

    def test_unmapped_sharepoint_selector_is_blocked(self):
        css, report = compile_reviewed_css('.ms-rtestate-field h2 {color:red}', HTML, selector_map=MAPPING)
        self.assertNotIn('color: red;', css)
        self.assertEqual(report['blockedFeatures']['selector-not-portable'], 1)
        self.assertEqual(len(report['selectorMapping']['unmatchedSourceSelectorHashes']), 4)

    def test_manifest_rejects_unknown_targets_and_injection(self):
        examples = [
            {'sourceSelector':'.ms-page h2', 'targetComponent':'body'},
            {'sourceSelector':'.ms-page h2', 'targetComponent':'.target-body,body'},
            {'sourceSelector':'.ms { color:red }', 'targetComponent':'content.heading2'},
            {'sourceSelector':'a:hover','targetComponent':'content.link'}
        ]
        for item in examples:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_selector_map({'version':'1.0','mappings':[item]})
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):
            validate_selector_map({'version':'1.0','mappings':[{'sourceSelector':'p','targetComponent':'content.paragraph'}]*2})
        with self.assertRaisesRegex(ValueError,'LIMIT'):
            validate_selector_map({'version':'1.0','mappings':[{'sourceSelector':f'.example{i}','targetComponent':'content.paragraph'} for i in range(65)]})
        with self.assertRaises(ValueError):
            validate_selector_map({'version':'1.0','mappings':[], 'arbitrary':True})

    def test_deterministic_no_input_mutation(self):
        before = json.dumps(MAPPING,sort_keys=True)
        self.assertEqual(compile_reviewed_css(CSS,HTML,selector_map=MAPPING),
                         compile_reviewed_css(CSS,HTML,selector_map=MAPPING))
        self.assertEqual(json.dumps(MAPPING,sort_keys=True),before)

    def test_studio_review_is_export_only(self):
        studio = ProjectStore()
        project = studio.analyze(sample_id='modern-demo')
        ident = project['projectId']
        studio.render(ident,mode='client')
        html_before=studio.output_file(ident,'client','index.html')
        ir_before=studio.output_file(ident,'client','page.ir.json')
        review=studio.review_stylesheet(ident,'client',CSS,selector_map=MAPPING)
        self.assertFalse(review['applied'])
        self.assertEqual(html_before, studio.output_file(ident,'client','index.html'))
        self.assertEqual(ir_before, studio.output_file(ident,'client','page.ir.json'))
        with ZipFile(io.BytesIO(studio.export(ident,'client'))) as z:
            self.assertIn('selector-mapping-review.json',z.namelist())
            self.assertIn('reviewed-candidates.css',z.namelist())
            self.assertNotIn(b'reviewed-candidates.css',z.read('index.html'))
        studio.review_stylesheet(ident,'client','h2 {font-weight:700}')
        with ZipFile(io.BytesIO(studio.export(ident,'client'))) as z:
            self.assertNotIn('selector-mapping-review.json',z.namelist())

    def test_cli_review_mode(self):
        with TemporaryDirectory() as tmp:
            command=[sys.executable, '-m','poc','css-workbench',
                     '--css','poc/samples/modern-selector-component-demo.css',
                     '--html','showcase/client-design/index.html',
                     '--selector-map','poc/profiles/modern-selector-component-map.json',
                     '--out',tmp]
            proc=subprocess.run(command,cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            report=json.loads((Path(tmp)/'css-review.json').read_text())
            self.assertEqual(report['selectorMapping']['configured'],4)


if __name__ == '__main__':
    unittest.main()
