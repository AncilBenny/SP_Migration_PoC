"""Offline content-accounting for one Modern source -> CIR -> target HTML.

Checks observable output, not just the renderer's reported mappings. This is a
content/structure check, NOT source visual-fidelity or browser behavior testing.
No third-party packages or SharePoint login required.
"""
from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlsplit

from .engine import IMAGE_ID, QUICKLINKS_ID, safe_url
from .rewrites import rewrite_url


def normalized_text(parts: list[str] | str) -> str:
    return ' '.join((' '.join(parts) if isinstance(parts, list) else parts).split())


class HTMLFacts(HTMLParser):
    """Visible-ish semantic facts from source rich HTML or an output fragment.

    Does not evaluate computed styles. Scripts/styles, templates and hidden
    iframe content are excluded; CSS-hidden elements cannot be detected here.
    """
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.links: list[str] = []
        self.images: list[dict] = []
        self.headings: Counter[str] = Counter()
        self.blocked = 0

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'template', 'iframe'}:
            self.blocked += 1
            return
        if self.blocked:
            return
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag == 'img':
            self.images.append({'src': attrs.get('src', ''), 'alt': attrs.get('alt', '')})
        if tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
            self.headings[tag] += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'template', 'iframe'}:
            self.blocked = max(0, self.blocked - 1)

    def handle_data(self, data):
        if not self.blocked:
            self.text.append(data)


def html_facts(raw: str) -> HTMLFacts:
    f = HTMLFacts()
    f.feed(raw)
    f.close()
    return f


class OutputInventory(HTMLParser):
    """Read generated DOM markers and actual nested text, links and images.

    Markers are added to rendered components only; output can be independently
    changed or corrupted, and validation will flag missing or changed items.
    """
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.active: list[tuple[int, str]] = []
        self.nodes: dict[str, dict] = {}
        self.duplicates: set[str] = set()
        self.blocked = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {'script', 'style'}:
            self.blocked += 1
        if not self.blocked:
            ident = attrs.get('data-ir-id')
            if ident is not None:
                if ident in self.nodes:
                    self.duplicates.add(ident)
                self.nodes[ident] = {'text': [], 'links': [], 'images': [], 'headings': Counter()}
                self.active.append((self.depth, ident))
            if self.active:
                data = self.nodes[self.active[-1][1]]
                if tag == 'a' and attrs.get('href'):
                    data['links'].append(attrs['href'])
                if tag == 'img':
                    data['images'].append({'src': attrs.get('src', ''), 'alt': attrs.get('alt', '')})
                if tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
                    data['headings'][tag] += 1
        if tag not in self.VOID:
            self.depth += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag not in self.VOID:
            self.depth = max(0, self.depth - 1)
        if tag in {'script', 'style'}:
            self.blocked = max(0, self.blocked - 1)
        while self.active and self.depth <= self.active[-1][0]:
            self.active.pop()

    def handle_data(self, data):
        if not self.blocked and self.active:
            self.nodes[self.active[-1][1]]['text'].append(data)


def leaf_nodes(ir: dict):
    def visit(node):
        if node.get('kind') in {'hero', 'richText', 'image', 'linkList', 'unknown'}:
            yield node
        for child in node.get('children') or []:
            yield from visit(child)
    yield from visit(ir['tree'])


def source_to_ir(source: dict, ir: dict) -> dict:
    """Account for known Modern Graph-like input blocks after canvas decoding.

    Input may be a PnP CanvasContent1 fixture first decoded into Graph-like
    sections. For unsupported controls, never report lossless conversion.
    """
    index = {n['id']: n for n in leaf_nodes(ir)}
    entries = []
    for ix, section in enumerate(source.get('canvasLayout', {}).get('horizontalSections', [])):
        for ci, col in enumerate(section.get('columns') or []):
            if 'webparts' not in col:
                entries.append({'nodeId': f'section-{ix}-column-{ci}', 'kind': 'sourceCompleteness',
                                'status': 'needs-review', 'reason': 'Expanded webparts relationship was not supplied'})
    vertical_section = source.get('canvasLayout', {}).get('verticalSection')
    if isinstance(vertical_section, dict) and 'webparts' not in vertical_section:
        entries.append({'nodeId': 'vertical-section', 'kind': 'sourceCompleteness',
                        'status': 'needs-review', 'reason': 'Expanded vertical webparts were not supplied'})
    title = str(source.get('title') or '')
    hero = next((n for n in index.values() if n['kind'] == 'hero'), None)
    entries.append({'nodeId': 'title-area', 'kind': 'pageTitle',
                    'status': 'preserved' if hero and hero.get('content', {}).get('text') == title else 'lost'})
    vertical = source.get('canvasLayout', {}).get('verticalSection')
    if vertical is not None:
        sections = [n for n in ir['tree'].get('children', []) if n.get('kind') == 'section'
                    and n.get('props', {}).get('placement') == 'sidebar']
        entries.append({'nodeId': 'vertical-section', 'kind': 'layout',
                        'status': 'needs-review' if sections else 'lost',
                        'reason': 'Sidebar content captured, but placement and styling need review' if sections
                                  else 'Source vertical section absent from CIR'})
    source_sections = list(source.get('canvasLayout', {}).get('horizontalSections', []))
    if vertical is not None:
        source_sections.append({'columns': [{'webparts': vertical.get('webparts') or []}]})
    for section in source_sections:
        for col in section.get('columns', []):
            for part in col.get('webparts') or []:
                part_id = str(part.get('id') or '')
                node = index.get(part_id)
                if not node:
                    entries.append({'nodeId': part_id, 'kind': 'webPart', 'status': 'lost', 'reason': 'No CIR node'})
                    continue
                kind = node['kind']
                if kind == 'unknown':
                    entries.append({'nodeId': part_id, 'kind': 'unknown', 'status': 'needs-review',
                                    'reason': 'Unmapped source control preserved as explicit unknown'})
                    continue
                if kind == 'richText':
                    old = html_facts(str(part.get('innerHtml') or ''))
                    new = html_facts(node.get('props', {}).get('safeHtml', ''))
                    source_links = [safe_url(link, source.get('webUrl', '')) for link in old.links]
                    ok = (normalized_text(old.text) == normalized_text(new.text)
                          and Counter(x for x in source_links if x) == Counter(new.links)
                          and old.headings == new.headings)
                    unsafe_links = any(not x for x in source_links)
                    # Unsupported inline images are not silently declared preserved.
                    if old.images or unsafe_links:
                        reasons = []
                        if old.images:
                            reasons.append(f'{len(old.images)} inline image(s) need dedicated extraction')
                        if unsafe_links:
                            reasons.append('Unsafe hyperlink(s) rejected and require review')
                        if not ok:
                            reasons.append('Other rich text mismatch detected')
                        entries.append({'nodeId': part_id, 'kind': kind, 'status': 'needs-review',
                                        'reason': '; '.join(reasons)})
                    else:
                        entries.append({'nodeId': part_id, 'kind': kind, 'status': 'preserved' if ok else 'lost',
                                        'reason': '' if ok else 'Rich text, headings or hyperlink missing in CIR'})
                elif kind == 'image':
                    src = node.get('props', {}).get('src', '')
                    asset_id = node.get('content', {}).get('assetId', '')
                    asset = next((a for a in ir.get('assets', []) if a.get('id') == asset_id), None)
                    entries.append({'nodeId': part_id, 'kind': kind,
                                    'status': 'preserved' if src and asset and asset.get('resolvedUrl') == src else 'lost',
                                    'reason': '' if src and asset else 'Image is missing asset provenance'})
                elif kind == 'linkList':
                    old_items = part.get('data', {}).get('properties', {}).get('items', [])
                    observed = [(str(x.get('title') or x.get('description') or x.get('url') or ''), safe_url(str(x.get('url') or (x.get('sourceItem') or {}).get('url') or ''), source.get('webUrl', ''))) for x in old_items if isinstance(x, dict)]
                    actual = [(x.get('label'), x.get('url')) for x in node.get('props', {}).get('items', [])]
                    complete = all(url for _, url in observed) and observed == actual
                    entries.append({'nodeId': part_id, 'kind': kind,
                                    'status': 'preserved' if complete else 'needs-review',
                                    'reason': '' if complete else 'Some Quick Links are missing or unsafe'})
                else:
                    entries.append({'nodeId': part_id, 'kind': kind, 'status': 'needs-review',
                                    'reason': 'No source-level field accounting available'})
    counts = Counter(x['status'] for x in entries)
    return {'passed': counts['lost'] == 0, 'summary': dict(counts), 'items': entries,
            'scope': 'Modern public fixture field/semantic checks; not computed CSS or visual fidelity'}


def ir_to_html(ir: dict, html: str, profile: dict, output_dir: Path | None = None) -> dict:
    """Check actual rendered HTML and optionally bundled assets against IR.

    'passed' means no detected loss in the supported content subset, never that
    CSS/JS, live remote URLs, or true source-to-target fidelity were verified.
    """
    dom = OutputInventory()
    dom.feed(html)
    dom.close()
    expected_nodes = list(leaf_nodes(ir))
    ids = [n['id'] for n in expected_nodes]
    rules = profile.get('urlMappings', [])
    roots = profile.get('rootMappings', [])
    base = ir.get('source', {}).get('url', '')
    asset_dir = profile.get('assetDirectory', 'assets')
    statuses = []
    if len(ids) != len(set(ids)):
        statuses.append({'nodeId': '(duplicate)', 'kind': 'integrity', 'status': 'lost', 'reason': 'Duplicate CIR node IDs'})
    for node_id in dom.duplicates:
        statuses.append({'nodeId': node_id, 'kind': 'integrity', 'status': 'lost', 'reason': 'Duplicate data-ir-id in output'})
    for node in expected_nodes:
        ident, kind = node['id'], node['kind']
        actual = dom.nodes.get(ident)
        if actual is None:
            statuses.append({'nodeId': ident, 'kind': kind, 'status': 'lost', 'reason': 'No matching data-ir-id in target HTML'})
            continue
        if kind == 'unknown':
            statuses.append({'nodeId': ident, 'kind': kind, 'status': 'needs-review',
                             'reason': 'Explicit placeholder; original behavior/content not migrated'})
            continue
        expected_text: str | None = None
        expected_links: list[str] = []
        expected_headings = Counter()
        expected_images: list[dict] = []
        if kind == 'hero':
            props = node.get('props') or {}
            expected_text = normalized_text([str(props.get('eyebrow', '')), str(node.get('content', {}).get('text', ''))])
            expected_headings['h1'] = 1
            if props.get('imageUrl'):
                src = str(props['imageUrl'])
                bundled = src.startswith('assets/') and any(a.get('resolvedUrl') == src for a in ir.get('assets', []))
                if bundled and asset_dir != 'assets':
                    src = asset_dir + '/' + src[len('assets/'):]
                if not bundled:
                    src = rewrite_url(src, base, rules, [], node_id=ident, kind='image', root_mappings=roots)
                expected_images = [{'src': src, 'alt': str(props.get('imageAlt') or '')}]
        elif kind == 'richText':
            facts = html_facts(str(node.get('props', {}).get('safeHtml', '')))
            expected_text = normalized_text(facts.text)
            expected_headings = facts.headings
            expected_links = [rewrite_url(link, base, rules, [], node_id=ident, root_mappings=roots) for link in facts.links]
            expected_images = [{'src': rewrite_url(img['src'], base, rules, [], node_id=ident, kind='image', root_mappings=roots), 'alt': img['alt']} for img in facts.images]
        elif kind == 'image':
            content = node.get('content') or {}
            expected_text = normalized_text(str(content.get('caption') or ''))
            src = str(node.get('props', {}).get('src') or '')
            bundled = src.startswith('assets/') and any(a.get('resolvedUrl') == src for a in ir.get('assets', []))
            if bundled and asset_dir != 'assets':
                src = asset_dir + '/' + src[len('assets/'):]
            if not bundled:
                src = rewrite_url(src, base, rules, [], node_id=ident, kind='image', root_mappings=roots)
            expected_images = [{'src': src, 'alt': str(content.get('altText') or '')}]
        elif kind == 'linkList':
            items = node.get('props', {}).get('items', [])
            # Client output can introduce a section heading, hence test labels in order.
            labels = [normalized_text(str(x.get('label') or '')) for x in items]
            actual_text = normalized_text(actual['text'])
            cursor = 0
            labels_ok = True
            for label in labels:
                idx = actual_text.find(label, cursor)
                if idx < 0:
                    labels_ok = False
                    break
                cursor = idx + len(label)
            expected_links = [rewrite_url(str(x.get('url', '')), base, rules, [], node_id=ident, root_mappings=roots) for x in items]
            expected_text = None
        else:
            labels_ok = True
        actual_text = normalized_text(actual['text'])
        text_ok = (expected_text is None or expected_text == actual_text)
        link_ok = Counter(expected_links) == Counter(actual['links'])
        headings_ok = expected_headings == actual['headings'] if kind in {'hero', 'richText'} else True
        images_ok = expected_images == actual['images']
        if kind == 'linkList':
            text_ok = labels_ok
        asset_ok = True
        if kind == 'image' and expected_images and output_dir is not None:
            src = expected_images[0]['src']
            parsed = urlsplit(src)
            if not parsed.scheme and not src.startswith('/'):
                asset_ok = bool(src and '..' not in Path(src).parts and (output_dir / src).is_file())
        errors = [name for name, ok in [('text', text_ok), ('links', link_ok), ('headings', headings_ok),
                                        ('images', images_ok), ('bundled asset', asset_ok)] if not ok]
        statuses.append({'nodeId': ident, 'kind': kind, 'status': 'lost' if errors else 'preserved',
                         'reason': 'Mismatched: ' + ', '.join(errors) if errors else ''})
    counts = Counter(x['status'] for x in statuses)
    return {'passed': counts['lost'] == 0, 'summary': dict(counts), 'items': statuses,
            'unverified': ['Computed CSS fidelity', 'JavaScript behavior', 'Remote URL accessibility', 'Pixel-level visual comparison']}


def validate_target_file(ir_path: Path, html_path: Path, profile_path: Path) -> dict:
    """Independently re-check a built page after manual edits or mapping changes."""
    import json
    from hashlib import sha256
    ir_bytes = ir_path.read_bytes()
    ir = json.loads(ir_bytes)
    from .contracts import validate_ir
    validate_ir(ir)
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    from .mapping import validate_profile
    validate_profile(profile)
    report = ir_to_html(ir, html_path.read_text(encoding='utf-8'), profile, html_path.parent)
    quality = {'version': '1.0', 'irSha256': sha256(ir_bytes).hexdigest(),
               'irToHtml': report, 'passed': report['passed'],
               'visualFidelity': 'not-evaluated'}
    (html_path.parent / 'quality-check.json').write_text(json.dumps(quality, indent=2) + '\n', encoding='utf-8')
    return quality
