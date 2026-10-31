"""Versioned, source-agnostic CIR boundary checks.

A light standard-library gate runs before rendering. The matching JSON Schema
is authoritative for complete structural validation (Draft 2020-12). Semantic
checks such as globally unique node IDs are enforced here as well.
"""
from __future__ import annotations

import math
from pathlib import PurePosixPath
from urllib.parse import urlsplit

CIR_VERSION = '0.2.0'
SUPPORTED_KINDS = frozenset({'page', 'section', 'columns', 'column', 'hero', 'richText', 'image', 'linkList', 'unknown'})
MAX_NODES = 10_000
MAX_DEPTH = 64


def _invalid(path: str, reason: str):
    raise ValueError(f'CIR_CONTRACT_INVALID at {path}: {reason}')


def validate_ir(ir: dict) -> dict:
    """Reject invalid version, shapes, geometry and references without mutation."""
    if not isinstance(ir, dict):
        _invalid('/', 'Expected CIR object')
    if ir.get('schemaVersion') != CIR_VERSION:
        _invalid('/schemaVersion', f'Expected {CIR_VERSION}; received {ir.get("schemaVersion")!r}. Use the explicit IR upgrade path')
    for key in ('source', 'page', 'tree', 'assets', 'diagnostics'):
        if key not in ir:
            _invalid('/' + key, 'Required field missing')
    src = ir['source']
    if not isinstance(src, dict) or not isinstance(src.get('platform'), str) or not isinstance(src.get('pageModel'), str):
        _invalid('/source', 'Expected source platform and page model')
    if not isinstance(src.get('url'), str) or not urlsplit(src['url']).scheme in {'http', 'https'}:
        _invalid('/source/url', 'Expected absolute web URL')
    page = ir['page']
    if not isinstance(page, dict) or not isinstance(page.get('id'), str) or not page['id'].strip() or not isinstance(page.get('title'), str):
        _invalid('/page', 'Expected page id and title')
    if not isinstance(ir['assets'], list) or not isinstance(ir['diagnostics'], list):
        _invalid('/assets|diagnostics', 'Expected arrays')
    seen = set()
    nodes = [(ir['tree'], '/tree', 0)]
    visits = 0
    while nodes:
        node, path, depth = nodes.pop()
        visits += 1
        if visits > MAX_NODES or depth > MAX_DEPTH:
            _invalid(path, 'CIR tree exceeds bounded complexity')
        if not isinstance(node, dict):
            _invalid(path, 'Expected node object')
        ident = node.get('id')
        kind = node.get('kind')
        if not isinstance(ident, str) or not ident.strip() or len(ident) > 256:
            _invalid(path + '/id', 'Expected nonempty node id (max 256 characters)')
        if ident in seen:
            _invalid(path + '/id', 'Duplicate node id: ' + ident)
        seen.add(ident)
        if kind not in SUPPORTED_KINDS:
            _invalid(path + '/kind', 'Unsupported node kind: ' + str(kind))
        if depth == 0 and kind != 'page':
            _invalid(path + '/kind', 'Root must be a page node')
        children = node.get('children', [])
        if not isinstance(children, list):
            _invalid(path + '/children', 'Expected array')
        if 'props' in node and not isinstance(node['props'], dict):
            _invalid(path + '/props', 'Expected object')
        if 'content' in node and not isinstance(node['content'], dict):
            _invalid(path + '/content', 'Expected object')
        if 'sourceRef' in node and not isinstance(node['sourceRef'], dict):
            _invalid(path + '/sourceRef', 'Expected object')
        if 'layout' in node:
            layout = node['layout']
            if not isinstance(layout, dict):
                _invalid(path + '/layout', 'Expected object')
            frac = layout.get('widthFraction')
            if frac is not None and (type(frac) not in (int, float) or not math.isfinite(frac) or not 0 < frac <= 1):
                _invalid(path + '/layout/widthFraction', 'Expected finite fraction within (0, 1]')
        if kind == 'richText' and not isinstance(node.get('props', {}).get('safeHtml'), str):
            _invalid(path + '/props/safeHtml', 'Rich text must provide HTML as string')
        if kind == 'image' and not isinstance(node.get('props', {}).get('src'), str):
            _invalid(path + '/props/src', 'Image must provide src as string')
        if kind == 'linkList':
            links = node.get('props', {}).get('items')
            if not isinstance(links, list) or any(not isinstance(x, dict) or not isinstance(x.get('url'), str) or not isinstance(x.get('label'), str) for x in links):
                _invalid(path + '/props/items', 'Link list requires url and label strings')
        for ix, child in enumerate(children):
            nodes.append((child, f'{path}/children/{ix}', depth + 1))
    for index, item in enumerate(ir['assets']):
        path = f'/assets/{index}'
        if not isinstance(item, dict) or not all(isinstance(item.get(field), str) for field in ('id', 'kind', 'originalUrl', 'resolvedUrl', 'status')):
            _invalid(path, 'Malformed asset record')
        target = item['resolvedUrl']
        if target.startswith('assets/'):
            parts = PurePosixPath(target).parts
            if len(parts) < 2 or any(p in ('.', '..') for p in target.split('/')) or '\\' in target:
                _invalid(path + '/resolvedUrl', 'Invalid local asset path')
    for index, diag in enumerate(ir['diagnostics']):
        if not isinstance(diag, dict) or not isinstance(diag.get('code'), str) or diag.get('severity') not in ('info', 'warning', 'error'):
            _invalid(f'/diagnostics/{index}', 'Malformed diagnostic')
    return ir
