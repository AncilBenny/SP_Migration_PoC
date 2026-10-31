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
from .rewrites import validate_url_mappings, validate_root_mappings, rewrite_url, rewrite_rich_html

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
    if set(profile) - {'version', 'id', 'components', 'colors', 'layout', 'font', 'labels', 'urlMappings', 'assetDirectory', 'rootMappings', 'stylePolicy', 'behaviorMappings'}:
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
    if profile.get('stylePolicy', 'target') not in {'target', 'source-safe'}:
        raise ValueError('Invalid stylePolicy: expected target or source-safe')
    directory = profile.get('assetDirectory', 'assets')
    if not isinstance(directory, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', directory):
        raise ValueError('assetDirectory must be a simple safe folder name')
    validate_url_mappings(profile.get('urlMappings', []))
    validate_root_mappings(profile.get('rootMappings', []))
    from .behavior_compiler import validate_behavior_mappings
    validate_behavior_mappings(profile.get('behaviorMappings', []))
    return profile


def _all_nodes(root: dict):
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.get('children', []))


def render_target(ir: dict, profile: dict) -> tuple[str, str, dict]:
    """Render only generic IR; the source may be SharePoint or any future adapter."""
    validate_profile(profile)
    from .contracts import validate_ir
    validate_ir(ir)
    mapping = DEFAULT_COMPONENTS | profile.get('components', {})
    counts: Counter[str] = Counter()
    diagnostics: list[dict] = []
    base_url = ir.get('source', {}).get('url', '')
    url_audit: list[dict] = []
    node_mappings: list[dict] = []
    asset_rewrites: list[dict] = []
    asset_directory = profile.get('assetDirectory', 'assets')
    rules = profile.get('urlMappings', [])
    root_mappings = profile.get('rootMappings', [])
    from .style_compiler import compile_stylesheet, presentation_report
    style_policy = profile.get('stylePolicy', 'target')
    source_styles, style_summary = compile_stylesheet(ir, style_policy)
    present = presentation_report(ir, style_summary)
    from .behavior_compiler import validate_behavior_mappings, compile_behavior, compile_link_filter, BEHAVIOR_CSS
    behavior_plan = validate_behavior_mappings(profile.get('behaviorMappings', []))
    behavior_done = []
    behavior_scripts = set()

    def node_html(node: dict) -> str:
        kind = node.get('kind')
        children = ''.join(node_html(child) for child in node.get('children', []))
        if kind == 'page':
            return children
        if kind == 'section':
            if (node.get('props') or {}).get('placement') == 'sidebar':
                return f'<aside class="target-section target-sidebar" aria-label="Related page content"><div class="target-wrap">{children}</div></aside>'
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
        marker = ' data-ir-id="' + escape(str(node.get('id', '')), quote=True) + '"'
        target = mapping[kind]
        counts[f'{kind}:{target}'] += 1
        node_mappings.append({'nodeId': str(node.get('id', '')), 'sourceRef': node.get('sourceRef'), 'irKind': kind, 'targetComponent': target})
        data = node.get('content') or {}
        props = node.get('props') or {}
        if target == 'pageHeader':
            eyebrow = escape(str(props.get('eyebrow', '')))
            subtitle = f'<p class="target-eyebrow">{eyebrow}</p>' if eyebrow else ''
            image_url = str(props.get('imageUrl') or '')
            # The IR hero image is an asset, never an arbitrary script/markup.
            bundled = image_url.startswith('assets/') and any(a.get('resolvedUrl') == image_url for a in ir.get('assets', []))
            if bundled and asset_directory != 'assets':
                target_path = asset_directory + '/' + image_url[len('assets/'):]
                asset_rewrites.append({'nodeId': str(node.get('id', '')), 'originalPath': image_url, 'targetPath': target_path})
                image_url = target_path
            image_url = image_url if bundled else rewrite_url(image_url, base_url, rules, url_audit, node_id=str(node.get('id', '')), kind='image', root_mappings=root_mappings)
            figure = (f'<img class="target-hero-image" src="{escape(image_url, quote=True)}" alt="{escape(str(props.get("imageAlt") or ""), quote=True)}">' if image_url else '')
            return f'<header class="target-header"{marker}><div class="target-wrap">{figure}{subtitle}<h1>{escape(str(data.get("text", "")))}</h1></div></header>'
        if target == 'contentBody':
            # Sanitize again: a CIR file may be modified independently of extraction.
            rich_html = rewrite_rich_html(str(props.get('safeHtml', '')), base_url, rules, url_audit, node_id=str(node.get('id', '')), root_mappings=root_mappings, keep_source_styles=style_policy=='source-safe')
            if node['id'] in behavior_plan:
                compiled, js_needed, result = compile_behavior(str(node['id']), rich_html, behavior_plan[node['id']], content_marker=marker)
                rich_html = compiled
                behavior_done.append(result)
                if js_needed:
                    behavior_scripts.add('behavior.js')
            # Generated on-page navigation is not original source content.
            # Keep its links outside the independent preservation marker.
            if node['id'] in behavior_plan and behavior_plan[node['id']]['interaction'] == 'toc':
                return f'<div class="target-body">{rich_html}</div>'
            return f'<div class="target-body"{marker}>{rich_html}</div>'
        if target == 'media':
            original_src = str(props.get('src', ''))
            # Reuse assets already rewritten by the CIR build, instead of
            # resolving them back to the original SharePoint host.
            bundled = (original_src.startswith('assets/') and
                       '..' not in Path(original_src).parts and
                       any(a.get('resolvedUrl') == original_src for a in ir.get('assets', [])))
            src = original_src if bundled else rewrite_url(original_src, base_url, rules, url_audit, node_id=str(node.get('id', '')), kind='image', root_mappings=root_mappings)
            if bundled and asset_directory != 'assets':
                src = asset_directory + '/' + original_src[len('assets/'):]
                asset_rewrites.append({'nodeId': str(node.get('id', '')), 'originalPath': original_src, 'targetPath': src})
            if src.startswith(('mailto:', '#')):
                src = ''
            alt = escape(str(data.get('altText', '')), quote=True)
            caption = escape(str(data.get('caption', '')))
            if not src:
                diagnostics.append({'code': 'TARGET_MISSING_IMAGE', 'nodeId': str(node.get('id', ''))})
                return '<aside class="target-unmapped">Image source unavailable</aside>'
            return f'<figure class="target-media"{marker}><img src="{escape(src, quote=True)}" alt="{alt}" loading="lazy"><figcaption>{caption}</figcaption></figure>'
        if target in {'simpleLinks', 'resourceCards'}:
            items = []
            for link in props.get('items', []):
                href = rewrite_url(str(link.get('url', '')), base_url, rules, url_audit, node_id=str(node.get('id', '')), root_mappings=root_mappings)
                if not href:
                    diagnostics.append({'code': 'TARGET_UNSAFE_LINK', 'nodeId': str(node.get('id', ''))})
                    continue
                items.append((escape(str(link.get('label', ''))), escape(href, quote=True)))
            title = escape(profile.get('labels', {}).get('resourcesHeading', 'Resources'))
            enhanced = node['id'] in behavior_plan
            if target == 'simpleLinks':
                attr = ' data-filter-item' if enhanced else ''
                links = ''.join(f'<li{attr}><a href="{href}">{label}</a></li>' for label, href in items)
                result = f'<nav class="target-links"{marker} aria-label="{title}"><h2>{title}</h2><ul>{links}</ul></nav>'
            else:
                attr = ' data-filter-item' if enhanced else ''
                cards = ''.join(f'<article class="target-resource"{attr}><a href="{href}">{label}</a></article>' for label, href in items)
                result = f'<section class="target-resources"{marker} aria-label="{title}"><h2>{title}</h2><div class="target-cards">{cards}</div></section>'
            if enhanced:
                if behavior_plan[node['id']]['interaction'] != 'filterLinks':
                    raise ValueError('BEHAVIOR_INVALID_PLAN: linkList supports filterLinks only')
                result, js_needed, audit = compile_link_filter(str(node['id']), result, len(items))
                behavior_done.append(audit)
                if js_needed:
                    behavior_scripts.add('behavior.js')
            return result
        if target == 'reviewNote':
            diagnostics.append({'code': 'TARGET_UNKNOWN_CONTROL', 'nodeId': str(node.get('id', ''))})
            return f'<aside class="target-unmapped" role="note"{marker}>This source component requires manual mapping.</aside>'
        raise ValueError('Unreachable target mapping')

    # A reviewed interaction must match the semantic IR node kind.
    eligible = {n['id']: n['kind'] for n in _all_nodes(ir['tree'])}
    for node_id, plan in behavior_plan.items():
        required_kind = 'linkList' if plan['interaction'] == 'filterLinks' else 'richText'
        if eligible.get(node_id) != required_kind:
            raise ValueError(f'BEHAVIOR_INVALID_PLAN: {plan["interaction"]} requires an existing {required_kind} node')
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
    if style_summary['emittedRules']:
        html = html.replace('</head>', '<link rel="stylesheet" href="source-styles.css"></head>')
    css += '.target-hero-image{display:block;max-width:100%;height:auto}.target-sidebar{width:100%}'
    if behavior_done:
        css += BEHAVIOR_CSS
    if behavior_scripts:
        html = html.replace('</body>', '<script src="behavior.js" defer></script></body>')
    report = {'profileId': profile['id'], 'inputFormat': 'canonical-page-ir', 'targetFormat': 'html-css',
              'mappedComponents': dict(counts), 'nodeMappings': node_mappings, 'urlRewrites': url_audit, 'assetRewrites': asset_rewrites, 'mappingWarnings': diagnostics,
              'sourceFidelity': 'not-evaluated-target-redesign-intent',
              'sharePointSourceReaderUsed': False}
    from .style_compiler import format_generated_css
    report['presentation'] = present
    report['behavior'] = {'compiled':behavior_done, 'scriptAssets':sorted(behavior_scripts), 'sourceRuntimeCopied':False, 'fidelity':'interaction-not-verified-in-browser'}
    return html, format_generated_css(css), report


def build_target(ir_path: Path, profile_path: Path, out: Path, *, strict: bool = False) -> dict:
    ir_bytes = ir_path.read_bytes()
    ir = json.loads(ir_bytes)
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    html, css, report = render_target(ir, profile)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'index.html').write_text(html, encoding='utf-8')
    if report['behavior']['scriptAssets']:
        from .behavior_compiler import BEHAVIOR_JS
        (out / 'behavior.js').write_text(BEHAVIOR_JS, encoding='utf-8')
    (out / 'style.css').write_text(css, encoding='utf-8')
    if report['presentation']['stylesheet']['emittedRules']:
        from .style_compiler import compile_stylesheet
        source_css, _ = compile_stylesheet(ir, 'source-safe')
        (out / 'source-styles.css').write_text(source_css, encoding='utf-8')
    (out / 'presentation-report.json').write_text(json.dumps(report['presentation'], indent=2) + '\n', encoding='utf-8')
    # A copied IR is immutable input to the mapping step; source parser is not called.
    (out / 'page.ir.json').write_bytes(ir_bytes)
    report['irSha256'] = sha256(ir_bytes).hexdigest()
    report['inputIr'] = str(ir_path)
    (out / 'mapping-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for asset in ir.get('assets', []):
        path = asset.get('resolvedUrl', '')
        if path.startswith('assets/') and '..' not in Path(path).parts:
            source = ir_path.parent / path
            if (not source.is_file() or source.is_symlink() or
                    not source.resolve().is_relative_to(ir_path.parent.resolve())):
                report['mappingWarnings'].append({'code': 'TARGET_MISSING_ASSET', 'path': path})
                continue
            dest_path = profile.get('assetDirectory', 'assets') + '/' + path[len('assets/'):]
            destination = out / dest_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    from .dependencies import audit_export
    from .acquisition import plan_acquisition
    acquisition_plan = plan_acquisition(ir, profile)
    (out / 'acquisition-plan.json').write_text(json.dumps(acquisition_plan, indent=2) + '\n', encoding='utf-8')
    export_files = {'index.html': html.encode('utf-8'), 'style.css': css.encode('utf-8')}
    if report['behavior']['scriptAssets']:
        export_files['behavior.js'] = (out / 'behavior.js').read_bytes()
    if report['presentation']['stylesheet']['emittedRules']:
        export_files['source-styles.css'] = (out / 'source-styles.css').read_bytes()
    for asset in ir.get('assets', []):
        path = asset.get('resolvedUrl', '')
        if path.startswith('assets/'):
            target = profile.get('assetDirectory', 'assets') + '/' + path[len('assets/'):]
            destination = out / target
            if destination.is_file() and not destination.is_symlink() and destination.resolve().is_relative_to(out.resolve()):
                export_files[target] = destination.read_bytes()
    dependency_audit = audit_export(ir, html, export_files, mode='client')
    if dependency_audit['sourceSensitiveReferenceCount'] or any(dep['status'] == 'blocked' and dep['reason'].startswith('Preauthenticated')
           for dep in dependency_audit['dependencies']):
        raise ValueError('PREAUTHENTICATED_REFERENCE_BLOCKED: remove temporary credential URLs before export')
    (out / 'dependency-manifest.json').write_text(json.dumps(dependency_audit, indent=2) + '\n', encoding='utf-8')
    from .validation import ir_to_html
    output_check = ir_to_html(ir, html, profile, out)
    input_quality_path = ir_path.parent / 'quality-report.json'
    source_check = {'status': 'unavailable; IR provenance only'}
    if input_quality_path.is_file():
        original = json.loads(input_quality_path.read_text(encoding='utf-8'))
        if original.get('irSha256') == report['irSha256']:
            source_check = original.get('sourceToIr', source_check)
    if dependency_audit['blocked']:
        output_check['passed'] = False
        output_check.setdefault('items', []).append({'nodeId': 'dependency-manifest', 'kind': 'dependency', 'status': 'lost', 'reason': 'Missing or unsafe bundled dependencies'})
        output_check['summary']['lost'] = output_check['summary'].get('lost', 0) + 1
    quality = {'version': '1.0', 'dependencyAudit': dependency_audit['summary'], 'irSha256': report['irSha256'],
               'sourceToIr': source_check, 'irToHtml': output_check,
               'passed': output_check['passed'] and source_check.get('passed', True),
               'visualFidelity': 'not-evaluated-client-target-intent'}
    (out / 'quality-report.json').write_text(json.dumps(quality, indent=2) + '\n', encoding='utf-8')
    report['acquisitionPlan'] = {'file': 'acquisition-plan.json', 'candidates': acquisition_plan['count']}
    report['dependencies'] = {'manifest': 'dependency-manifest.json', 'summary': dependency_audit['summary']}
    report['contentAccounting'] = {'passed': quality['passed'],
                                   'outputSummary': output_check['summary'],
                                   'qualityReport': 'quality-report.json'}
    (out / 'mapping-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if strict and not quality['passed']:
        raise ValueError('Target content accounting failed; see quality-report.json')
    return report
