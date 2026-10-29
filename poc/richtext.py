"""Conservative rich HTML serializer for offline Modern-page migrations.

Not a full browser HTML sanitizer. Inputs are untrusted; security requires a
browser-vetted sanitizer such as DOMPurify for production. Preserve only a
reviewed, inert subset and return an audit of deliberate transformations.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
import unicodedata
from urllib.parse import urljoin, urlsplit

ALLOWED_TAGS = frozenset({
    'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b', 'em', 'i',
    'ul', 'ol', 'li', 'a', 'br', 'blockquote', 'code', 'pre', 'table',
    'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'img', 'figure', 'figcaption',
})
VOID_TAGS = frozenset({'br', 'img'})
# A blocked subtree must never be flattened into executable descendants/text.
BLOCKED_TAGS = frozenset({
    'script', 'style', 'iframe', 'object', 'embed', 'svg', 'math',
    'form', 'textarea', 'template', 'noscript', 'video', 'audio',
    'canvas', 'select', 'button', 'input', 'link', 'meta', 'base',
})
MAX_HTML_LENGTH = 1_000_000


def safe_url(value: str, base_url: str = '') -> str:
    """Accept only ordinary web/mailto URLs and safe relative references.

    Reject control characters and browser-differential backslash URLs. Do not
    treat an arbitrary source as trusted when resolving against a base URL.
    """
    if not isinstance(value, str) or not value or '\\' in value:
        return ''
    if any(unicodedata.category(c) in {'Cc', 'Cf'} for c in value):
        return ''
    value = value.strip()
    if not value or value.startswith('//'):
        return ''
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ''
    if parsed.scheme:
        if parsed.scheme.lower() not in {'https', 'http', 'mailto'}:
            return ''
        if parsed.scheme.lower() in {'http', 'https'}:
            try:
                port = parsed.port
            except ValueError:
                return ''
            if not parsed.hostname or parsed.username is not None or parsed.password is not None or '%' in parsed.netloc:
                return ''
        if parsed.scheme.lower() == 'mailto' and (not parsed.path or parsed.netloc):
            return ''
        return value
    if parsed.netloc or value.startswith('#'):
        return value if value.startswith('#') else ''
    if not base_url:
        return value
    try:
        parent = urlsplit(base_url)
        if parent.scheme.lower() not in {'http', 'https'} or not parent.hostname or parent.username is not None or parent.password is not None or '%' in parent.netloc:
            return ''
        resolved = urljoin(base_url, value)
    except ValueError:
        return ''
    return safe_url(resolved)


@dataclass(frozen=True)
class SanitizeResult:
    html: str
    removed_elements: dict[str, int]
    removed_attributes: int
    rejected_urls: int
    kept_inline_images: int

    @property
    def changed_for_safety(self) -> bool:
        return bool(self.removed_elements or self.removed_attributes or self.rejected_urls)


class _RichTextParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: list[str] = []
        self.stack: list[str] = []
        self.blocked = 0
        self.removed: Counter[str] = Counter()
        self.removed_attributes = 0
        self.rejected_urls = 0
        self.kept_images = 0

    def handle_starttag(self, tag, attrs):
        if tag in BLOCKED_TAGS:
            self.blocked += 1
            self.removed[tag] += 1
            return
        if self.blocked:
            return
        if tag not in ALLOWED_TAGS:
            self.removed[tag] += 1
            return
        attr = dict(attrs)
        keep: dict[str, str] = {}
        if tag == 'a' and attr.get('href') is not None:
            href = safe_url(attr['href'], self.base_url)
            if href:
                keep['href'] = href
            else:
                self.rejected_urls += 1
        if tag == 'img':
            src = safe_url(attr.get('src', ''), self.base_url)
            if src and urlsplit(src).scheme.lower() in {'http', 'https', ''} and not src.startswith('#'):
                keep['src'] = src
                keep['alt'] = str(attr.get('alt') or '')
                self.kept_images += 1
            else:
                self.rejected_urls += 1
                self.removed['img'] += 1
                return
        if tag == 'th' and attr.get('scope') in {'row', 'col', 'rowgroup', 'colgroup'}:
            keep['scope'] = attr['scope']
        if tag in {'td', 'th'}:
            for key in ('colspan', 'rowspan'):
                value = attr.get(key, '')
                if value and value.isascii() and value.isdecimal() and 1 <= int(value) <= 20:
                    keep[key] = str(int(value))
        self.removed_attributes += sum(1 for key, _ in attrs if key not in keep)
        extras = ''.join(f' {key}="{escape(value, quote=True)}"' for key, value in keep.items())
        self.parts.append(f'<{tag}{extras}>')
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in BLOCKED_TAGS:
            self.handle_endtag(tag)
        elif tag in ALLOWED_TAGS and tag not in VOID_TAGS and not self.blocked:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in BLOCKED_TAGS:
            if self.blocked:
                self.blocked -= 1
            return
        if self.blocked or tag not in self.stack:
            return
        while self.stack:
            current = self.stack.pop()
            self.parts.append(f'</{current}>')
            if current == tag:
                break

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(escape(data))

    def result(self) -> SanitizeResult:
        while self.stack:
            self.parts.append(f'</{self.stack.pop()}>')
        return SanitizeResult(''.join(self.parts), dict(self.removed), self.removed_attributes,
                              self.rejected_urls, self.kept_images)


def sanitize_with_audit(raw: str, base_url: str = '') -> SanitizeResult:
    if not isinstance(raw, str):
        raw = ''
    if len(raw) > MAX_HTML_LENGTH:
        raise ValueError('Rich text exceeds the maximum supported length')
    parser = _RichTextParser(base_url)
    parser.feed(raw)
    parser.close()
    return parser.result()


def sanitize_html(raw: str, base_url: str = '') -> str:
    return sanitize_with_audit(raw, base_url).html
