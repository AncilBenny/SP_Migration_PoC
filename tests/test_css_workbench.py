"""Static CSS compilation is conservative, scoped, and non-executable."""
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from poc.css_workbench import compile_reviewed_css
from poc.browser_audit import audit_browser_page
from studio.service import ProjectStore

ROOT = Path(__file__).resolve().parents[1]


class CssWorkbenchTests(unittest.TestCase):
    def test_semantic_css_rules_and_media_queries_are_scoped(self):
        text = 'h2 { color:#345;font-size:20px } @media (max-width: 700px){ p {line-height:1.5} }'
        css, report = compile_reviewed_css(text, '<div class="target-body"><h2>A</h2><p>B</p></div>')
        self.assertIn(':is(.rich-text,.target-body) h2', css)
        self.assertIn('@media (max-width: 700px)', css)
        self.assertIn('line-height: 1.5;', css)
        self.assertEqual(report['emittedRuleCount'], 2)
        self.assertTrue(report['candidateRules'][0]['lastTagObserved'])
        self.assertEqual(report['candidateColorTokens'], [{'color':'#345','references':1}])
        self.assertEqual(report['result'], 'review-required')

    def test_disallowed_selectors_imports_and_unsafe_properties_are_blocked(self):
        source = ('html,body{background-color:red}'
                  '@import url(https://external.invalid/file.css);'
                  '.ms-RTE h2{ color:blue }'
                  'h2{position:absolute;behavior:url(x);color:expression(alert(1));font-weight:700}'
                  '@font-face{src:url(https://external.invalid/f.woff)}'
                  '@supports(display:grid){p{color:red}}'
                  '@container(width>500px){a{color:blue}}'
                  'h2:hover{color:red}')
        css, report = compile_reviewed_css(source)
        self.assertIn('font-weight: 700;', css)
        for value in ('url(', 'expression(', 'position:', 'behavior:', 'https://', '.ms-RTE', ':hover'):
            self.assertNotIn(value, css)
        blocked = report['blockedFeatures']
        self.assertEqual(blocked['external-import-not-acquired'], 1)
        self.assertEqual(blocked['@font-face-requires-review'], 1)
        self.assertEqual(blocked['@supports-requires-review'], 1)
        self.assertEqual(blocked['@container-requires-review'], 1)
        self.assertEqual(blocked['selector-not-portable'], 3)
        self.assertTrue(all('selector' not in x or x['selector'] == 'h2' for x in report['candidateRules']))

    def test_unsupported_media_does_not_flatten_into_unconditional_style(self):
        css, r = compile_reviewed_css('@media (orientation:landscape) {p{color:red}} '
                                       '@media (max-width:100px){h2{color:red}}'
                                       '@media (min-width:900px){h2{color:blue}}')
        self.assertNotIn('color: red', css)
        self.assertIn('@media (min-width: 900px)', css)
        self.assertEqual(r['blockedFeatures']['conditional-media-unhandled'], 2)

    def test_limits_and_parse_errors_do_not_execute(self):
        with self.assertRaisesRegex(ValueError,'exceeds 200 KB'):
            compile_reviewed_css('p{color:red}'*25000)
        with self.assertRaisesRegex(ValueError,'exceeds 2 MB'):
            compile_reviewed_css('p{color:red}','a'*2_000_001)
        css, report = compile_reviewed_css('@import "x"; p{color:red!important} broken {color:red')
        self.assertNotIn('!important', css)
        self.assertGreater(sum(report['blockedFeatures'].values()), 0)

    def test_deterministic_candidate_css_and_sha(self):
        text='h2{color:#123456}p{line-height:1.5}'
        self.assertEqual(compile_reviewed_css(text), compile_reviewed_css(text))
        _, r = compile_reviewed_css(text)
        self.assertEqual(len(r['sourceSha256']), 64)

    def test_studio_review_keeps_ir_and_preview_unmodified(self):
        store=ProjectStore()
        project=store.analyze(sample_id='modern-demo')
        ident=project['projectId']
        store.render(ident, mode='client')
        old_ir=store.output_file(ident,'client','page.ir.json')
        old_html=store.output_file(ident,'client','index.html')
        review=store.review_stylesheet(ident,'client','h2 {color:red} script {behavior:url(x)}')
        self.assertFalse(review['applied'])
        self.assertEqual(review['report']['emittedRuleCount'],1)
        self.assertIn('h2',review['css'])
        self.assertEqual(old_ir,store.output_file(ident,'client','page.ir.json'))
        self.assertEqual(old_html,store.output_file(ident,'client','index.html'))
        with ZipFile(io.BytesIO(store.export(ident,'client'))) as archive:
            self.assertIn('reviewed-candidates.css',archive.namelist())
            self.assertIn('css-review.json',archive.namelist())
        with self.assertRaisesRegex(ValueError,'Generate a destination'):
            fresh=store.analyze(sample_id='modern-demo')
            store.review_stylesheet(fresh['projectId'],'client','p{color:red}')

    def test_browser_checks_static_generated_page_when_available(self):
        # The CLI is optional. Don't require Chromium/Playwright in ordinary CI.
        import importlib.util, shutil
        if not importlib.util.find_spec('playwright') or not any(shutil.which(s) for s in ('chromium','chromium-browser','google-chrome')):
            self.skipTest('Optional browser tooling not installed')
        with TemporaryDirectory() as temp:
            result = audit_browser_page(ROOT/'showcase/client-design/index.html', Path(temp))
            self.assertTrue(result['structuralPassed'])
            self.assertTrue(result['reviewRequired'])
            self.assertTrue((Path(temp)/'mobile.png').is_file())
            self.assertTrue((Path(temp)/'desktop.png').is_file())
            self.assertIn('viewports',json.loads((Path(temp)/'browser-audit.json').read_text()))


if __name__=='__main__':
    unittest.main()
