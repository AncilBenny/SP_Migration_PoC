"""Offline page dependency accounting for a portable CIR -> HTML export.

This module NEVER fetches remote URLs. A destination URL rewrite is not proof
that a SharePoint page, document or image was migrated. References are taken
from the actual output HTML; local bytes are verified against the export.

Only <a href> and <img src> within the rendered body are inventoried in v0.1.
CSS url(), srcset, JS dependencies and SharePoint drive IDs are future work.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

from .richtext import safe_url

# Signed/preauthenticated SharePoint or Graph URLs must not enter manifests
# or be treated as stable target identifiers. Do not log these query values.
SENSITIVE_QUERY_KEYS = frozenset({
    'access_token', 'authkey', 'token', 'sig', 'signature', 'sas',
    'client_secret', 'authorization', 'accesskey', 'apikey', 'code',
})
MAX_DEPENDENCIES = 20_000


def _signed(value: str) -> bool:
    try:
        parts = urlsplit(value)
        keys = {key.lower() for key, _ in parse_qsl(parts.query, keep_blank_values=True)}
        return bool(keys & SENSITIVE_QUERY_KEYS) or '@microsoft.graph.downloadurl' in value.lower()
    except ValueError:
        return True


def _safe_display(value: str) -> str:
    """Prevent leaking preauthenticated query strings in exported JSON."""
    try:
        url = urlsplit(value)
        if _signed(value):
            return urlunsplit((url.scheme, url.netloc, url.path, '[REDACTED]', url.fragment))
        return value
    except ValueError:
        return '[INVALID_URL]'


def _local_path(value: str) -> str | None:
    """Portable relative path only, no root-relative, encoded traversal or query."""
    if not isinstance(value, str) or not value or '\\' in value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or value.startswith(('/', '//')):
            return None
        unescaped = unquote(parsed.path)
        if unescaped != value:
            return None  # no ambiguous encoded path segments in portable ZIP
        if '\\' in unescaped or '%' in unescaped:
            return None  # reject double encoding and ambiguous filenames
        parts = unescaped.split('/')
        if any(part in ('', '.', '..') for part in parts):
            return None
        pure = PurePosixPath(unescaped)
        if pure.is_absolute() or not pure.parts:
            return None
        return unescaped
    except (ValueError, UnicodeError):
        return None


class _References(HTMLParser):
    VOID = frozenset({'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.containers: list[tuple[int, str]] = []
        self.refs: list[dict] = []
        self.blocked = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in ('script', 'style', 'template', 'iframe'):
            self.blocked += 1
        if not self.blocked:
            if attributes.get('data-ir-id') is not None:
                self.containers.append((self.depth, attributes['data-ir-id']))
            if tag in ('img', 'a'):
                field = 'src' if tag == 'img' else 'href'
                if field in attributes:
                    self.refs.append({'kind': 'image' if tag == 'img' else 'link',
                                      'nodeId': self.containers[-1][1] if self.containers else None,
                                      'url': attributes[field] or ''})
                    if len(self.refs) > MAX_DEPENDENCIES:
                        raise ValueError('HTML_DEPENDENCIES_LIMIT: too many references')
        if tag not in self.VOID:
            self.depth += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag not in self.VOID:
            self.depth = max(0, self.depth - 1)
        if tag in ('script', 'style', 'template', 'iframe'):
            self.blocked = max(0, self.blocked - 1)
        while self.containers and self.depth <= self.containers[-1][0]:
            self.containers.pop()


def source_inventory(ir: dict) -> list[dict]:
    """Identify authored dependencies without changing source-independent CIR."""
    from .contracts import validate_ir
    validate_ir(ir)
    references: list[dict] = []
    def add(node_id: str, kind: str, url: str):
        if url:
            references.append({'nodeId': node_id, 'kind': kind, 'url': _safe_display(url), 'sensitive': _signed(url)})
    def walk(node: dict):
        props = node.get('props') or {}
        kind = node.get('kind')
        ident = node.get('id')
        if kind == 'hero':
            add(ident, 'image', str(props.get('imageUrl') or ''))
        elif kind == 'image':
            add(ident, 'image', str(props.get('src') or ''))
        elif kind == 'linkList':
            for link in props.get('items', []):
                add(ident, 'link', link['url'])
        elif kind == 'richText':
            parser = _References()
            parser.feed(props.get('safeHtml', ''))
            parser.close()
            for found in parser.refs:
                add(ident, found['kind'], found['url'])
        for child in node.get('children', []):
            walk(child)
    walk(ir['tree'])
    return references


def audit_export(ir: dict, html: str, files: dict[str, bytes], *, mode: str) -> dict:
    """Return evidence-aware dependency manifest based on actual exported bytes.

    Missing/unsafe/transient dependencies block supported export checks;
    remote or root-relative dependencies remain explicitly unverified.
    """
    from .contracts import validate_ir
    validate_ir(ir)
    parser = _References()
    parser.feed(html)
    parser.close()
    origin = urlsplit(ir['source']['url'])
    entries = []
    for seq, ref in enumerate(parser.refs, start=1):
        raw = ref['url']
        status, reason = '', ''
        digest = None
        size = None
        if _signed(raw):
            status, reason = 'blocked', 'Preauthenticated or credential-like URL; not a durable export reference'
        elif not raw or not safe_url(raw):
            status, reason = 'blocked', 'Unsafe or empty reference'
        elif raw.startswith('#'):
            status, reason = 'fragment', 'Fragment target not checked by dependency engine'
        else:
            parsed = urlsplit(raw)
            if parsed.scheme == 'mailto':
                status, reason = 'external-unverified', 'Email destination not checked'
            elif parsed.scheme in ('http', 'https'):
                status = 'remote-unverified'
                if parsed.netloc.lower() == origin.netloc.lower():
                    reason = 'Source-origin URL; asset/page not downloaded or verified'
                else:
                    reason = 'External URL; accessibility and rights unverified'
            elif raw.startswith('/'):
                status, reason = 'target-unverified', 'Root-relative destination path; target does not exist in standalone export'
            else:
                local = _local_path(raw)
                if local is None:
                    status, reason = 'blocked', 'Invalid or ambiguous bundled file path'
                elif local not in files:
                    status, reason = 'blocked', 'Referenced local file missing from export'
                else:
                    payload = files[local]
                    status, reason = 'bundled-verified', 'Exact bytes present in portable output'
                    digest, size = sha256(payload).hexdigest(), len(payload)
        entry = {'id': f'dep-{seq}', 'kind': ref['kind'], 'nodeId': ref['nodeId'],
                 'destination': _safe_display(raw), 'status': status, 'reason': reason}
        if digest:
            entry['sha256'] = digest
            entry['sizeBytes'] = size
        entries.append(entry)
    stats = dict(Counter(item['status'] for item in entries))
    source = source_inventory(ir)
    source_sensitive = sum(bool(entry['sensitive']) for entry in source)
    return {'version': '0.1', 'mode': mode, 'method': 'offline-HTML-and-export-bytes',
            'sourceReferenceCount': len(source), 'sourceSensitiveReferenceCount': source_sensitive, 'renderedReferenceCount': len(entries),
            'coverage': 'Anchor href and image src only; not CSS url, srcset, JS, or Graph driveItem binaries',
            'summary': stats, 'blocked': stats.get('blocked', 0) > 0 or source_sensitive > 0,
            'remoteOrTargetUnverified': stats.get('remote-unverified', 0) + stats.get('target-unverified', 0),
            'dependencies': entries,
            'limitations': ['No network fetch or SharePoint authentication',
                            'Graph @microsoft.graph.downloadUrl links are ephemeral and never accepted as durable assets',
                            'No entitlement, malware scan, expiry, content-type or license validation']}
