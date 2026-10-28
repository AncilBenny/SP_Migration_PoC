"""Destination-specific HTML/CSS mapping from generic page IR (offline PoC).

No SharePoint imports or source-parsing logic. Profiles select a small set of
safe, reviewed HTML renderers; they never supply executable markup or scripts.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import shutil

from .engine import safe_url, sanitize_html

TARGETS = {
    'hero': {'pageHeader'},
    'richText': {'contentBody'},
    'image': {'media'},
    'linkList': {'resourceCards', 'simpleLinks'},
    'unknown': {'reviewNote'},
}
DEFAULT_COMPONENTS = {
    'hero': 'pageHeader', 'richText': 'contentBody', 'image': 'media',
    'linkList': 'resourceCards', 'unknown': 'reviewNote',
}
COLORS = {'primary', 'background', 'surface', 'text', 'link'}
COLOR_RE = re.compile(r'^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$')
ALLOWED_FONTS = {'system', 'serif', 'sans-serif'}


def validate_profile(profile: dict) -> dict:
    if not isinstance(profile, dict) or profile.get('version') != '1.0':
        raise ValueError('Expected target mapping profile version 1.0')
    if not isinstance(profile.get('id'), str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', profile['id']):
        raise ValueError('Invalid profile id')
    if set(profile) - {'version', 'id', 'components', 'colors', 'layout', 'font', 'labels'}:
        raise ValueError('Unknown profile configuration keys')
    components = profile.get('components', {})
    if not isinstance(components, dict):
        raise ValueError('components must be an object')
    for kind, target in components.items():
        if kind not in TARGETS or target not in TARGETS[kind]:
            raise ValueError(f'Unrecognized target component: {kind} -> {target}')
    colors = profile.get('colors', {})
    if not isinstance(colors, dict) or set(colors) - COLORS:
        raise ValueError('Invalid color token')
    for value in colors.values():
        if not isinstance(value, str) or not COLOR_RE.fullmatch(value):
            raise ValueError('Colors must be hex, never raw CSS')
    layout = profile.get('layout', {})
    if not isinstance(layout, dict) or set(layout) - {'maxWidthPx', 'gapPx'}:
        raise ValueError('Invalid layout settings')
    for name, lo, hi in [('maxWidthPx', 600, 1800), ('gapPx', 0, 80)]:
        if name in layout and (type(layout[name]) is not int or not lo <= layout[name] <= hi):
            raise ValueError(f'Invalid {name}')
    if profile.get('font', 'system') not in ALLOWED_FONTS:
        raise ValueError('Unsupported font token')
    labels = profile.get('labels', {})
    if not isinstance(labels, dict) or set(labels) - {'resourcesHeading'}:
        raise ValueError('Invalid labels')
    if any(not isinstance(v, str) or len(v) > 120 for v in labels.values()):
        raise ValueError('Invalid label length')
    return profile


def render_target(ir: dict, profile: dict) -> tuple[str, str, dict]:
    """Render only generic IR; the source may be SharePoint or any future adapter."""
    validate_profile(profile)
    if not isinstance(ir, dict) or not isinstance(ir.get('tree'), dict):
        raise ValueError('Expected canonical page IR with tree')
    mapping = DEFAULT_COMPONENTS | profile.get('components', {})
    counts: Counter[str] = Counter()
    diagnostics: list[dict] = []
    base_url = ir.get('source', {}).get('url', '')

    def node_html(node: dict) -> str:
        kind = node.get('kind')
        children = ''.join(node_html(child) for child in node.get('children', []))
        if kind == 'page':
            return children
        if kind == 'section':
            return f'<section class="target-section"><div class="target-wrap">{children}</div></section>'
        if kind == 'columns':
            return f'<div class="target-grid">{children}</div>'
        if kind == 'column':
            raw = node.get('layout', {}).get('widthFraction', 1)
            try:
                width = float(raw)
            except (ValueError, TypeError):
                width = 1.0
            width = min(1.0, max(0.05, width))
            return f'<div class="target-column" style="--fraction:{width:.6f}">{children}</div>'
        if kind not in TARGETS:
            diagnostics.append({'code': 'TARGET_UNMAPPED_KIND', 'nodeId': str(node.get('id', 'unknown')), 'kind': str(kind)})
            return f'<aside class="target-unmapped" role="note">Unmapped content kind: {escape(str(kind))}</aside>'
        target = mapping[kind]
        counts[f'{kind}:{target}'] += 1
        data = node.get('content') or {}
        props = node.get('props') or {}
        if target == 'pageHeader':
            eyebrow = escape(str(props.get('eyebrow', '')))
            subtitle = f'<p class="target-eyebrow">{eyebrow}</p>' if eyebrow else ''
            return f'<header class="target-header"><div class="target-wrap">{subtitle}<h1>{escape(str(data.get("text", "")))}</h1></div></header>'
        if target == 'contentBody':
            # Sanitize again: a CIR file may be modified independently of extraction.
            return f'<div class="target-body">{sanitize_html(str(props.get("safeHtml", "")), base_url)}</div>'
        if target == 'media':
            original_src = str(props.get('src', ''))
            # Reuse assets already rewritten by the CIR build, instead of
            # resolving them back to the original SharePoint host.
            bundled = (original_src.startswith('assets/') and
                       '..' not in Path(original_src).parts and
                       any(a.get('resolvedUrl') == original_src for a in ir.get('assets', [])))
            src = original_src if bundled else safe_url(original_src, base_url)
            if src.startswith(('mailto:', '#')):
                src = ''
            alt = escape(str(data.get('altText', '')), quote=True)
            caption = escape(str(data.get('caption', '')))
            if not src:
                diagnostics.append({'code': 'TARGET_MISSING_IMAGE', 'nodeId': str(node.get('id', ''))})
                return '<aside class="target-unmapped">Image source unavailable</aside>'
            return f'<figure class="target-media"><img src="{escape(src, quote=True)}" alt="{alt}" loading="lazy"><figcaption>{caption}</figcaption></figure>'
        if target in {'simpleLinks', 'resourceCards'}:
            items = []
            for link in props.get('items', []):
                href = safe_url(str(link.get('url', '')), base_url)
                if not href:
                    diagnostics.append({'code': 'TARGET_UNSAFE_LINK', 'nodeId': str(node.get('id', ''))})
                    continue
                items.append((escape(str(link.get('label', ''))), escape(href, quote=True)))
            title = escape(profile.get('labels', {}).get('resourcesHeading', 'Resources'))
            if target == 'simpleLinks':
                links = ''.join(f'<li><a href="{href}">{label}</a></li>' for label, href in items)
                return f'<nav class="target-links" aria-label="{title}"><h2>{title}</h2><ul>{links}</ul></nav>'
            cards = ''.join(f'<article class="target-resource"><a href="{href}">{label}</a></article>' for label, href in items)
            return f'<section class="target-resources" aria-label="{title}"><h2>{title}</h2><div class="target-cards">{cards}</div></section>'
        if target == 'reviewNote':
            diagnostics.append({'code': 'TARGET_UNKNOWN_CONTROL', 'nodeId': str(node.get('id', ''))})
            return '<aside class="target-unmapped" role="note">This source component requires manual mapping.</aside>'
        raise ValueError('Unreachable target mapping')

    body = node_html(ir['tree'])
    page = ir.get('page') or {}
    title = escape(str(page.get('title', 'Page')))
    description = escape(str(page.get('description', '')), quote=True)
    html = (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="description" content="{description}"><title>{title}</title>'
            f'<link rel="stylesheet" href="style.css"></head><body><main>{body}</main></body></html>')
    palette = {'primary': '#26496b', 'background': '#f6f8fa', 'surface': '#ffffff', 'text': '#202c36', 'link': '#145f94'} | profile.get('colors', {})
    width = profile.get('layout', {}).get('maxWidthPx', 1100)
    gap = profile.get('layout', {}).get('gapPx', 24)
    font = {'system': 'system-ui,sans-serif', 'serif': 'Georgia,serif', 'sans-serif': 'Arial,sans-serif'}[profile.get('font', 'system')]
    variables = ':root{' + ''.join(f'--{k}:{v};' for k, v in palette.items()) + f'--content-width:{width}px;--gap:{gap}px;' + '}'
    css = variables + f'''*{{box-sizing:border-box}}body{{margin:0;color:var(--text);background:var(--background);font:16px/1.55 {font}}}.target-wrap{{max-width:var(--content-width);padding:0 24px;margin:auto}}.target-header{{padding:54px 0;background:var(--primary);color:#fff}}.target-header h1{{font-size:clamp(2rem,4vw,3.25rem);margin:0}}.target-eyebrow{{font-size:13px;letter-spacing:.12em;text-transform:uppercase}}.target-section{{padding:36px 0}}.target-grid{{display:flex;gap:var(--gap);align-items:start}}.target-column{{flex:calc(var(--fraction)*12) 1 0;min-width:0}}.target-body{{overflow-wrap:anywhere}}.target-body h2{{font-size:1.75rem}}.target-body a,.target-resources a,.target-links a{{color:var(--link)}}.target-media{{margin:0}}.target-media img{{max-width:100%;height:auto;display:block}}.target-media figcaption{{font-size:.85rem;color:var(--text)}}.target-resources{{padding:16px 0}}.target-cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}}.target-resource{{padding:18px;border:1px solid #d7dde3;background:var(--surface);border-radius:8px}}.target-resource a{{font-weight:700}}.target-unmapped{{padding:16px;border:2px dashed #777}}@media(max-width:720px){{.target-grid{{flex-direction:column}}.target-column{{width:100%;flex:none}}.target-wrap{{padding:0 16px}}}}'''
    report = {'profileId': profile['id'], 'inputFormat': 'canonical-page-ir', 'targetFormat': 'html-css',
              'mappedComponents': dict(counts), 'mappingWarnings': diagnostics,
              'sourceFidelity': 'not-evaluated-target-redesign-intent',
              'sharePointSourceReaderUsed': False}
    return html, css, report


def build_target(ir_path: Path, profile_path: Path, out: Path) -> dict:
    ir_bytes = ir_path.read_bytes()
    ir = json.loads(ir_bytes)
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    html, css, report = render_target(ir, profile)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'index.html').write_text(html, encoding='utf-8')
    (out / 'style.css').write_text(css, encoding='utf-8')
    # A copied IR is immutable input to the mapping step; source parser is not called.
    (out / 'page.ir.json').write_bytes(ir_bytes)
    report['irSha256'] = sha256(ir_bytes).hexdigest()
    report['inputIr'] = str(ir_path)
    (out / 'mapping-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for asset in ir.get('assets', []):
        path = asset.get('resolvedUrl', '')
        if path.startswith('assets/') and '..' not in Path(path).parts:
            source = ir_path.parent / path
            if not source.is_file():
                report['mappingWarnings'].append({'code': 'TARGET_MISSING_ASSET', 'path': path})
                continue
            destination = out / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    (out / 'mapping-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
