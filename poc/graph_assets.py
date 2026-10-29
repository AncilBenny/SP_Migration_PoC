"""Graph driveItem-aware dependency resolution and offline binary staging.

The catalog is a user-supplied Microsoft Graph v1.0 driveItem metadata response,
not an authenticated API client. Graph identities are stable acquisition keys;
webUrl is only a lookup hint. Temporary @microsoft.graph.downloadUrl capabilities
are intentionally NOT consumed, stored or emitted. No network requests here.

A future authorized Graph transport can call stage_graph_files with a vetted
fetcher(drive_id, item_id) callable; never pass tokens through this module.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import quote, unquote, urlsplit

from .acquisition import MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES, ALLOWED_MIMES, plan_acquisition
from .dependencies import _signed
from .rewrites import IMAGE_EXTS, DOCUMENT_EXTS

MAX_CATALOG_ITEMS = 5000
MAX_METADATA_LENGTH = 4096
MAX_SOURCE_BYTES = 5 * 1024 * 1024
ID_RE = re.compile(r'^[A-Za-z0-9_.!$()\-]{1,256}$')
SP_FIELDS = ('listId', 'listItemId', 'listItemUniqueId', 'siteId', 'webId')


def _identity(value: object, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value) or value in ('.', '..'):
        raise ValueError(f'GRAPH_INVALID_{label}: unsafe Graph resource identifier')
    return value


def _canonical_url(value: str) -> str:
    """Match URL paths without query/fragment, never decode path separators.

    SharePoint URLs are effectively case-insensitive. Encoded separators,
    dot segments, control chars and signed capability references are denied.
    """
    if not isinstance(value, str) or not value or len(value) > MAX_METADATA_LENGTH or '\\' in value or _signed(value):
        return ''
    try:
        parts = urlsplit(value)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
            return ''
        raw = parts.path
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            return ''
        if re.search(r'%(?:2f|5c|00|0a|0d|25)', raw, re.I):
            return ''
        decoded = unquote(raw)
        if ('\\' in decoded or any(part in ('.', '..') for part in decoded.split('/'))
            or '%' in decoded or '//' in decoded):
            return ''
        # IDNA/hostname checks are handled by urlsplit; reject nondefault port.
        return f'https://{parts.hostname.lower()}{decoded.casefold()}'
    except (ValueError, UnicodeError):
        return ''


def _metadata_field(value: object, max_length: int = 512) -> str | None:
    if isinstance(value, str) and len(value) <= max_length and not any(ord(c) < 32 for c in value):
        return value
    return None


def normalize_drive_items(raw: dict | list) -> list[dict]:
    """Read Graph driveItem list or {value:[...]} response; no Graph secrets.

    Only file-facet items with drive and item identifiers can be resolved.
    Metadata lacking identity is rejected rather than falling back to a URL.
    """
    entries = raw.get('value') if isinstance(raw, dict) else raw
    if not isinstance(entries, list) or len(entries) > MAX_CATALOG_ITEMS:
        raise ValueError('GRAPH_CATALOG_FORMAT: expected driveItem array (max 5000)')
    normalized = []
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            raise ValueError(f'GRAPH_CATALOG_ENTRY: entry {index} must be an object')
        if not isinstance(item.get('file'), dict):
            # A folder, package or list item without a file facet is not a binary.
            continue
        parent = item.get('parentReference')
        if not isinstance(parent, dict):
            raise ValueError(f'GRAPH_CATALOG_PARENT: file entry {index} has no parentReference')
        drive_id = _identity(parent.get('driveId'), 'DRIVE_ID')
        item_id = _identity(item.get('id'), 'ITEM_ID')
        original_url = item.get('webUrl')
        key = _canonical_url(original_url)
        if not key:
            raise ValueError(f'GRAPH_CATALOG_WEB_URL: file entry {index} has no safe HTTPS webUrl')
        name = _metadata_field(item.get('name'))
        if not name or name in ('.', '..') or '/' in name or '\\' in name or ':' in name or unicodedata.normalize('NFC', name) != name:
            raise ValueError(f'GRAPH_CATALOG_NAME: file entry {index} has an invalid name')
        size = item.get('size')
        if size is not None and (type(size) is not int or size < 0):
            raise ValueError(f'GRAPH_CATALOG_SIZE: file entry {index} has an invalid size')
        mime = _metadata_field(item['file'].get('mimeType'), 200)
        ids = item.get('sharepointIds') or {}
        if not isinstance(ids, dict):
            raise ValueError('GRAPH_CATALOG_SHAREPOINT_IDS: expected an object')
        stable_sp_ids = {k: v for k in SP_FIELDS if (v := _metadata_field(ids.get(k), 256))}
        normalized.append({
            'driveId': drive_id, 'itemId': item_id, 'webUrl': original_url.split('?', 1)[0].split('#', 1)[0],
            'urlKey': key, 'name': name, 'mimeType': mime, 'declaredSizeBytes': size,
            'eTag': _metadata_field(item.get('eTag')),
            'sharepointIds': stable_sp_ids,
            'graphContentPath': f'/v1.0/drives/{quote(drive_id, safe="")}/items/{quote(item_id, safe="")}/content',
        })
    return normalized


def resolve_graph_assets(ir: dict, graph_response: dict | list, profile: dict | None = None) -> dict:
    """Reconcile authored file refs with explicit Graph metadata by exact URL.

    Matching is intentionally NOT an inferred SharePoint lookup. A missing or
    ambiguous match is surfaced for review, never auto-mapped to a wrong file.
    """
    files = normalize_drive_items(graph_response)
    by_url: dict[str, list[dict]] = {}
    for item in files:
        by_url.setdefault(item['urlKey'], []).append(item)
    plan = plan_acquisition(ir, profile)
    resolved = []
    for dep in plan['items']:
        entry = {k: v for k, v in dep.items() if k != 'needsDownload'}
        url = dep['sourceUrl']
        key = _canonical_url(url)
        if '[REDACTED]' in url or dep.get('status') == 'requires-source-resolution' and _signed(url):
            entry.update(status='requires-source-review', reason='Transient or sensitive source reference cannot be used for Graph identity matching')
        elif dep['status'] == 'already-bundled':
            entry.update(status='already-bundled', verifiedInOriginalExport=False)
        elif not key:
            entry.update(status='requires-source-review', reason='Source URL cannot be safely matched to a Graph item')
        else:
            matches = by_url.get(key, [])
            unique = {(x['driveId'], x['itemId']): x for x in matches}
            if len(unique) == 1:
                item = next(iter(unique.values()))
                # Do not retain preauthenticated urls, only stable metadata.
                entry.update(status='graph-identity-resolved',
                             graphItem={k: v for k, v in item.items() if k not in {'urlKey', 'webUrl'}},
                             graphWebUrl=item['webUrl'],
                             reason='Source reference matched Graph driveItem webUrl; bytes not downloaded')
            elif len(unique) > 1:
                entry.update(status='ambiguous-graph-match', candidateCount=len(unique),
                             reason='Multiple distinct Graph IDs claim the same source URL')
            else:
                entry.update(status='unresolved-graph-metadata',
                             reason='No exact file URL match in supplied Graph metadata catalog')
        entry['uploadedToDestination'] = False
        resolved.append(entry)
    counts = dict(Counter(x['status'] for x in resolved))
    return {'version': '0.1', 'adapter': 'microsoft-graph-driveitem-offline',
            'catalogFileItems': len(files), 'referencedFiles': len(resolved),
            'summary': counts, 'items': resolved, 'downloaded': 0, 'uploadedToDestination': False,
            'sourceProvenance': 'user-supplied Graph driveItem metadata; not live API verification',
            'limitations': [
                'Exact webUrl matching only; no SharePoint tenant API calls, URL-to-item discovery or document version retrieval',
                'No network access, authentication, or destination publishing; metadata resolution is NOT binary migration',
                'Temporary @microsoft.graph.downloadUrl values never used or stored',
            ]}


def stage_graph_files(plan: dict, output: Path, *, fetcher) -> dict:
    """Stage vetted Graph binary bytes using an injected authenticated provider.

    fetcher(drive_id,item_id) -> (bytes,mime) is owned by the caller and MUST
    retrieve content from Microsoft Graph by ID, not a cached downloadUrl.
    Files are only marked staged once bytes are persisted and SHA-256 verified.
    This adapter never sees credentials or tries to follow redirect URLs.
    """
    if not callable(fetcher):
        raise ValueError('GRAPH_FETCHER_REQUIRED: an authorized Graph transport must be provided')
    entries = plan.get('items')
    if not isinstance(entries, list) or len(entries) > MAX_FILES:
        raise ValueError('GRAPH_STAGE_BATCH_LIMIT: max 25 dependencies per stage')
    if output.is_symlink():
        raise ValueError('GRAPH_STAGING_ROOT_SYMLINK_DENIED')
    output.mkdir(parents=True, exist_ok=True)
    records = []
    staged = {}  # one binary per stable driveId/itemId, even if referenced twice
    total = 0
    for entry in entries:
        result = {k: v for k, v in entry.items() if k != 'graphContentPath'}
        if entry.get('status') != 'graph-identity-resolved':
            result['stageStatus'] = 'not-stageable'
            records.append(result)
            continue
        item = entry['graphItem']
        drive_id = _identity(item.get('driveId'), 'DRIVE_ID')
        item_id = _identity(item.get('itemId'), 'ITEM_ID')
        key = (drive_id, item_id)
        try:
            if key in staged:
                result.update(staged[key])
            else:
                name = str(item.get('name') or '')
                extension = Path(name).suffix.lower()
                if extension in {'.svg', '.html', '.htm', '.js', '.css', '.xml', '.exe', '.bat', '.ps1'}:
                    raise ValueError('GRAPH_ACTIVE_CONTENT_DENIED')
                if extension not in IMAGE_EXTS | DOCUMENT_EXTS:
                    raise ValueError('GRAPH_UNSUPPORTED_FILE_EXTENSION')
                declared_size = item.get('declaredSizeBytes')
                if isinstance(declared_size, int) and declared_size > MAX_FILE_BYTES:
                    raise ValueError('GRAPH_DECLARED_FILE_TOO_LARGE')
                # Restrict the receiver to modest, independently testable binaries.
                payload, mime = fetcher(drive_id, item_id)
                if type(payload) is not bytes or not (0 < len(payload) <= MAX_FILE_BYTES):
                    raise ValueError('GRAPH_BINARY_INVALID_SIZE')
                if not isinstance(mime, str) or mime not in ALLOWED_MIMES:
                    raise ValueError('GRAPH_BINARY_UNSUPPORTED_MIME')
                if item.get('mimeType') not in (None, mime, 'application/octet-stream') and mime != 'application/octet-stream':
                    raise ValueError('GRAPH_BINARY_MIME_MISMATCH')
                if declared_size is not None and declared_size != len(payload):
                    raise ValueError('GRAPH_BINARY_SIZE_MISMATCH')
                if mime == 'application/pdf' and not payload.startswith(b'%PDF-'):
                    raise ValueError('GRAPH_BINARY_SIGNATURE_MISMATCH')
                if mime == 'image/png' and not payload.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('GRAPH_BINARY_SIGNATURE_MISMATCH')
                total += len(payload)
                if total > MAX_TOTAL_BYTES:
                    raise ValueError('GRAPH_STAGE_TOTAL_LIMIT')
                identifier = sha256(f'{drive_id}\0{item_id}'.encode()).hexdigest()[:24]
                rel = f'graph-staged/{identifier}{extension}'
                destination = output / rel
                # Never write through a caller-controlled symlink or outside root.
                stage_dir = destination.parent
                if stage_dir.is_symlink():
                    raise ValueError('GRAPH_STAGING_SYMLINK_DENIED')
                stage_dir.mkdir(parents=True, exist_ok=True)
                if destination.is_symlink() or not destination.resolve().is_relative_to(output.resolve()):
                    raise ValueError('GRAPH_STAGING_PATH_DENIED')
                destination.write_bytes(payload)
                digest = sha256(destination.read_bytes()).hexdigest()
                if digest != sha256(payload).hexdigest():
                    destination.unlink(missing_ok=True)
                    raise ValueError('GRAPH_STAGED_HASH_MISMATCH')
                receipt = {'stageStatus': 'staged-verified', 'stagedPath': rel,
                           'sizeBytes': len(payload), 'sha256': digest, 'contentType': mime}
                staged[key] = receipt
                result.update(receipt)
        except Exception as error:
            # Provider exceptions can contain bearer tokens / signed URLs.
            # Surface only our vetted diagnostic codes, never its raw message.
            code = str(error).split(':', 1)[0]
            if not re.fullmatch(r'GRAPH_[A-Z0-9_]{1,64}', code):
                code = 'GRAPH_STAGE_FAILED'
            result.update(stageStatus='stage-failed', errorCode=code)
        records.append(result)
    summary = dict(Counter(x['stageStatus'] for x in records))
    report = {'version': '0.1', 'adapter': 'microsoft-graph-driveitem-binary-stage',
              'items': records, 'summary': summary, 'uniqueStagedBinaries': len(staged),
              'uploadedToDestination': False,
              'limitations': ['Authorized Graph transport not provided by this offline PoC',
                              'Staging bytes locally does not prove a destination upload']}
    (output / 'graph-staging-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return report


def verify_graph_staging(report: dict, output: Path) -> dict:
    """Independent post-write verification; detects tampering or deleted files."""
    checked = []
    for item in report.get('items', []):
        if item.get('stageStatus') != 'staged-verified':
            continue
        rel = item.get('stagedPath', '')
        if not isinstance(rel, str) or not re.fullmatch(r'graph-staged/[0-9a-f]{24}\.[a-z0-9]{1,8}', rel):
            checked.append({'stageStatus': 'blocked', 'reason': 'Invalid staging path'})
            continue
        path = output / rel
        try:
            # Symlinks may not redirect verification outside the stage tree.
            if path.is_symlink() or not path.resolve().is_relative_to(output.resolve()):
                raise ValueError('Invalid staged file path')
            data = path.read_bytes()
            valid = len(data) == item['sizeBytes'] and sha256(data).hexdigest() == item['sha256']
        except (ValueError, OSError, KeyError):
            valid = False
        checked.append({'stagedPath': rel, 'verified': valid})
    good = sum(bool(i.get('verified')) for i in checked)
    return {'checked': len(checked), 'verified': good, 'failed': len(checked) - good,
            'passed': good == len(checked), 'details': checked,
            'uploadedToDestination': False}


def load_graph_metadata(path: Path) -> dict | list:
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError('GRAPH_CATALOG_TOO_LARGE')
    raw = json.loads(path.read_text(encoding='utf-8'))
    normalize_drive_items(raw)
    return raw
