"""Safe, declarative URL routing for page, image and document destinations.

Destination policies never mutate the canonical IR. Rules match an entire HTTPS
origin and a path-directory boundary, not an arbitrary string prefix.
"""
from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

from .engine import safe_url

DOCUMENT_EXTS = frozenset({'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv', '.rtf', '.odt', '.ods', '.odp', '.zip'})
IMAGE_EXTS = frozenset({'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.avif', '.bmp', '.ico', '.tif', '.tiff'})
ROOT_KINDS = frozenset({'page', 'image', 'document'})


def reference_kind(value: str, *, tag: str = 'a') -> str:
    """Classify by known extension; unknown hyperlinks are pages by default."""
    if tag == 'img':
        return 'image'
    path = urlsplit(value).path.lower()
    extension = '.' + path.rsplit('.', 1)[-1] if '.' in path.rsplit('/', 1)[-1] else ''
    if extension in DOCUMENT_EXTS:
        return 'document'
    if extension in IMAGE_EXTS:
        return 'image'
    return 'page'


def _validate_directory_url(value: str, *, source: bool) -> None:
    if not isinstance(value, str) or not value or '\\' in value or len(value) > 2048:
        raise ValueError('Invalid source/target root')
    p = urlsplit(value)
    if (p.scheme != 'https' if source else p.scheme not in ('', 'https')) or p.username or p.password or p.query or p.fragment or not value.endswith('/'):
        raise ValueError('Root must be an HTTPS URL (or a root-relative destination) ending in /')
    if source and (not p.netloc or not p.hostname):
        raise ValueError('Source root must include a hostname')
    if not source and not (p.netloc and p.hostname or not p.netloc and value.startswith('/') and not value.startswith('//')):
        raise ValueError('Destination root must be HTTPS or root-relative')
    if any(segment in ('.', '..') for segment in p.path.split('/')) or '%2f' in p.path.lower() or '%5c' in p.path.lower() or '%' in p.netloc:
        raise ValueError('Unsafe root path')
    if not safe_url(value):
        raise ValueError('Unsafe source/target root')


def validate_url_mappings(rules: list) -> list:
    """Legacy generic mappings (kept compatible with existing profiles)."""
    if not isinstance(rules, list) or len(rules) > 100:
        raise ValueError('urlMappings must be a list of at most 100 entries')
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {'sourcePrefix', 'targetPrefix'}:
            raise ValueError('Each URL mapping requires sourcePrefix and targetPrefix')
        _validate_directory_url(rule['sourcePrefix'], source=True)
        _validate_directory_url(rule['targetPrefix'], source=False)
    return rules


def validate_root_mappings(rules: list) -> list:
    """Typed destination roots; stripAspx applies only to page references."""
    if not isinstance(rules, list) or len(rules) > 100:
        raise ValueError('rootMappings must be a list of at most 100 rules')
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) - {'kind', 'sourcePrefix', 'targetPrefix', 'stripAspx'} or not {'kind', 'sourcePrefix', 'targetPrefix'} <= set(rule):
            raise ValueError('Root mapping requires kind, sourcePrefix, targetPrefix')
        if rule['kind'] not in ROOT_KINDS:
            raise ValueError('Unknown root mapping kind')
        if 'stripAspx' in rule and (type(rule['stripAspx']) is not bool or rule['kind'] != 'page'):
            raise ValueError('stripAspx is a page-only boolean setting')
        _validate_directory_url(rule['sourcePrefix'], source=True)
        _validate_directory_url(rule['targetPrefix'], source=False)
    return rules


def _apply_rule(original: str, rule: dict, *, strip_aspx: bool = False) -> str | None:
    parts, source, destination = urlsplit(original), urlsplit(rule['sourcePrefix']), urlsplit(rule['targetPrefix'])
    if parts.scheme.lower() != source.scheme or parts.netloc.lower() != source.netloc.lower() or not parts.path.startswith(source.path):
        return None
    suffix = parts.path[len(source.path):]
    if strip_aspx and suffix.lower().endswith('.aspx'):
        suffix = suffix[:-5]
    result = urlunsplit((destination.scheme, destination.netloc, destination.path + suffix, parts.query, parts.fragment))
    return result if safe_url(result) else None


def rewrite_url(value: str, base: str, rules: list, audit: list, *, node_id: str,
                kind: str | None = None, root_mappings: list | None = None) -> str:
    """Rewrite based on source origin, path and reference type; retain query/fragment.

    Longest matching path wins within typed rules. Legacy generic mappings are
    a fallback only. Resolution never replaces unrelated lookalike hosts.
    """
    original = safe_url(value, base)
    if not original:
        return ''
    # Temporary Graph/SharePoint signed URLs are capabilities, not page assets.
    # Never carry them into the target HTML or rewrite history.
    from .dependencies import _signed
    if _signed(original):
        return ''
    parts = urlsplit(original)
    if parts.scheme not in {'http', 'https'}:
        return original
    kind = kind or reference_kind(original)
    applicable = [r for r in root_mappings or [] if r['kind'] == kind]
    for rule in sorted(applicable, key=lambda r: len(urlsplit(r['sourcePrefix']).path), reverse=True):
        rewritten = _apply_rule(original, rule, strip_aspx=rule.get('stripAspx', False))
        if rewritten is not None:
            if rewritten != original:
                audit.append({'nodeId': node_id, 'kind': kind, 'originalUrl': original, 'targetUrl': rewritten, 'rule': 'typed-root'})
            return rewritten
    for rule in sorted(rules, key=lambda r: len(urlsplit(r['sourcePrefix']).path), reverse=True):
        rewritten = _apply_rule(original, rule)
        if rewritten is not None:
            if rewritten != original:
                audit.append({'nodeId': node_id, 'kind': kind, 'originalUrl': original, 'targetUrl': rewritten, 'rule': 'legacy-url'})
            return rewritten
    return original


class LinkHTMLMapper(HTMLParser):
    """Re-serialize sanitized rich HTML while applying destination URL rules."""
    def __init__(self, base: str, rules: list, audit: list, node_id: str, root_mappings: list | None = None, *, keep_source_styles: bool = False):
        super().__init__(convert_charrefs=True)
        self.base, self.rules, self.audit, self.node_id, self.root_mappings = base, rules, audit, node_id, root_mappings
        self.parts: list[str] = []
        self.keep_source_styles = keep_source_styles

    def handle_starttag(self, tag: str, attrs):
        from .richtext import ALLOWED_TAGS
        if tag not in ALLOWED_TAGS:
            return
        attrs = dict(attrs)
        retained = {}
        if self.keep_source_styles:
            from .style_compiler import STYLE_CLASS
            if isinstance(attrs.get('class'), str) and STYLE_CLASS.fullmatch(attrs['class']):
                retained['class'] = attrs['class']
        if tag == 'a' and attrs.get('href'):
            href = rewrite_url(attrs['href'], self.base, self.rules, self.audit, node_id=self.node_id,
                               kind=reference_kind(attrs['href']), root_mappings=self.root_mappings)
            if href:
                retained['href'] = href
        if tag == 'img' and attrs.get('src'):
            src = rewrite_url(attrs['src'], self.base, self.rules, self.audit, node_id=self.node_id,
                              kind='image', root_mappings=self.root_mappings)
            if src and urlsplit(src).scheme.lower() in ('', 'http', 'https'):
                retained['src'] = src
                retained['alt'] = attrs.get('alt', '')
        if tag in ('td', 'th'):
            for name in ('rowspan', 'colspan'):
                if name in attrs and attrs[name].isascii() and attrs[name].isdecimal() and 1 <= int(attrs[name]) <= 20:
                    retained[name] = attrs[name]
        if tag == 'th' and attrs.get('scope') in ('row', 'col', 'rowgroup', 'colgroup'):
            retained['scope'] = attrs['scope']
        extra = ''.join(f' {key}="{escape(value, quote=True)}"' for key, value in retained.items())
        self.parts.append(f'<{tag}{extra}>')

    def handle_endtag(self, tag: str):
        from .engine import ALLOWED_TAGS, VOID_TAGS
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.parts.append(f'</{tag}>')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        from .richtext import VOID_TAGS
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str):
        self.parts.append(escape(data))

    def handle_entityref(self, name: str):
        self.parts.append(f'&{name};')

    def handle_charref(self, name: str):
        self.parts.append(f'&#{name};')


def rewrite_rich_html(raw: str, base: str, rules: list, audit: list, *, node_id: str,
                      root_mappings: list | None = None, keep_source_styles: bool = False) -> str:
    from .engine import sanitize_html
    parser = LinkHTMLMapper(base, rules, audit, node_id, root_mappings, keep_source_styles=keep_source_styles)
    parser.feed(sanitize_html(raw, base))
    parser.close()
    return ''.join(parser.parts)
