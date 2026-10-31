"""Evidence-based CIR component change ranking: no pixels are assigned causal blame."""
import copy
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from PIL import Image, ImageDraw
from poc.visual_compare import compare_screenshots, compare_screenshot_files
from studio.service import ProjectStore


def png(width=390, height=300, *, region=None):
    img=Image.new('RGB',(width,height),'white')
    if region:
        ImageDraw.Draw(img).rectangle(region, fill=(0,0,0))
    out=BytesIO();img.save(out,format='PNG')
    return out.getvalue()


GEOMETRY=[
 {'nodeId':'content-main','elementTag':'div', 'rect':{'x':10,'y':10,'width':180,'height':160},'styleProbe':{'fontSize':'16px','lineHeight':'24px','display':'block'}},
 {'nodeId':'right-card','elementTag':'article','rect':{'x':200,'y':10,'width':180,'height':160}},
]
MAPPINGS=[{'nodeId':'content-main','targetComponent':'contentBody'}, {'nodeId':'right-card','targetComponent':'resourceCards'}]


class ComponentVisualReviewTests(unittest.TestCase):
    def test_difference_assigned_to_overlapping_destination_component_only(self):
        baseline=png()
        modified=png(region=(20,20,50,50))
        report,_=compare_screenshots(baseline,modified,viewport_width=390,components=GEOMETRY,node_mappings=MAPPINGS)
        differences=report['componentDifferences']
        self.assertEqual(differences['reviewedNodeCount'],2)
        self.assertEqual(differences['affectedNodeCount'],1)
        row=differences['topAffectedNodes'][0]
        self.assertEqual(row['nodeId'],'content-main')
        self.assertEqual(row['targetComponent'],'contentBody')
        self.assertEqual(row['targetBounds']['x'],10)
        self.assertEqual(row['targetStyleProbe']['fontSize'],'16px')
        self.assertEqual(row['changedPixels'],31*31)
        self.assertEqual(differences['unattributedChangedPixels'],0)
        self.assertFalse(report['releaseApproved'])
        self.assertIn('does NOT establish root cause',differences['limitations'])

    def test_background_difference_is_unattributed_not_assigned_to_a_component(self):
        report,_=compare_screenshots(png(),png(region=(385,200,389,204)),viewport_width=390,components=GEOMETRY)
        self.assertEqual(report['componentDifferences']['affectedNodeCount'],0)
        self.assertEqual(report['componentDifferences']['unattributedChangedPixels'],25)

    def test_identical_baseline_has_no_false_affected_nodes(self):
        report,_=compare_screenshots(png(),png(),viewport_width=390,components=GEOMETRY)
        self.assertEqual(report['componentDifferences']['topAffectedNodes'],[])
        self.assertEqual(report['componentDifferences']['affectedNodeCount'],0)

    def test_page_height_mismatch_attributed_only_to_target_tail(self):
        tail=[{'nodeId':'footer','elementTag':'section','rect':{'x':0,'y':270,'width':390,'height':130}}]
        report,_=compare_screenshots(png(height=300),png(height=400),viewport_width=390,components=tail)
        rows=report['componentDifferences']['topAffectedNodes']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['unmatchedTargetPixels'],390*100)
        self.assertEqual(rows[0]['comparedPixels'],390*30)
        self.assertFalse(report['geometry']['sameDimensions'])

    def test_defensive_geometry_validation(self):
        bad=[
            [{'nodeId':'invalid id','elementTag':'div','rect':{'x':1,'y':2,'width':10,'height':10}}],
            GEOMETRY+GEOMETRY[:1],
            [{'nodeId':'x','elementTag':'script','rect':{'x':1,'y':2,'width':10,'height':10}}],
            [{'nodeId':'x','elementTag':'div','rect':{'x':1,'y':2,'width':True,'height':10}}],
            [{'nodeId':'x','elementTag':'div','rect':{'x':1,'y':2,'width':10,'height':10},'styleProbe':{'fontSize':'z'*81}}],
            [{'nodeId':'x','elementTag':'div','rect':{'x':1,'y':2,'width':0,'height':10}}],
        ]
        for geometry in bad:
            with self.subTest(geometry=geometry),self.assertRaisesRegex(ValueError,'VISUAL_COMPONENT_GEOMETRY_INVALID'):
                compare_screenshots(png(),png(),viewport_width=390,components=geometry)
        with self.assertRaisesRegex(ValueError,'VISUAL_COMPONENT_MAPPING_INVALID'):
            compare_screenshots(png(),png(),viewport_width=390,components=GEOMETRY,node_mappings=[{'nodeId':'x','targetComponent':'<script>'}])

    def test_cli_refuses_audit_from_a_different_target_screenshot(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=png();target=png(region=(20,20,50,50))
            (root/'source.png').write_bytes(source)
            (root/'target.png').write_bytes(target)
            (root/'browser-audit.json').write_text(json.dumps({'viewports':{'mobile':{'viewportWidth':390,'sha256':'bad','componentGeometry':GEOMETRY}}}))
            with self.assertRaisesRegex(ValueError,'VISUAL_COMPONENT_GEOMETRY_MISMATCH'):
                compare_screenshot_files(root/'source.png',root/'target.png',root/'out',viewport_width=390,browser_report=root/'browser-audit.json')

    def test_cli_validated_audit_and_mapping_report(self):
        import hashlib
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=png();target=png(region=(20,20,50,50))
            (root/'source.png').write_bytes(source)
            (root/'target.png').write_bytes(target)
            (root/'browser-audit.json').write_text(json.dumps({'viewports':{'mobile':{'viewportWidth':390,'sha256':hashlib.sha256(target).hexdigest(),'componentGeometry':GEOMETRY}}}))
            (root/'mapping-report.json').write_text(json.dumps({'nodeMappings':MAPPINGS}))
            report=compare_screenshot_files(root/'source.png',root/'target.png',root/'out',viewport_width=390,browser_report=root/'browser-audit.json',mapping_report=root/'mapping-report.json')
            self.assertEqual(report['componentDifferences']['topAffectedNodes'][0]['nodeId'],'content-main')
            self.assertEqual(json.loads((root/'out'/'visual-review.json').read_text())['componentDifferences']['affectedNodeCount'],1)

    def test_studio_injected_png_does_not_fabricate_component_geometry(self):
        store=ProjectStore();pid=store.analyze(sample_id='modern-demo')['projectId']
        store.render(pid,mode='client')
        result=store.review_visual(pid,'client',png(),390,target_screenshot=png(region=(20,20,50,50)))
        self.assertNotIn('componentDifferences',result['report'])
        self.assertEqual(result['report']['componentAttribution'],'unavailable-no-target-dom-geometry')

    def test_offline_chromium_capture_traces_target_nodes_and_keeps_images_private(self):
        try:
            import playwright.sync_api  # optional browser-audit dependency
        except ImportError:
            self.skipTest('Optional Playwright not installed')
        import shutil
        if not (shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')):
            self.skipTest('Local Chromium unavailable')
        from poc.browser_audit import audit_browser_page
        store=ProjectStore();pid=store.analyze(sample_id='modern-demo')['projectId']
        store.render(pid,mode='client')
        original_ir=store.output_file(pid,'client','page.ir.json')
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            with ZipFile(BytesIO(store.export(pid,'client'))) as z:z.extractall(root)
            audit=audit_browser_page(root/'index.html',root/'capture')
            mobile=audit['viewports']['mobile']
            self.assertGreaterEqual(len(mobile['componentGeometry']),3)
            self.assertTrue(all('nodeId' in c and 'rect' in c and 'styleProbe' in c for c in mobile['componentGeometry']))
            baseline=(root/'capture'/'mobile.png').read_bytes()
            result=store.review_visual(pid,'client',baseline,390)
            self.assertEqual(result['report']['componentDifferences']['affectedNodeCount'],0)
            self.assertGreaterEqual(result['report']['componentDifferences']['reviewedNodeCount'],3)
            self.assertEqual(result['report']['componentGeometrySource'],'matching-offline-chromium-capture')
            with ZipFile(BytesIO(store.export(pid,'client'))) as z:
                self.assertIn('visual-review.json',z.namelist())
                self.assertEqual(z.read('page.ir.json'),original_ir)
                self.assertNotIn('mobile.png',z.namelist())
                self.assertNotIn('difference-heatmap.png',z.namelist())
