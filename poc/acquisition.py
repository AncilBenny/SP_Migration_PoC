"""Opt-in, unauthenticated PUBLIC file acquisition for explicit allowlisted hosts.

Modern SharePoint authenticated library downloads must use a future Graph
adapter; this module never handles bearer tokens, signed download URLs,
cookies, redirects, automatic remote fetching, or uploading to destination.
Each acquired binary has evidence (status, SHA-256 and byte count).
"""
from __future__ import annotations

from hashlib import sha256
import http.client
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
from urllib.parse import urlsplit

from .dependencies import _signed, _safe_display, source_inventory
from .rewrites import reference_kind, rewrite_url, validate_root_mappings, validate_url_mappings

MAX_FILES = 25
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024
ALLOWED_MIMES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/avif',
    'application/pdf', 'text/plain', 'text/csv', 'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.ms-excel', 'application/vnd.ms-powerpoint',
    'application/octet-stream',
}


def plan_acquisition(ir: dict, profile: dict | None = None) -> dict:
    """Produce an evidence-based file manifest without network access.

    References are tracked by node and original URL. Destination URL changes
    do not imply file transfer or successful hosting.
    """
    from .contracts import validate_ir
    validate_ir(ir)
    profile = profile or {}
    legacy, roots = profile.get('urlMappings', []), profile.get('rootMappings', [])
    validate_url_mappings(legacy)
    validate_root_mappings(roots)
    assets = {a.get('resolvedUrl'): a for a in ir.get('assets', [])}
    results = []
    seen = set()
    for ref in source_inventory(ir):
        original = ref['url']
        kind = 'image' if ref['kind'] == 'image' else reference_kind(original)
        if kind not in {'image', 'document'}:
            continue
        # A local mapped image may stand in for a real SharePoint source image.
        if kind == 'image' and original in assets:
            original = assets[original].get('originalUrl') or original
        already_bundled = kind == 'image' and ref['url'] in assets and assets[ref['url']].get('status') == 'resolved'
        if (ref['nodeId'], original) in seen:
            continue
        seen.add((ref['nodeId'], original))
        transient = bool(ref.get('sensitive')) or _signed(original)
        url = urlsplit(original)
        downloadable = not transient and url.scheme == 'https' and bool(url.hostname) and not url.username and not url.password
        target = rewrite_url(original, ir['source']['url'], legacy, [], node_id=ref['nodeId'], kind=kind, root_mappings=roots) if not transient else ''
        results.append({
            'id': f'file-{len(results)+1}', 'nodeId': ref['nodeId'], 'kind': kind,
            'sourceUrl': _safe_display(original), 'destinationUrl': _safe_display(target),
            'status': 'already-bundled' if already_bundled else 'pending-public-fetch' if downloadable else 'requires-source-resolution',
            'needsDownload': not already_bundled, 'uploadedToDestination': False,
        })
    return {'version': '0.1', 'mode': 'explicit-opt-in-public-only',
            'items': results, 'count': len(results),
            'limitations': ['No SharePoint authentication, Graph driveItem download, CDN upload or rights validation',
                            'Public HTTPS files only; explicit host allowlist required for retrieval',
                            'Successful fetch does not imply file is deployed at destinationUrl']}


def _safe_host_and_ip(source_url: str, allowed_hosts: set[str]) -> tuple[str, str, int, str]:
    url = urlsplit(source_url)
    if (_signed(source_url) or url.scheme != 'https' or not url.hostname or url.username or url.password
        or url.hostname.lower() not in allowed_hosts or url.port not in (None, 443)
        or '\\' in source_url or len(source_url) > 4096):
        raise ValueError('PUBLIC_FETCH_DENIED: URL is not permitted by the public HTTPS allowlist')
    hostname = url.hostname.lower()
    try:
        ipaddress.ip_address(hostname)
        raise ValueError('PUBLIC_FETCH_DENIED: IP-literal hosts are not allowed')
    except ValueError as e:
        if str(e).startswith('PUBLIC_FETCH_DENIED'):
            raise
    addresses = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    candidates = []
    for addr in addresses:
        ip = ipaddress.ip_address(addr[4][0])
        if not ip.is_global:
            raise ValueError('PUBLIC_FETCH_DENIED: private, loopback or reserved DNS address')
        candidates.append(str(ip))
    if not candidates:
        raise ValueError('PUBLIC_FETCH_DENIED: DNS returned no public addresses')
    path = url.path or '/'
    if url.query:
        path += '?' + url.query
    return hostname, candidates[0], 443, path


def _fetch_public_url(url: str, allowed_hosts: set[str]) -> tuple[bytes, str]:
    """TLS to prevalidated IP, cert checked against hostname; no proxies/redirects."""
    host, pinned_ip, port, path = _safe_host_and_ip(url, allowed_hosts)
    conn = http.client.HTTPSConnection(host, port, timeout=15, context=ssl.create_default_context())
    # Resolve once: pin the socket to the checked PUBLIC IP. HTTPSConnection's
    # TLS certificate verification and SNI still use the original hostname.
    conn._create_connection = lambda _address, timeout=None, source_address=None: socket.create_connection((pinned_ip, port), timeout=timeout)
    try:
        conn.request('GET', path, headers={'User-Agent': 'MigrationStudioPublicAssetPull/0.1',
                                          'Accept': '*/*', 'Accept-Encoding': 'identity', 'Connection': 'close'})
        response = conn.getresponse()
        if response.status != 200:  # redirects intentionally not followed
            raise ValueError(f'PUBLIC_FETCH_UNAVAILABLE: HTTP {response.status}')
        size_header = response.getheader('Content-Length')
        if size_header and size_header.isdecimal() and int(size_header) > MAX_FILE_BYTES:
            raise ValueError('PUBLIC_FETCH_TOO_LARGE')
        mime = (response.getheader('Content-Type') or '').split(';', 1)[0].strip().lower()
        if mime not in ALLOWED_MIMES:
            raise ValueError('PUBLIC_FETCH_UNSUPPORTED_MIME')
        payload = response.read(MAX_FILE_BYTES + 1)
        if len(payload) > MAX_FILE_BYTES:
            raise ValueError('PUBLIC_FETCH_TOO_LARGE')
        return payload, mime
    finally:
        conn.close()


def pull_public_files(plan: dict, out: Path, allowed_hosts: set[str], *, fetcher=None) -> dict:
    """Explicit opt-in operation. fetcher injection used by offline tests only."""
    if not allowed_hosts or len(allowed_hosts) > 20:
        raise ValueError('At least one explicit allowed source host is required')
    hosts = set()
    for hostname in allowed_hosts:
        if not isinstance(hostname, str) or not re.fullmatch(r'[a-zA-Z0-9.-]{1,253}', hostname) or hostname.startswith(('.', '-')):
            raise ValueError('Invalid allowlisted host')
        hosts.add(hostname.lower())
    items = plan.get('items', [])
    if len(items) > MAX_FILES:
        raise ValueError('Too many files for one public pull batch')
    fetcher = fetcher or _fetch_public_url
    out.mkdir(parents=True, exist_ok=True)
    records = []
    total = 0
    for item in items:
        kind, url = item.get('kind'), item.get('sourceUrl', '')
        record = dict(item)
        record['sourceUrl'] = _safe_display(url)
        if 'destinationUrl' in record:
            record['destinationUrl'] = _safe_display(str(record['destinationUrl']))
        if kind not in {'image', 'document'} or item.get('status') != 'pending-public-fetch':
            record['status'] = 'not-fetched'; records.append(record); continue
        try:
            if Path(urlsplit(url).path).suffix.lower() in {'.svg', '.html', '.htm', '.js', '.css', '.xml'}:
                raise ValueError('PUBLIC_FETCH_ACTIVE_CONTENT_DENIED')
            # Tests use fake fetch bytes, but URL security checks still run.
            hostname = urlsplit(url).hostname
            if not hostname or hostname.lower() not in hosts or _signed(url) or urlsplit(url).scheme != 'https':
                raise ValueError('PUBLIC_FETCH_DENIED')
            payload, mime = fetcher(url, hosts)
            if not isinstance(payload, bytes) or len(payload) > MAX_FILE_BYTES or mime not in ALLOWED_MIMES:
                raise ValueError('PUBLIC_FETCH_INVALID_PAYLOAD')
            total += len(payload)
            if total > MAX_TOTAL_BYTES:
                raise ValueError('PUBLIC_FETCH_TOTAL_LIMIT')
            extension = Path(urlsplit(url).path).suffix.lower()
            if not re.fullmatch(r'\.[a-z0-9]{1,8}', extension):
                extension = '.bin'
            file_path = f"downloads/{kind}s/{sha256(url.encode('utf-8')).hexdigest()[:20]}{extension}"
            target = out / file_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            record.update({'status': 'downloaded-verified', 'downloadedPath': file_path,
                           'sha256': sha256(payload).hexdigest(), 'sizeBytes': len(payload), 'contentType': mime})
        except (ValueError, OSError, ssl.SSLError, TimeoutError, socket.gaierror) as exc:
            # No secrets in error; retain evidence without claiming success.
            record.update({'status': 'pull-failed', 'errorCode': str(exc).split(':', 1)[0][:60]})
        records.append(record)
    result = {'version': '0.1', 'items': records,
              'downloaded': sum(x['status'] == 'downloaded-verified' for x in records),
              'unresolved': sum(x['status'] != 'downloaded-verified' for x in records),
              'uploadedToDestination': False}
    (out / 'acquisition-result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result
