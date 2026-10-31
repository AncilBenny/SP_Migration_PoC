"""Destination-root routing and explicit public-asset acquisition regression tests."""
import io
import json
import tempfile
import unittest
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import patch

from poc.acquisition import plan_acquisition, pull_public_files, _safe_host_and_ip
from poc.engine import normalize
from poc.mapping import render_target, validate_profile
from poc.rewrites import rewrite_url, rewrite_rich_html, validate_root_mappings
from poc.validation import ir_to_html
from studio.service import ProjectStore

ROOT = Path(__file__).resolve().parents[1]
CDPH = json.loads((ROOT/'poc/profiles/cdph-root-routing-example.json').read_text())


def source():
    data = json.loads((ROOT/'poc/samples/modern-internal-links.json').read_text())
    return data


def ir():
    data = source()
    return normalize(data, asset_map=data.get('_assetMap', {}))


class RootRouteTests(unittest.TestCase):
    def test_requested_cdph_example_and_nested_paths(self):
        rules = validate_root_mappings(CDPH['rootMappings'])
        audit = []
        for source_url, expected in [
            ('https://www.cdph.ca.gov/anything.aspx','https://internet.staging/anything'),
            ('https://www.cdph.ca.gov/nested/sub/Anything.ASPX?q=1#h','https://internet.staging/nested/sub/Anything?q=1#h'),
            ('https://www.cdph.ca.gov/SiteAssets/pic.png', 'https://images.internet.staging/SiteAssets/pic.png'),
            ('https://www.cdph.ca.gov/docs/file.pdf?download=1', 'https://documents.internet.staging/docs/file.pdf?download=1'),
        ]:
            self.assertEqual(rewrite_url(source_url, '', [], audit, node_id='x', root_mappings=rules), expected)
        self.assertEqual(len(audit), 4)
        self.assertEqual([r['kind'] for r in audit], ['page','page','image','document'])

    def test_relative_links_resolve_before_mapping_and_preserve_query_fragment(self):
        audit=[]
        got = rewrite_url('/guides/a.aspx?lang=en#three','https://www.cdph.ca.gov/SitePages/main.aspx',[],audit,node_id='node',root_mappings=CDPH['rootMappings'])
        self.assertEqual(got,'https://internet.staging/guides/a?lang=en#three')
        self.assertEqual(audit[0]['nodeId'],'node')

    def test_host_and_path_boundaries_prevent_lookalike_match(self):
        rules=[{'kind':'page','sourcePrefix':'https://www.cdph.ca.gov/sites/news/','targetPrefix':'https://internet.staging/','stripAspx':True}]
        for url in ['https://www.cdph.ca.gov.attacker.net/sites/news/item.aspx',
                    'https://www.cdph.ca.gov/sites/newspaper/item.aspx',
                    'http://www.cdph.ca.gov/sites/news/item.aspx']:
            self.assertEqual(rewrite_url(url, '', [], [], node_id='x',root_mappings=rules), url)

    def test_longest_typed_rule_wins_and_keeps_non_aspx(self):
        rules=deepcopy(CDPH['rootMappings'])
        rules.append({'kind':'page','sourcePrefix':'https://www.cdph.ca.gov/sections/',
                      'targetPrefix':'/kb/','stripAspx':True})
        self.assertEqual(rewrite_url('https://www.cdph.ca.gov/sections/nested/info.aspx','',[],[],node_id='x',root_mappings=rules),'/kb/nested/info')
        self.assertEqual(rewrite_url('https://www.cdph.ca.gov/test.html','',[],[],node_id='x',root_mappings=rules),'https://internet.staging/test.html')

    def test_invalid_roots_rejected_before_output(self):
        invalid=[
            {'kind':'document','sourcePrefix':'http://www.cdph.ca.gov/','targetPrefix':'https://docs.invalid/'},
            {'kind':'image','sourcePrefix':'https://www.cdph.ca.gov/','targetPrefix':'//evil.net/'},
            {'kind':'page','sourcePrefix':'https://www.cdph.ca.gov/','targetPrefix':'javascript:attack/'},
            {'kind':'image','sourcePrefix':'https://www.cdph.ca.gov/','targetPrefix':'/x/','stripAspx':True},
            {'kind':'page','sourcePrefix':'https://www.cdph.ca.gov/','targetPrefix':'/../evil/'},
            {'kind':'page','sourcePrefix':'https://www.cdph.ca.gov/','targetPrefix':'/ok/','stripAspx':'true'},
            {'kind':'other','sourcePrefix':'https://www.cdph.ca.gov/','targetPrefix':'/ok/'},
        ]
        for bad in invalid:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_profile({**CDPH,'rootMappings':[bad]})

    def test_rich_html_page_document_image_routes(self):
        data=('<p><a href="https://www.cdph.ca.gov/a.aspx">Page</a>'
              '<a href="https://www.cdph.ca.gov/docs/d.pdf">Doc</a>'
              '<img src="https://www.cdph.ca.gov/images/a.png" alt="A"></p>')
        history=[]
        out=rewrite_rich_html(data,'https://www.cdph.ca.gov/',[],history,node_id='rich',root_mappings=CDPH['rootMappings'])
        self.assertIn('href="https://internet.staging/a"',out)
        self.assertIn('href="https://documents.internet.staging/docs/d.pdf"',out)
        self.assertIn('src="https://images.internet.staging/images/a.png"',out)
        self.assertEqual(len(history),3)

    def test_real_renderer_and_independent_checker_agree(self):
        data=source()
        data['webUrl']='https://www.cdph.ca.gov/SitePages/Overview.aspx'
        data['title']='CDPH root routing sample (authored test data)'
        # Graph fixture URL is source-specific, normalizer uses page.webUrl as base
        node=ir()
        node['source']['url']='https://www.cdph.ca.gov/SitePages/Overview.aspx'
        rich=next(x for x in _walk(node['tree']) if x['kind']=='richText')
        rich['props']['safeHtml']='<p><a href="https://www.cdph.ca.gov/anything.aspx">One</a> <a href="https://www.cdph.ca.gov/docs/report.pdf">Two</a></p>'
        link_list=next(x for x in _walk(node['tree']) if x['kind']=='linkList')
        link_list['props']['items']=[{'url':'https://www.cdph.ca.gov/nested/page.aspx','label':'Nested'}]
        html, _, report=render_target(node,CDPH)
        self.assertIn('https://internet.staging/anything',html)
        self.assertIn('https://documents.internet.staging/docs/report.pdf',html)
        self.assertTrue(ir_to_html(node,html,CDPH)['passed'])
        self.assertEqual(len(report['urlRewrites']),3)


def _walk(node):
    yield node
    for child in node.get('children',[]):
        yield from _walk(child)


class PublicPullTests(unittest.TestCase):
    def test_plan_preserves_original_and_maps_asset_category(self):
        node=ir()
        rich=next(x for x in _walk(node['tree']) if x['kind']=='richText')
        rich['props']['safeHtml'] = '<p><a href="https://www.cdph.ca.gov/public/report.pdf">Report</a><img src="https://www.cdph.ca.gov/images/pic.png" alt="Image"></p>'
        p=plan_acquisition(node,CDPH)
        pdf=next(x for x in p['items'] if x['kind']=='document')
        png=next(x for x in p['items'] if x['sourceUrl'].endswith('pic.png'))
        self.assertEqual(pdf['destinationUrl'],'https://documents.internet.staging/public/report.pdf')
        self.assertEqual(png['destinationUrl'],'https://images.internet.staging/images/pic.png')
        self.assertEqual(pdf['status'],'pending-public-fetch')
        self.assertFalse(pdf['uploadedToDestination'])

    def test_public_pull_verifies_bytes_and_never_claims_upload(self):
        single={'items':[{'id':'f1','kind':'document','sourceUrl':'https://files.public.test/report.pdf',
                          'destinationUrl':'https://documents.internet.staging/report.pdf','status':'pending-public-fetch'}]}
        payload=b'%PDF-1.7 test bytes'
        with tempfile.TemporaryDirectory() as d:
            result=pull_public_files(single,Path(d),{'files.public.test'},fetcher=lambda url, allow:(payload,'application/pdf'))
            entry=result['items'][0]
            self.assertEqual(entry['status'],'downloaded-verified')
            self.assertEqual(entry['sha256'],sha256(payload).hexdigest())
            self.assertEqual((Path(d)/entry['downloadedPath']).read_bytes(),payload)
            self.assertFalse(result['uploadedToDestination'])
            self.assertEqual(result['unresolved'],0)

    def test_pull_denies_unapproved_hosts_and_signed_query(self):
        single={'items':[{'kind':'image','sourceUrl':'https://evil.test/a.jpg','status':'pending-public-fetch'},
                         {'kind':'image','sourceUrl':'https://files.public.test/a.jpg?sig=SECRET','status':'pending-public-fetch'}]}
        with tempfile.TemporaryDirectory() as d:
            result=pull_public_files(single,Path(d),{'files.public.test'},fetcher=lambda url,hosts:(b'IMG','image/jpeg'))
            self.assertEqual(result['downloaded'],0)
            self.assertEqual(result['unresolved'],2)

    def test_private_and_loopback_dns_addresses_rejected(self):
        with patch('poc.acquisition.socket.getaddrinfo',return_value=[(None,None,None,None,('127.0.0.1',443))]):
            with self.assertRaisesRegex(ValueError,'private, loopback'):
                _safe_host_and_ip('https://example.org/file.jpg',{'example.org'})
        with self.assertRaisesRegex(ValueError,'IP-literal'):
            _safe_host_and_ip('https://127.0.0.1/file.jpg',{'127.0.0.1'})

    def test_pull_rejects_oversized_and_html_payloads(self):
        single={'items':[{'kind':'image','sourceUrl':'https://example.org/img.png','status':'pending-public-fetch'}]}
        for payload,mime in [(b'<script>x</script>','text/html'),(b'x'*(10*1024*1024+1),'image/png')]:
            with tempfile.TemporaryDirectory() as d:
                result=pull_public_files(single,Path(d),{'example.org'},fetcher=lambda url,hosts:(payload,mime))
                self.assertEqual(result['unresolved'],1)

    def test_dependency_manifests_exported_in_mvp(self):
        store=ProjectStore()
        p=store.analyze(sample_id='modern-internal-links')
        info=store.render(p['projectId'],mode='client')
        with ZipFile(io.BytesIO(store.export(p['projectId'],'client'))) as z:
            plan=json.loads(z.read('acquisition-plan.json'))
            self.assertGreater(plan['count'],0)
            self.assertIn('dependency-manifest.json',z.namelist())
        self.assertFalse(info['quality']['releaseDecision']['readyForProduction'])


if __name__=='__main__':
    unittest.main()
