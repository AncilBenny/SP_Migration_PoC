"""Visual comparison is an evidence aid, never proof of source parity."""
from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from poc.visual_compare import compare_screenshots, compare_screenshot_files
from studio.service import ProjectStore


def png(width=390, height=300, color='white', *, difference=False):
    from PIL import Image,ImageDraw
    im=Image.new('RGB',(width,height),color)
    if difference:
        ImageDraw.Draw(im).rectangle((10,10,90,60),fill='black')
    out=BytesIO();im.save(out,'PNG');return out.getvalue()


class VisualDiffTests(unittest.TestCase):
    def test_identical_images_are_not_automatically_approved(self):
        data=png()
        report,heatmap=compare_screenshots(data,data,viewport_width=390,include_heatmap=True)
        self.assertEqual(report['pixelDifferences']['changedOverlapPixels'],0)
        self.assertEqual(report['geometry']['unmatchedFraction'],0)
        self.assertEqual(report['pixelDifferences']['largestChangedTiles'],[])
        self.assertEqual(report['sourceImage']['sha256'],report['destinationImage']['sha256'])
        self.assertFalse(report['releaseApproved'])
        self.assertTrue(report['reviewRequired'])
        self.assertFalse(report['sourceBaselineVerified'])
        self.assertTrue(heatmap.startswith(b'\x89PNG'))

    def test_difference_has_hotspots_and_pixel_metrics(self):
        report,heatmap=compare_screenshots(png(),png(difference=True),viewport_width=390,include_heatmap=True)
        self.assertGreater(report['pixelDifferences']['changedOverlapPixels'],4000)
        self.assertGreater(report['pixelDifferences']['changedOverlapFraction'],0.01)
        self.assertTrue(report['pixelDifferences']['largestChangedTiles'])
        self.assertEqual(report['pixelDifferences']['changedBoundingBox'],[10,10,91,61])
        self.assertNotEqual(heatmap,png(difference=True))

    def test_height_mismatch_never_cropped_silently(self):
        report,_=compare_screenshots(png(height=300),png(height=500),viewport_width=390)
        self.assertFalse(report['geometry']['sameDimensions'])
        self.assertEqual(report['geometry']['unmatchedVerticalPixels'],200)
        self.assertAlmostEqual(report['geometry']['unmatchedFraction'],0.4)
        self.assertAlmostEqual(report['pixelDifferences']['combinedChangedOrUnmatchedFraction'],0.4)

    def test_dimension_and_content_guards(self):
        cases=[(b'NOTPNG',png(),390,'VISUAL_IMAGE_LIMIT'),
               (b'x'*80,png(),390,'VISUAL_IMAGE_FORMAT'),
               (png(),png(1440),390,'VISUAL_VIEWPORT_MISMATCH'),
               (png(),png(),500,'VISUAL_VIEWPORT_INVALID')]
        for a,b,w,error in cases:
            with self.subTest(error=error),self.assertRaisesRegex(ValueError,error):
                compare_screenshots(a,b,viewport_width=w)
        with self.assertRaisesRegex(ValueError,'VISUAL_THRESHOLD_INVALID'):
            compare_screenshots(png(),png(),viewport_width=390,threshold=-1)
        with self.assertRaisesRegex(ValueError,'VISUAL_IMAGE_INVALID'):
            compare_screenshots(b'\x89PNG\r\n\x1a\n'+b'x'*100,png(),viewport_width=390)

    def test_png_signature_not_enough_to_evade_pixel_limits(self):
        # Valid PNG with oversized image header, but tiny compressed payload.
        from PIL import Image
        import struct,zlib
        tiny=bytearray(png())
        self.assertEqual(tiny[12:16],b'IHDR')
        tiny[16:24]=struct.pack('>II',3000,16000)
        tiny[29:33]=struct.pack('>I',zlib.crc32(tiny[12:29]) & 0xffffffff)
        with self.assertRaisesRegex(ValueError,'VISUAL_IMAGE_LIMIT'):
            compare_screenshots(bytes(tiny),png(),viewport_width=390)

    def test_cli_report_and_heatmap_do_not_copy_source(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'source.png').write_bytes(png())
            (root/'target.png').write_bytes(png(difference=True))
            report=compare_screenshot_files(root/'source.png',root/'target.png',root/'out',viewport_width=390)
            self.assertIn('visual-review.json',[p.name for p in (root/'out').iterdir()])
            self.assertIn('difference-heatmap.png',[p.name for p in (root/'out').iterdir()])
            self.assertNotIn('source.png',[p.name for p in (root/'out').iterdir()])
            self.assertFalse(report['releaseApproved'])

    def test_studio_report_only_exported_and_ir_unchanged(self):
        store=ProjectStore();pr=store.analyze(sample_id='modern-demo');pid=pr['projectId']
        rendered=store.render(pid,mode='client')
        before=store.output_file(pid,'client','page.ir.json')
        result=store.review_visual(pid,'client',png(),390,target_screenshot=png(difference=True))
        self.assertTrue(result['heatmapDataUrl'].startswith('data:image/png;base64,'))
        self.assertTrue(base64.b64decode(result['heatmapDataUrl'].split(',')[1]).startswith(b'\x89PNG'))
        self.assertFalse(result['sourceScreenshotExported'])
        self.assertFalse(result['report']['releaseApproved'])
        self.assertEqual(store.output_file(pid,'client','page.ir.json'),before)
        with ZipFile(BytesIO(store.export(pid,'client'))) as z:
            files=z.namelist()
            self.assertIn('visual-review.json',files)
            self.assertNotIn('source.png',files)
            self.assertNotIn('difference-heatmap.png',files)
            self.assertEqual(json.loads(z.read('manifest.json'))['files'].count('visual-review.json'),1)
            self.assertEqual(z.read('page.ir.json'),before)

    def test_offline_browser_capture_can_be_compared_in_studio(self):
        try:
            import playwright.sync_api
        except ImportError:
            self.skipTest('Optional Playwright not installed')
        import shutil
        if not (shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')):
            self.skipTest('No installed Chromium binary')
        from poc.browser_audit import audit_browser_page
        store=ProjectStore();pr=store.analyze(sample_id='modern-demo');pid=pr['projectId']
        store.render(pid,mode='client')
        with TemporaryDirectory() as temp:
            root=Path(temp)
            with ZipFile(BytesIO(store.export(pid,'client'))) as z:
                z.extractall(root)
            rendered=audit_browser_page(root/'index.html',root/'capture')
            self.assertTrue(rendered['structuralPassed'])
            visual=store.review_visual(pid,'client',(root/'capture'/'mobile.png').read_bytes(),390)
            self.assertEqual(visual['report']['pixelDifferences']['changedOverlapPixels'],0)
            self.assertEqual(visual['report']['destinationCapture'],'offline-static-chromium-js-disabled-network-blocked')
            self.assertFalse(visual['report']['releaseApproved'])

    def test_studio_review_requires_existing_output(self):
        store=ProjectStore();project=store.analyze(sample_id='modern-demo')
        with self.assertRaisesRegex(ValueError,'Generate a destination'):
            store.review_visual(project['projectId'],'client',png(),390,target_screenshot=png())
        store.render(project['projectId'])
        with self.assertRaisesRegex(ValueError,'VISUAL_VIEWPORT_INVALID'):
            store.review_visual(project['projectId'],'client',png(),1024,target_screenshot=png())


if __name__ == '__main__': unittest.main()
