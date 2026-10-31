"""Dependency engine regression tests: exact bundles, remote review, hostile paths."""
import io
import json
import subprocess
import sys
import tempfile
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import unittest

from poc.dependencies import audit_export, source_inventory
from poc.engine import normalize, build
from poc.mapping import build_target
from studio.service import ProjectStore

ROOT = Path(__file__).resolve().parents[1]


def ir():
    raw = json.loads((ROOT / 'poc/samples/modern-demo.json').read_text())
    return normalize(raw, asset_map=raw['_assetMap'])


class DependencyTests(unittest.TestCase):
    def test_studio_exports_bundle_manifest_and_hash(self):
        studio = ProjectStore()
        page = studio.analyze(sample_id='modern-demo')
        for mode in ('client', 'structural'):
            with self.subTest(mode=mode):
                result = studio.render(page['projectId'], mode=mode)
                with ZipFile(io.BytesIO(studio.export(page['projectId'], mode))) as archive:
                    manifest = json.loads(archive.read('dependency-manifest.json'))
                    images = [d for d in manifest['dependencies'] if d['kind'] == 'image']
                    self.assertEqual(len(images), 1)
                    self.assertEqual(images[0]['status'], 'bundled-verified')
                    name = images[0]['destination']
                    self.assertEqual(images[0]['sha256'], sha256(archive.read(name)).hexdigest())
                    self.assertEqual(images[0]['sizeBytes'], len(archive.read(name)))
                    self.assertEqual(manifest['sourceReferenceCount'], 4)
                    self.assertFalse(manifest['blocked'])
                    self.assertEqual(result['quality']['dependencyAudit']['bundled-verified'], 1)
                    self.assertFalse(result['quality']['releaseDecision']['readyForProduction'])

    def test_remote_and_mapped_links_are_unverified_not_migrated(self):
        studio = ProjectStore()
        page = studio.analyze(sample_id='modern-internal-links')
        studio.render(page['projectId'], mode='client')
        with ZipFile(io.BytesIO(studio.export(page['projectId'], 'client'))) as archive:
            manifest = json.loads(archive.read('dependency-manifest.json'))
        self.assertTrue(any(d['status'] == 'target-unverified' and d['destination'].startswith('/knowledge/') for d in manifest['dependencies']))
        self.assertFalse(manifest['blocked'])

    def test_detects_missing_local_bytes(self):
        page = ir()
        html = '<div data-ir-id="intro-image"><img src="media/health.svg"></div>'
        report = audit_export(page, html, {}, mode='client')
        self.assertTrue(report['blocked'])
        self.assertEqual(report['summary'], {'blocked': 1})
        self.assertIn('missing', report['dependencies'][0]['reason'])

    def test_detects_bad_local_paths_and_rejects_unsafe_schemes(self):
        page = ir()
        for path in ('../secret.txt', 'media/%2e%2e/secret', 'media//f', 'media/..\\f', 'javascript:alert(1)', '//attacker.example/x'):
            with self.subTest(path=path):
                manifest = audit_export(page, f'<img src="{path}">', {}, mode='client')
                self.assertTrue(manifest['blocked'])

    def test_duplicate_references_stay_accounted_for(self):
        page = ir()
        payload = b'deterministic image bytes'
        html = '<img src="media/pic.png"><img src="media/pic.png">'
        result = audit_export(page, html, {'media/pic.png': payload}, mode='client')
        self.assertEqual(result['renderedReferenceCount'], 2)
        self.assertEqual(result['summary']['bundled-verified'], 2)
        self.assertEqual(result['dependencies'][0]['sha256'], result['dependencies'][1]['sha256'])

    def test_pre_authenticated_queries_redacted_and_blocked(self):
        page = ir()
        url = 'https://files.example.org/thumbnail.jpg?sig=SECRET-DO-NOT-LEAK&se=2026-10-29'
        result = audit_export(page, f'<img src="{url}">', {}, mode='client')
        self.assertTrue(result['blocked'])
        self.assertEqual(result['dependencies'][0]['status'], 'blocked')
        self.assertNotIn('SECRET-DO-NOT-LEAK', json.dumps(result))
        self.assertIn('REDACTED', json.dumps(result))

    def test_pre_authenticated_source_prevents_studio_export(self):
        studio = ProjectStore()
        raw = json.loads((ROOT / 'poc/samples/modern-demo.json').read_text())
        del raw['_assetMap']
        parts = raw['canvasLayout']['horizontalSections'][0]['columns'][0]['webparts']
        text_part = next(p for p in parts if 'innerHtml' in p)
        text_part['innerHtml'] += '<a href="https://x.example/doc?authkey=PRIVATE">private</a>'
        page = studio.analyze(source=raw)
        with self.assertRaisesRegex(ValueError, 'PREAUTHENTICATED_REFERENCE_BLOCKED'):
            studio.render(page['projectId'], mode='client')
        with self.assertRaises(KeyError):
            studio.export(page['projectId'], 'client')

    def test_output_manifest_from_cli_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(ROOT / 'poc/samples/modern-demo.json', root/'source', ROOT/'poc/assets')
            result = build_target(root/'source/page.ir.json', ROOT/'poc/profiles/client-example.json', root/'client')
            manifest = json.loads((root/'client/dependency-manifest.json').read_text())
            self.assertEqual(manifest['summary']['bundled-verified'], 1)
            self.assertEqual(result['dependencies']['manifest'], 'dependency-manifest.json')
            self.assertEqual(manifest['dependencies'][0]['kind'], 'image')

    def test_missing_asset_in_cli_target_blocks_strict_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(ROOT/'poc/samples/modern-demo.json', root/'source', ROOT/'poc/assets')
            (root/'source/assets/health.svg').unlink()
            with self.assertRaisesRegex(ValueError, 'content accounting failed'):
                build_target(root/'source/page.ir.json', ROOT/'poc/profiles/client-example.json', root/'client', strict=True)
            manifest = json.loads((root/'client/dependency-manifest.json').read_text())
            self.assertTrue(manifest['blocked'])
            self.assertEqual(manifest['summary']['blocked'], 1)


if __name__ == '__main__':
    unittest.main()
