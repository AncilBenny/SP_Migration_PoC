"""Contract and hostile-input tests for the offline Graph asset adapter."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from poc.engine import normalize
from poc.graph_assets import (normalize_drive_items, resolve_graph_assets,
                              stage_graph_files, verify_graph_staging, load_graph_metadata)

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return json.loads((ROOT/'tests/fixtures/graph-drive-items-offline-demo.json').read_text())


def page():
    source = json.loads((ROOT/'poc/samples/modern-cdph-routes-demo.json').read_text())
    return normalize(source)


def profile():
    return json.loads((ROOT/'poc/profiles/cdph-root-routing-example.json').read_text())


class GraphAdapterTests(TestCase):
    def test_fixture_resolves_by_graph_ids_preserves_destination(self):
        plan = resolve_graph_assets(page(), fixture(), profile())
        self.assertEqual(plan['referencedFiles'], 4)
        self.assertEqual(plan['summary'], {'graph-identity-resolved': 3, 'unresolved-graph-metadata': 1})
        self.assertEqual(plan['uploadedToDestination'], False)
        pdf = next(x for x in plan['items'] if x['kind'] == 'document')
        self.assertEqual(pdf['graphItem']['graphContentPath'],
                         '/v1.0/drives/graph-documents-drive/items/graph-pdf-example-03/content')
        self.assertEqual(pdf['graphItem']['itemId'], 'graph-pdf-example-03')
        self.assertEqual(pdf['destinationUrl'], 'https://documents.internet.staging/records/report.pdf')
        png = next(x for x in plan['items'] if x['sourceUrl'].endswith('sample.png'))
        self.assertEqual(png['graphItem']['sharepointIds']['listItemId'], '42')
        self.assertNotIn('DO_NOT_EXPORT_ME', json.dumps(plan))
        self.assertNotIn('some-cdn.invalid', json.dumps(plan))

    def test_unmatched_graph_url_is_review_not_fuzzy_guess(self):
        catalog = fixture()
        catalog['value'][0]['webUrl'] = 'https://other.example.org/images/sample.png'
        plan = resolve_graph_assets(page(), catalog, profile())
        self.assertEqual(plan['summary']['unresolved-graph-metadata'], 2)
        self.assertEqual(plan['summary']['graph-identity-resolved'], 2)

    def test_ambiguous_duplicate_same_url_is_review(self):
        raw = fixture()
        alternate = json.loads(json.dumps(raw['value'][0]))
        alternate['id'] = 'different-id'
        raw['value'].append(alternate)
        plan = resolve_graph_assets(page(), raw, profile())
        self.assertIn('ambiguous-graph-match', plan['summary'])
        self.assertEqual(next(x['candidateCount'] for x in plan['items']
                         if x['status'] == 'ambiguous-graph-match'), 2)

    def test_folder_ignored_and_id_must_be_safe(self):
        self.assertEqual(len(normalize_drive_items(fixture())), 3)
        for invalid in ('../steal', 'folder/item', '', 'line\nbreak', '%2F'):
            raw = fixture()
            raw['value'][0]['id'] = invalid
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'GRAPH_INVALID_ITEM_ID'):
                normalize_drive_items(raw)

    def test_host_lookalikes_and_encoded_traversal_block(self):
        for hostile in ('http://www.cdph.ca.gov/images/sample.png',
                        'https://www.cdph.ca.gov/images/%2e%2e/sample.png',
                        'https://www.cdph.ca.gov/images/%2fadmin.png',
                        'https://www.cdph.ca.gov/images/sample.png?sig=SECRET'):
            raw = fixture()
            raw['value'][0]['webUrl'] = hostile
            with self.subTest(url=hostile), self.assertRaisesRegex(ValueError, 'GRAPH_CATALOG_WEB_URL'):
                normalize_drive_items(raw)

    def test_lookalike_domain_is_not_auto_matched(self):
        raw = fixture()
        raw['value'][0]['webUrl'] = 'https://www.cdph.ca.gov.evil.org/images/sample.png'
        result = resolve_graph_assets(page(), raw, profile())
        self.assertEqual(result['summary']['unresolved-graph-metadata'], 2)

    def test_identity_and_size_and_metadata_limits(self):
        raw = fixture()
        raw['value'][0]['size'] = -1
        with self.assertRaisesRegex(ValueError, 'GRAPH_CATALOG_SIZE'):
            normalize_drive_items(raw)
        raw['value'][0]['size'] = 11
        raw['value'][0]['file'] = None
        self.assertEqual(len(normalize_drive_items(raw)), 2)
        with self.assertRaisesRegex(ValueError, 'GRAPH_CATALOG_FORMAT'):
            normalize_drive_items({'items': []})
        with self.assertRaisesRegex(ValueError, 'GRAPH_CATALOG_FORMAT'):
            normalize_drive_items([{}] * 5001)

    def test_stage_bytes_dedupe_and_independent_verify(self):
        raw = fixture()
        raw['value'] = [x for x in raw['value'] if x.get('file')]
        raw['value'][0]['size'] = 11
        plan = resolve_graph_assets(page(), raw, profile())
        # Duplicate reference is a second page node requiring the same Graph ID.
        duplicate = dict(plan['items'][0])
        duplicate['id'] = 'file-duplicate'
        plan['items'].append(duplicate)
        png = b'\x89PNG\r\n\x1a\nabc'   # 11 bytes
        calls = []
        def fetch(drive_id, item_id):
            calls.append((drive_id, item_id))
            if item_id == 'graph-png-example-01':
                return png, 'image/png'
            if item_id == 'graph-jpg-example-02':
                return b'\xff\xd8\xffhello', 'image/jpeg'
            return b'%PDF-1.7\nexample', 'application/pdf'
        with TemporaryDirectory() as tmp:
            location = Path(tmp)
            result = stage_graph_files(plan, location, fetcher=fetch)
            self.assertEqual(result['summary'], {'staged-verified': 4, 'not-stageable': 1})
            self.assertEqual(len(calls), 3)
            self.assertEqual(result['uniqueStagedBinaries'], 3)
            self.assertEqual(verify_graph_staging(result, location)['verified'], 4)
            path = location / result['items'][0]['stagedPath']
            path.write_bytes(b'changed')
            check = verify_graph_staging(result, location)
            self.assertFalse(check['passed'])
            self.assertEqual(check['failed'], 2)

    def test_stage_detects_binary_mismatch_and_missing_fetcher(self):
        plan = resolve_graph_assets(page(), fixture(), profile())
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'GRAPH_FETCHER_REQUIRED'):
                stage_graph_files(plan, Path(tmp), fetcher=None)
            result = stage_graph_files(plan, Path(tmp), fetcher=lambda d,i: (b'WRONG', 'image/png'))
            self.assertEqual(result['summary'], {'stage-failed': 3, 'not-stageable': 1})
            self.assertFalse((Path(tmp)/'graph-staged').exists())
            self.assertNotIn('WRONG', json.dumps(result))

    def test_cannot_stage_unknown_extension_as_executable(self):
        plan = resolve_graph_assets(page(), fixture(), profile())
        plan['items'][0]['graphItem']['name'] = 'run.js'
        with TemporaryDirectory() as tmp:
            result = stage_graph_files(plan, Path(tmp), fetcher=lambda d,i: (b'script', 'text/plain'))
        self.assertTrue(any(i.get('errorCode') == 'GRAPH_ACTIVE_CONTENT_DENIED' for i in result['items']))

    def test_load_metadata_file_size_restriction(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'graph.json'
            path.write_text(json.dumps(fixture()), encoding='utf-8')
            self.assertEqual(len(normalize_drive_items(load_graph_metadata(path))), 3)
            path.write_bytes(b'a' * (5 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, 'GRAPH_CATALOG_TOO_LARGE'):
                load_graph_metadata(path)

class AdditionalSecurityTests(TestCase):
    def test_unicode_filename_and_percent_encoded_sharepoint_url(self):
        raw = fixture()
        raw['value'][0]['name'] = 'Café – révision.png'
        raw['value'][0]['webUrl'] = 'https://www.cdph.ca.gov/images/sample.png'
        self.assertEqual(normalize_drive_items(raw)[0]['name'], 'Café – révision.png')
        raw['value'][0]['name'] = '../evil.png'
        with self.assertRaisesRegex(ValueError, 'GRAPH_CATALOG_NAME'):
            normalize_drive_items(raw)

    def test_signed_original_not_resolved_even_if_metadata_url_matches(self):
        raw = json.loads((ROOT/'poc/samples/modern-cdph-routes-demo.json').read_text())
        webparts = raw['canvasLayout']['horizontalSections'][0]['columns'][0]['webparts']
        textpart = next(x for x in webparts if 'innerHtml' in x)
        textpart['innerHtml'] += '<a href="https://www.cdph.ca.gov/records/report.pdf?sig=HIGHLY-PRIVATE">secure</a>'
        import json as _json
        from copy import deepcopy
        original = normalize(raw)
        saved = _json.dumps(original, sort_keys=True)
        plan = resolve_graph_assets(original, fixture(), profile())
        self.assertEqual(saved, _json.dumps(original, sort_keys=True))
        self.assertIn('requires-source-review', plan['summary'])
        self.assertNotIn('HIGHLY-PRIVATE', _json.dumps(plan))

    def test_provider_error_cannot_leak_tokens(self):
        plan = resolve_graph_assets(page(), fixture(), profile())
        with TemporaryDirectory() as tmp:
            report = stage_graph_files(plan, Path(tmp), fetcher=lambda a,b: (_ for _ in ()).throw(ValueError('Bearer ABC123SECRET')))
        self.assertEqual(report['summary']['stage-failed'], 3)
        self.assertNotIn('ABC123SECRET', json.dumps(report))
        self.assertTrue(all(x['errorCode'] == 'GRAPH_STAGE_FAILED' for x in report['items'] if x['stageStatus']=='stage-failed'))

    def test_existing_stage_symlink_denied(self):
        plan = resolve_graph_assets(page(), fixture(), profile())
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'out').mkdir()
            (root/'outside').mkdir()
            (root/'out'/'graph-staged').symlink_to(root/'outside', target_is_directory=True)
            report = stage_graph_files(plan, root/'out', fetcher=lambda a,b: (b'%PDF-test','application/pdf'))
            self.assertGreater(report['summary']['stage-failed'], 0)
            self.assertFalse(list((root/'outside').iterdir()))
