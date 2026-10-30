"""Product CSS compilation and script-inventory regression coverage.

Public Graph contract shaped sample; never claim this is a tenant capture.
"""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile
from io import BytesIO

from poc.style_compiler import compile_declarations, compile_stylesheet, presentation_report, verified_rules
from poc.richtext import sanitize_with_audit
from poc.engine import normalize, build, render_node
from poc.mapping import render_target, build_target
from studio.service import ProjectStore

ROOT = Path(__file__).resolve().parents[1]
SOURCE = json.loads((ROOT/'poc/samples/modern-rich-layout-public-adapted.json').read_text())
PROFILE = json.loads((ROOT/'poc/profiles/client-example.json').read_text())
RAW = ('<h2 style="font-weight: bold;color:#346;line-height:1.4">Helpful resources</h2>'
       '<p style="color:#346;font-weight:bold;line-height:1.4">Repeated style</p>'
       '<p><span style="font-style:italic;font-size:18px">Safe emphasis</span></p>'
       '<a href="/services" style="color:#346">Visit services</a>'
       '<p style="position:fixed; background-image:url(https://bad.test/payload);color:red!important; text-align:center"'
       ' onclick="steal()">Review blocked declarations</p>'
       '<style>@import url(https://evil.test/c.css);body{background:red}</style>'
       '<script src="https://evil.test/track.js"></script><script>alert(1)</script>')


def sample():
    doc = copy.deepcopy(SOURCE)
    doc['canvasLayout']['horizontalSections'][0]['columns'][0]['webparts'][0]['innerHtml'] = RAW
    return doc


def rich(ir):
    return ir['tree']['children'][1]['children'][0]['children'][0]['children'][0]


class PresentationCompilerTests(unittest.TestCase):
    def test_compiles_deduplicated_css_classes(self):
        ir = normalize(sample())
        item = rich(ir)
        self.assertIn('mig-s-', item['props']['safeHtml'])
        self.assertEqual(len(item['props']['styleRules']), 4)
        rules, counts = verified_rules(ir)
        self.assertEqual(len(rules), 4)
        self.assertEqual(counts['nodeRuleReferences'], 4)
        css, summary = compile_stylesheet(ir, 'source-safe')
        self.assertEqual(css.count('.mig-s-'), 4)
        self.assertNotIn('@import', css)
        self.assertNotIn('url(', css)
        self.assertNotIn('position:', css)
        self.assertIn('font-weight:bold', css)
        self.assertIn('text-align:center', css)
        self.assertEqual(summary['emittedRules'], 4)

    def test_rejects_executable_css_and_unsafe_declarations(self):
        good, bad = compile_declarations('color: #ff00ff; font-size:18px; position:absolute;'
                                         'width:100vw; background:url(javascript:alert(1));'
                                         'behavior:url(x);color:expression(alert(1));'
                                         'font-weight:900!important; text-align:right')
        self.assertEqual(good, {'color':'#ff00ff','font-size':'18px','text-align':'right'})
        self.assertIn('position', bad)
        self.assertIn('background', bad)
        self.assertIn('color', bad)
        self.assertIn('font-weight', bad)

    def test_no_untrusted_source_scripts_or_css_tags_escape(self):
        ir = normalize(sample())
        html = rich(ir)['props']['safeHtml']
        for word in ('<script','onclick','steal()', '<style','evil.test','@import','expression('):
            self.assertNotIn(word, html)
        report = presentation_report(ir, compile_stylesheet(ir, 'source-safe')[1])
        self.assertEqual(report['sourceCodeInventory']['externalScripts'], 1)
        self.assertEqual(report['sourceCodeInventory']['inlineScripts'], 1)
        self.assertEqual(report['sourceCodeInventory']['embeddedStylesheets'], 1)
        self.assertEqual(report['sourceCodeInventory']['inlineEventHandlers'], 1)
        self.assertEqual(report['behavior']['status'], 'review-required')
        self.assertEqual(report['behavior']['executableSourceScriptsCopied'], 0)
        codes = {d['code'] for d in ir['diagnostics']}
        self.assertIn('SOURCE_CSS_DECLARATIONS_REVIEW', codes)
        self.assertIn('SOURCE_SCRIPTS_STYLES_REVIEW', codes)

    def test_client_policy_does_not_import_source_colors(self):
        ir = normalize(sample())
        html, css, report = render_target(ir, PROFILE)
        self.assertNotIn('source-styles.css', html)
        self.assertNotIn('class="mig-s-', html)
        self.assertNotIn('#346', css)
        self.assertEqual(report['presentation']['stylesheet']['emittedRules'], 0)
        self.assertEqual(report['presentation']['stylesheet']['intentionallyOmittedRules'], 4)
        target_profile = {**PROFILE, 'stylePolicy':'source-safe'}
        html2, _, report2 = render_target(ir, target_profile)
        self.assertIn('source-styles.css', html2)
        self.assertIn('class="mig-s-', html2)
        self.assertEqual(report2['presentation']['stylesheet']['emittedRules'], 4)

    def test_validate_rejects_forged_arbitrary_rules(self):
        ir = normalize(sample())
        cases = [
            {'className':'mig-s-000000000000','declarations':{'color':'#000'}},
            {'className':'mig-s-000000000000','declarations':{'background-image':'url(https://evil.test)'}},
            {'className':'mig-s-000000000000','declarations':{'color':'red;position:fixed'}},
            {'className':'mig-s-000000000000','declarations':{'--x':'abc'}},
        ]
        for case in cases:
            edited = copy.deepcopy(ir)
            rich(edited)['props']['styleRules'].append(case)
            with self.subTest(case=case):
                with self.assertRaisesRegex(ValueError, 'STYLE_CONTRACT_INVALID'):
                    render_target(edited, PROFILE)

    def test_studio_and_cli_exports_include_traceable_style_report(self):
        doc = sample()
        store = ProjectStore()
        project = store.analyze(source=doc)
        source_style = {**PROFILE, 'stylePolicy':'source-safe'}
        result = store.render(project['projectId'], mode='client', profile=source_style)
        self.assertEqual(result['quality']['presentation']['stylesheet']['emittedRules'], 4)
        with ZipFile(BytesIO(store.export(project['projectId'],'client'))) as z:
            self.assertIn('source-styles.css', z.namelist())
            self.assertIn('presentation-report.json', z.namelist())
            self.assertNotIn('steal()', z.read('source-styles.css').decode())
            self.assertIn('href="source-styles.css"', z.read('index.html').decode())
        result = store.render(project['projectId'], mode='client', profile=PROFILE)
        with ZipFile(BytesIO(store.export(project['projectId'],'client'))) as z:
            self.assertNotIn('source-styles.css', z.namelist())
            self.assertIn('presentation-report.json', z.namelist())
        with TemporaryDirectory() as t:
            src = Path(t)/'source.json'; src.write_text(json.dumps(doc))
            dest = Path(t)/'structural'; build(src,dest)
            self.assertTrue((dest/'source-styles.css').is_file())
            self.assertIn('source-styles.css', (dest/'index.html').read_text())
            profile = Path(t)/'profile.json'; profile.write_text(json.dumps(source_style))
            mapped = Path(t)/'target'; build_target(dest/'page.ir.json',profile,mapped)
            self.assertTrue((mapped/'source-styles.css').is_file())
            self.assertTrue((mapped/'presentation-report.json').is_file())

    def test_existing_safe_html_is_stable_and_keeps_only_compiler_class(self):
        r = sanitize_with_audit('<span class="mig-s-123456789abc" style="color:red" onclick="X()">Hi</span>')
        self.assertEqual(r.html, '<span class="mig-s-123456789abc">Hi</span>')
        parsed = sanitize_with_audit('<span class="mig-s-123456789abc" style="color:red">Hi</span>', compile_styles=True)
        self.assertNotIn('123456789abc', parsed.html)
        self.assertIn('mig-s-', parsed.html)
        self.assertEqual(len(parsed.style_rules), 1)


if __name__ == '__main__':
    unittest.main()

class ProductWorkflowRegressionTests(unittest.TestCase):
    def test_modified_ir_cannot_spoof_compiler_classes(self):
        ir = normalize(sample())
        rich(ir)['props']['safeHtml'] += '<span class="mig-s-000000000000">Spoof</span>'
        with self.assertRaisesRegex(ValueError, 'STYLE_CONTRACT_INVALID'):
            render_target(ir, PROFILE)

    def test_styled_demo_in_local_studio(self):
        store = ProjectStore()
        analyzed = store.analyze(sample_id='modern-style-compiler')
        self.assertTrue(analyzed['ir']['tree'])
        mapped = store.render(analyzed['projectId'], mode='client', profile={**PROFILE,'stylePolicy':'source-safe'})
        report = mapped['quality']['presentation']
        self.assertGreater(report['stylesheet']['emittedRules'], 1)
        self.assertEqual(report['behavior']['status'], 'review-required')
        self.assertIn('externalScripts', report['sourceCodeInventory'])

class CSSReadabilityTests(unittest.TestCase):
    def test_formats_only_compiler_owned_styles_preserving_order(self):
        import tinycss2
        from poc.style_compiler import format_generated_css
        source = '.x{color:#123;font-size:18px}@media(max-width:760px){.x{color:red}}'
        formatted = format_generated_css(source)
        self.assertIn('  color: #123;', formatted)
        self.assertIn('@media (max-width:760px) {', formatted)
        self.assertLess(formatted.index('color: #123'), formatted.index('color: red'))
        self.assertEqual([r.type for r in tinycss2.parse_stylesheet(source, skip_whitespace=True)],
                         [r.type for r in tinycss2.parse_stylesheet(formatted, skip_whitespace=True)])
        with self.assertRaises(ValueError):
            format_generated_css('@import "https://evil.test/";')

    def test_exported_css_is_editable_multiline(self):
        ir = normalize(sample())
        _, css, _ = render_target(ir, PROFILE)
        self.assertGreater(css.count('\n'), 35)
        self.assertIn('target-header {', css)
        self.assertIn('  padding: 54px 0;', css)

class ProfileIntegrationTest(unittest.TestCase):
    def test_bundled_source_safe_profile_is_valid_and_compiles(self):
        profile = json.loads((ROOT/'poc/profiles/client-example-source-safe.json').read_text())
        html, _, report = render_target(normalize(sample()), profile)
        self.assertIn('source-styles.css', html)
        self.assertEqual(report['presentation']['stylesheet']['stylePolicy'], 'source-safe')
