"""No network or credentials: protocol-level Graph and publication failure tests."""
import json
import os
from pathlib import Path
from hashlib import sha256
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from poc.graph_transport import GraphBinaryFetcher, GraphTransferError, HttpResult, _location, _resolve_public_ip
from poc.publication import LocalDirectoryStore, publish_staged_assets
from poc.graph_assets import resolve_graph_assets, stage_graph_files
from poc.engine import normalize

ROOT = Path(__file__).resolve().parents[1]
GRAPH_URL = 'https://graph.microsoft.com/v1.0/drives/drv/items/item/content'
CDN_URL = 'https://tenant.files.1drv.com/download?sig=SENSITIVE'


def fetcher_with(executor, sleeper=lambda x: None):
    return GraphBinaryFetcher(lambda: 'secret_GRAPH_TOKEN', redirect_hosts={'tenant.files.1drv.com'},
                              executor=executor, sleeper=sleeper)


class GraphTransportTests(TestCase):
    def test_graph_302_does_not_forward_bearer_to_cdn(self):
        calls = []
        def exchange(url, headers, limit, timeout):
            calls.append((url, dict(headers)))
            if len(calls) == 1:
                return HttpResult(302, {'location': CDN_URL}, b'')
            return HttpResult(200, {'content-type': 'image/png'}, b'\x89PNG\r\n\x1a\nabc')
        result = fetcher_with(exchange)('drv', 'item')
        self.assertEqual(result[1], 'image/png')
        self.assertEqual(calls[0][0], GRAPH_URL)
        self.assertEqual(calls[0][1], {'Authorization': 'Bearer secret_GRAPH_TOKEN'})
        self.assertEqual(calls[1][0], CDN_URL)
        self.assertEqual(calls[1][1], {})

    def test_graph_200_direct_content_supported(self):
        seen = []
        def exchange(url, headers, limit, timeout):
            seen.append(url)
            return HttpResult(200, {'content-type': 'application/pdf; charset=binary'}, b'%PDF-1.7')
        self.assertEqual(fetcher_with(exchange)('drv', 'item'), (b'%PDF-1.7', 'application/pdf'))
        self.assertEqual(len(seen), 1)

    def test_unauthorized_redirect_hosts_and_http_denied(self):
        blocked = ['http://tenant.files.1drv.com/x', 'https://attacker.test/x',
                   'https://tenant.files.1drv.com.evil.org/x',
                   'https://user:pw@tenant.files.1drv.com/x',
                   'https://tenant.files.1drv.com:8080/x',
                   'https://tenant.files.1drv.com/x#frag',
                   '//tenant.files.1drv.com/x',
                   'https://tenant.files.1drv.com/x\nInjected:xx']
        for target in blocked:
            with self.subTest(target=target), self.assertRaises(GraphTransferError):
                _location(target, {'tenant.files.1drv.com'})

    def test_invalid_graph_identity_rejected_before_network(self):
        calls = []
        fetcher = fetcher_with(lambda *args: calls.append(args))
        with self.assertRaisesRegex(ValueError, 'GRAPH_INVALID_ITEM_ID'):
            fetcher('drv', '../../item')
        self.assertEqual(calls, [])

    def test_graph_429_retry_after_fresh_token_then_ok(self):
        calls, waits, auth = [], [], []
        def exchange(url, headers, limit, timeout):
            calls.append(url)
            auth.append(headers.get('Authorization'))
            return (HttpResult(429, {'retry-after': '2'}, b'') if len(calls) == 1
                    else HttpResult(200, {'content-type': 'application/pdf'}, b'%PDF-1.4'))
        provider_calls = []
        def token():
            provider_calls.append(1)
            return 'new_TOKEN'
        f = GraphBinaryFetcher(token, redirect_hosts={'tenant.files.1drv.com'},
                               executor=exchange, sleeper=waits.append)
        self.assertEqual(f('drv', 'item')[0], b'%PDF-1.4')
        self.assertEqual(waits, [2])
        self.assertEqual(len(provider_calls), 2)
        self.assertEqual(auth, ['Bearer new_TOKEN'] * 2)

    def test_graph_retry_exhaustion_and_no_token_or_signed_url_leak(self):
        def exchange(url, headers, limit, timeout):
            raise RuntimeError('Bearer secret_GRAPH_TOKEN https://signed.url/?token=secret')
        with self.assertRaisesRegex(GraphTransferError, '^GRAPH_NETWORK_FAILED$') as ctx:
            fetcher_with(exchange)('drv', 'item')
        self.assertNotIn('secret', str(ctx.exception))
        def cdn_fail(url, headers, limit, timeout):
            if 'graph.microsoft.com' in url:
                return HttpResult(302, {'location': CDN_URL}, b'')
            raise RuntimeError('signed token leaked in exception')
        with self.assertRaisesRegex(GraphTransferError, '^GRAPH_NETWORK_FAILED$'):
            fetcher_with(cdn_fail)('drv', 'item')

    def test_unexpected_cdn_302_not_followed(self):
        calls = []
        def exchange(url, headers, limit, timeout):
            calls.append(url)
            return (HttpResult(302, {'location': CDN_URL}, b'') if len(calls) == 1
                    else HttpResult(302, {'location': 'https://attacker.test/secret'}, b''))
        with self.assertRaisesRegex(GraphTransferError, 'GRAPH_CONTENT_HTTP_ERROR'):
            fetcher_with(exchange)('drv', 'item')
        self.assertEqual(len(calls), 2)

    def test_non_public_dns_rejected(self):
        with patch('poc.graph_transport.socket.getaddrinfo', return_value=[
            (2, 1, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaisesRegex(GraphTransferError, 'GRAPH_DNS_NONPUBLIC_ADDRESS'):
                _resolve_public_ip('tenant.files.1drv.com')
        with patch('poc.graph_transport.socket.getaddrinfo', return_value=[
            (2, 1, 6, '', ('8.8.8.8', 443)), (2, 1, 6, '', ('10.2.2.2', 443))]):
            with self.assertRaisesRegex(GraphTransferError, 'GRAPH_DNS_NONPUBLIC_ADDRESS'):
                _resolve_public_ip('tenant.files.1drv.com')

    def test_binary_limits_content_type_and_auth_failure(self):
        with self.assertRaises(GraphTransferError):
            GraphBinaryFetcher(lambda: 'x', redirect_hosts=set())
        with self.assertRaisesRegex(GraphTransferError, 'GRAPH_AUTH_TOKEN_INVALID'):
            GraphBinaryFetcher(lambda: 'secret\nINJECT', redirect_hosts={'tenant.files.1drv.com'},
                               executor=lambda *args: None)('drv', 'item')
        f = GraphBinaryFetcher(lambda: 'safe', redirect_hosts={'tenant.files.1drv.com'},
                executor=lambda *args: HttpResult(200, {'content-type': 'image/png'}, b'a'*12),
                max_file_bytes=8)
        with self.assertRaisesRegex(GraphTransferError, 'GRAPH_HTTP_INVALID_RESPONSE'):
            f('drv', 'item')


class PublicationTests(TestCase):
    def test_publication_readback_happy_path_and_idempotence(self):
        data = b'\x89PNG\r\n\x1a\n123'
        with TemporaryDirectory() as t:
            root = Path(t); staged = root/'stage'; stage_dir = staged/'graph-staged'
            stage_dir.mkdir(parents=True)
            name = 'a'*24 + '.png'
            (stage_dir/name).write_bytes(data)
            digest = sha256(data).hexdigest()
            row = {'nodeId': 'pic1', 'kind': 'image', 'stageStatus': 'staged-verified',
                   'stagedPath': 'graph-staged/'+name, 'sizeBytes': len(data), 'sha256': digest}
            report = {'items': [row, {**row, 'nodeId': 'pic2'},
                                {'nodeId': 'unmapped', 'status': 'unresolved-graph-metadata'}]}
            store = LocalDirectoryStore(root/'published')
            receipt = publish_staged_assets(report, staged, store, output_report=root/'receipt.json')
            self.assertEqual(receipt['readBackVerified'], 2)
            self.assertEqual(receipt['summary']['not-stageable'], 1)
            self.assertFalse(receipt['hostedDestinationVerified'])
            key = receipt['items'][0]['storageKey']
            self.assertEqual(store.read(key), data)
            self.assertEqual(publish_staged_assets(report, staged, store)['readBackVerified'], 2)
            self.assertIn('published-verified', (root/'receipt.json').read_text())

    def test_tampered_source_blocks_publication(self):
        with TemporaryDirectory() as t:
            root = Path(t); staged = root/'stage'/'graph-staged'
            staged.mkdir(parents=True)
            (staged/('a'*24+'.pdf')).write_bytes(b'NOT THE EXPECTED FILE')
            report = {'items': [{'nodeId': 'doc', 'kind': 'document', 'stageStatus': 'staged-verified',
                      'stagedPath': 'graph-staged/'+'a'*24+'.pdf', 'sizeBytes': 7, 'sha256': 'b'*64}]}
            receipt = publish_staged_assets(report, root/'stage', LocalDirectoryStore(root/'publish'))
            self.assertEqual(receipt['summary'], {'publish-failed': 1})
            self.assertFalse(list((root/'publish').rglob('*.pdf')))

    def test_malicious_staging_path_blocked(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            for path in ('../../secret.pdf', 'graph-staged/../../secret.pdf', 'https://example.org/file.pdf'):
                report={'items': [{'kind': 'document', 'stageStatus': 'staged-verified',
                                   'stagedPath': path, 'sha256': 'c'*64, 'sizeBytes': 1}]}
                res = publish_staged_assets(report, root, LocalDirectoryStore(root/'publish'))
                self.assertEqual(res['summary'], {'publish-failed': 1})

    def test_corrupt_readback_fails_without_success(self):
        class CorruptStore:
            destination_type = 'mock-blob'
            def put_if_absent(self, key, data): pass
            def read(self, key): return b'wrong'
        with TemporaryDirectory() as t:
            root=Path(t); (root/'graph-staged').mkdir()
            data=b'%PDF-1.7'
            (root/'graph-staged'/('d'*24+'.pdf')).write_bytes(data)
            report={'items':[{'kind':'document','stageStatus':'staged-verified',
                    'stagedPath':'graph-staged/'+'d'*24+'.pdf',
                    'sha256':sha256(data).hexdigest(), 'sizeBytes':len(data)}]}
            res=publish_staged_assets(report, root, CorruptStore())
            self.assertEqual(res['items'][0]['status'], 'publish-failed')
            self.assertEqual(res['items'][0]['errorCode'], 'PUBLISH_READBACK_MISMATCH')

class IntegrationBoundaryTests(TestCase):
    def test_resolve_stage_publish_pipeline_never_claims_hosted_url(self):
        from poc.graph_assets import resolve_graph_assets, verify_graph_staging
        source = json.loads((ROOT/'poc/samples/modern-cdph-routes-demo.json').read_text())
        ir = normalize(source)
        catalog = json.loads((ROOT/'tests/fixtures/graph-drive-items-offline-demo.json').read_text())
        for item in catalog['value']:
            if item.get('file'):
                item.pop('size', None)
        profile = json.loads((ROOT/'poc/profiles/cdph-root-routing-example.json').read_text())
        plan = resolve_graph_assets(ir, catalog, profile)
        png = b'\x89PNG\r\n\x1a\nabc'
        jpeg = b'\xff\xd8\xffDATA'
        pdf = b'%PDF-1.7\nhello'
        def executor(url, headers, max_bytes, timeout):
            if 'graph-png-example-01' in url:
                return HttpResult(200, {'content-type':'image/png'}, png)
            if 'graph-jpg-example-02' in url:
                return HttpResult(200, {'content-type':'image/jpeg'}, jpeg)
            if 'graph-pdf-example-03' in url:
                return HttpResult(200, {'content-type':'application/pdf'}, pdf)
            raise RuntimeError('unexpected Graph identity')
        fetch = fetcher_with(executor)
        with TemporaryDirectory() as t:
            root = Path(t)
            stage = stage_graph_files(plan, root/'stage', fetcher=fetch)
            self.assertEqual(stage['summary']['staged-verified'], 3)
            self.assertEqual(stage['summary']['not-stageable'], 1)
            self.assertTrue(verify_graph_staging(stage, root/'stage')['passed'])
            local = LocalDirectoryStore(root/'destination')
            receipt = publish_staged_assets(stage, root/'stage', local)
            self.assertEqual(receipt['readBackVerified'], 3)
            self.assertFalse(receipt['allDependenciesPublished'])
            self.assertFalse(receipt['hostedDestinationVerified'])

    def test_missing_token_env_cli_refuses_without_staging(self):
        import subprocess
        import sys
        with TemporaryDirectory() as t:
            root=Path(t)
            result=subprocess.run([sys.executable, '-m', 'poc', 'graph-stage', '--plan', 'missing.json',
                   '--out', str(root/'output'), '--allow-download-host', 'tenant.files.1drv.com',
                   '--token-env', 'INTENTIONALLY_MISSING_GRAPH_TEST_TOKEN'],
                   cwd=ROOT, env={k:v for k,v in os.environ.items() if k!='INTENTIONALLY_MISSING_GRAPH_TEST_TOKEN'},
                   capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Graph access token environment variable is not set', result.stderr)
            self.assertFalse((root/'output').exists())

    def test_all_throttled_requests_fail_boundedly(self):
        seen=[]
        def exchange(url, headers, max_bytes, timeout):
            seen.append(url)
            return HttpResult(429, {'retry-after':'9999999999999999999'}, b'')
        f=fetcher_with(exchange)
        with self.assertRaises(GraphTransferError):
            f('drv','item')
        self.assertEqual(len(seen), 3)
