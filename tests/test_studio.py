"""Browser/API workflow regression for the local-only Migration Studio."""
import io
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from studio.quality import capabilities_snapshot, release_decision
from studio.server import StudioServer, StudioHandler, serve
from studio.service import ProjectStore


class StudioProductTests(unittest.TestCase):
    def test_all_three_public_samples_convert_and_export(self):
        store = ProjectStore()
        for sample in ['modern-demo', 'modern-internal-links', 'pnp-public-canvas']:
            with self.subTest(sample=sample):
                analysis = store.analyze(sample_id=sample)
                self.assertTrue(analysis['sourceCheck']['passed'])
                for mode in ['client', 'structural']:
                    result = store.render(analysis['projectId'], mode=mode)
                    self.assertTrue(result['quality']['passed'])
                    self.assertFalse(result['quality']['releaseDecision']['readyForProduction'])
                    self.assertEqual(result['quality']['releaseDecision']['status'], 'review-required')
                    with ZipFile(io.BytesIO(store.export(analysis['projectId'], mode))) as archive:
                        names = set(archive.namelist())
                        self.assertTrue({'index.html', 'style.css', 'page.ir.json', 'quality-report.json', 'manifest.json'} <= names)
                        self.assertEqual(json.loads(archive.read('page.ir.json')), analysis['ir'])
                        self.assertIn('releaseDecision', json.loads(archive.read('quality-report.json')))

    def test_malformed_upload_does_not_create_project(self):
        store = ProjectStore()
        with self.assertRaisesRegex(ValueError, 'expected|Expected'):
            store.analyze(source={'title': 'Incomplete'})
        value = {'title': 'bad'}
        for _ in range(60):
            value = {'child': value}
        with self.assertRaisesRegex(ValueError, 'complexity'):
            store.analyze(source=value)
        with self.assertRaisesRegex(ValueError, 'Unknown public sample'):
            store.analyze(sample_id='not-a-sample')

    def test_supported_checks_do_not_claim_production_approval(self):
        result = release_decision({'passed': True, 'items': []}, {'passed': True, 'items': []}, [])
        self.assertFalse(result['readyForProduction'])
        self.assertEqual(result['status'], 'review-required')
        result = release_decision({'passed': True, 'items': []}, {'passed': False, 'items': []}, [])
        self.assertEqual(result['status'], 'blocked')
        caps = capabilities_snapshot()
        self.assertFalse(caps['productionReady'])
        self.assertTrue(any(x['id'] == 'visual-fidelity' and x['maturity'] == 'not-verified' for x in caps['engineCapabilities']))


class StudioHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = StudioServer(('127.0.0.1', 0), StudioHandler)
        cls.address = 'http://127.0.0.1:' + str(cls.server.server_port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, path, data=None, headers=None):
        request = Request(self.address + path, data=json.dumps(data).encode('utf-8') if data is not None else None,
                          headers={'Content-Type':'application/json', **(headers or {})})
        try:
            with urlopen(request, timeout=4) as response:
                return response.status, response.read(), response.headers
        except HTTPError as e:
            return e.code, e.read(), e.headers

    def test_http_full_import_preview_export(self):
        code, raw, headers = self.request('/api/samples')
        self.assertEqual(code, 200)
        self.assertGreaterEqual(len(json.loads(raw)['samples']), 6)
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        code, raw, _ = self.request('/api/capabilities')
        self.assertEqual(code, 200)
        self.assertFalse(json.loads(raw)['productionReady'])
        code, raw, _ = self.request('/api/analyze', {'sampleId': 'modern-demo'})
        self.assertEqual(code, 200)
        project = json.loads(raw)['projectId']
        code, raw, _ = self.request('/api/render', {'projectId': project, 'mode':'client'})
        self.assertEqual(code, 200)
        payload = json.loads(raw)
        self.assertEqual(payload['quality']['releaseDecision']['status'], 'review-required')
        code, data, headers = self.request(payload['previewUrl'])
        self.assertEqual(code, 200)
        self.assertIn(b'<!doctype html>', data.lower())
        self.assertIn("default-src 'none'", headers['Content-Security-Policy'])
        code, data, headers = self.request(payload['exportUrl'])
        self.assertEqual(code, 200)
        self.assertEqual(headers['Content-Type'], 'application/zip')
        with ZipFile(io.BytesIO(data)) as archive:
            self.assertIn('quality-report.json', archive.namelist())
            self.assertIn('mapping-report.json', archive.namelist())

    def test_http_rejects_bad_source_and_invalid_paths(self):
        code, raw, _ = self.request('/api/analyze', {'source': {'title': 'bad'}})
        self.assertEqual(code, 400)
        code, raw, _ = self.request('/api/analyze', {'sampleId': 'unknown'})
        self.assertEqual(code, 400)
        code, raw, _ = self.request('/api/preview/nonexistent/client/../secrets')
        self.assertEqual(code, 404)
        code, raw, _ = self.request('/api/export/invalid/client')
        self.assertEqual(code, 404)
        code, raw, _ = self.request('/static/../service.py')
        self.assertEqual(code, 404)

    def test_loopback_only(self):
        with self.assertRaises(ValueError):
            serve('0.0.0.0', 8080)
