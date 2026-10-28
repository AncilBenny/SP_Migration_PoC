"""Safe, declarative destination URL rewriting; never mutates canonical IR."""
from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

from .engine import safe_url


def validate_url_mappings(rules: list) -> list:
    if not isinstance(rules, list) or len(rules) > 100:
        raise ValueError("urlMappings must be a list of at most 100 entries")
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {"sourcePrefix", "targetPrefix"}:
            raise ValueError("Each URL mapping requires sourcePrefix and targetPrefix")
        source, target = rule["sourcePrefix"], rule["targetPrefix"]
        if not isinstance(source, str) or not isinstance(target, str):
            raise ValueError("URL mapping prefixes must be strings")
        src = urlsplit(source)
        if src.scheme != "https" or not src.netloc or src.username or src.password or src.query or src.fragment or not source.endswith("/"):
            raise ValueError("sourcePrefix must be a full HTTPS URL ending in /")
        if target.startswith("//") or not target.endswith("/") or not safe_url(target):
            raise ValueError("targetPrefix must be a safe path or HTTPS URL ending in /")
        dest = urlsplit(target)
        if dest.scheme not in {"", "https"} or (not dest.scheme and not target.startswith("/")) or dest.query or dest.fragment:
            raise ValueError("targetPrefix must be root-relative or HTTPS, without query/fragment")
    return rules


def rewrite_url(value: str, base: str, rules: list, audit: list, *, node_id: str) -> str:
    """Resolve source URL, rewrite only matching URL origin AND path boundary."""
    original = safe_url(value, base)
    if not original:
        return ""
    parts = urlsplit(original)
    if parts.scheme not in {"http", "https"}:
        return original
    for rule in rules:
        src, dest = urlsplit(rule["sourcePrefix"]), urlsplit(rule["targetPrefix"])
        if parts.scheme != src.scheme or parts.netloc.lower() != src.netloc.lower() or not parts.path.startswith(src.path):
            continue
        suffix = parts.path[len(src.path):]
        target_path = dest.path + suffix
        rewritten = urlunsplit((dest.scheme, dest.netloc, target_path, parts.query, parts.fragment))
        if rewritten != original and safe_url(rewritten):
            audit.append({"nodeId": node_id, "originalUrl": original, "targetUrl": rewritten})
            return rewritten
    return original


class LinkHTMLMapper(HTMLParser):
    """Re-serialize sanitized rich HTML while applying URL destination rules."""
    def __init__(self, base: str, rules: list, audit: list, node_id: str):
        super().__init__(convert_charrefs=True)
        self.base, self.rules, self.audit, self.node_id = base, rules, audit, node_id
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        from .engine import ALLOWED_TAGS
        if tag not in ALLOWED_TAGS:
            return
        attr = dict(attrs)
        extra = ""
        if tag == "a" and attr.get("href"):
            target = rewrite_url(attr["href"], self.base, self.rules, self.audit, node_id=self.node_id)
            if target:
                extra = f' href="{escape(target, quote=True)}"'
        self.parts.append(f"<{tag}{extra}>")

    def handle_endtag(self, tag: str):
        from .engine import ALLOWED_TAGS, VOID_TAGS
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str):
        self.parts.append(escape(data))

    def handle_entityref(self, name: str):
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str):
        self.parts.append(f"&#{name};")


def rewrite_rich_html(raw: str, base: str, rules: list, audit: list, *, node_id: str) -> str:
    from .engine import sanitize_html
    parser = LinkHTMLMapper(base, rules, audit, node_id)
    parser.feed(sanitize_html(raw, base))
    parser.close()
    return "".join(parser.parts)
