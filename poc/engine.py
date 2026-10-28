"""Offline Modern SharePoint Graph -> portable CIR -> standalone HTML PoC.

No network, credentials, SharePoint runtime, or third-party dependencies.
Only a deliberately small subset of common standard web parts is mapped.
"""
from __future__ import annotations

from collections import Counter
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urljoin, urlsplit

IMAGE_ID = "d1d91016-032f-456d-98a4-721247c305e8"
QUICKLINKS_ID = "c70391ea-0b10-4ee9-b2b4-006d3fcad0cd"
ALLOWED_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "em", "i", "ul", "ol", "li", "a", "br", "blockquote", "code", "pre", "table", "thead", "tbody", "tr", "td", "th"}
VOID_TAGS = {"br"}


def safe_url(value: str, base_url: str = "") -> str:
    """Reject executable/opaque schemes; resolve ordinary SharePoint-relative URLs."""
    if not isinstance(value, str) or not value or any(ord(ch) < 32 for ch in value):
        return ""
    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme and parts.scheme.lower() not in {"https", "http", "mailto"}:
        return ""
    if value.startswith("//"):
        return ""
    if parts.scheme:
        return value
    if value.startswith("#"):
        return value
    if not base_url:
        return value
    if not urlsplit(base_url).scheme in {"http", "https"}:
        return ""
    return urljoin(base_url, value)


class CleanHTML(HTMLParser):
    """Small allow-list HTML serializer; never echo executable markup."""
    def __init__(self, base_url: str = ""):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.output: list[str] = []
        self.stack: list[str] = []
        self.blocked = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag in {"script", "style", "iframe", "object", "svg", "form"}:
            self.blocked += 1
            return
        if self.blocked or tag not in ALLOWED_TAGS:
            return
        attrs = dict(attrs)
        extra = ""
        if tag == "a":
            href = safe_url(attrs.get("href", ""), self.base_url)
            if href:
                extra = f' href="{escape(href, quote=True)}"'
        self.output.append(f"<{tag}{extra}>")
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str):
        if tag in {"script", "style", "iframe", "object", "svg", "form"}:
            if self.blocked:
                self.blocked -= 1
            return
        if self.blocked or tag not in self.stack:
            return
        while self.stack:
            top = self.stack.pop()
            self.output.append(f"</{top}>")
            if top == tag:
                break

    def handle_data(self, data: str):
        if not self.blocked:
            self.output.append(escape(data))

    def get_html(self) -> str:
        while self.stack:
            self.output.append(f"</{self.stack.pop()}>")
        return "".join(self.output)


def sanitize_html(raw: str, base_url: str = "") -> str:
    parser = CleanHTML(base_url)
    parser.feed(raw if isinstance(raw, str) else "")
    parser.close()
    return parser.get_html()


def processed_value(data: dict, category: str, key: str) -> str:
    """Graph serverProcessedContent may contain lists of {key,value} or maps."""
    processed = (data.get("serverProcessedContent") or {}).get(category) or {}
    if isinstance(processed, dict):
        value = processed.get(key, "")
        return value if isinstance(value, str) else ""
    if isinstance(processed, list):
        for item in processed:
            if isinstance(item, dict) and item.get("key") == key:
                value = item.get("value")
                return value if isinstance(value, str) else ""
    return ""


def normalize(page: dict, *, asset_map: dict[str, str] | None = None) -> dict:
    if not isinstance(page, dict) or not isinstance(page.get("canvasLayout"), dict):
        raise ValueError("Expected a modern Graph sitePage object with expanded canvasLayout")
    page_type = str(page.get("@odata.type", "")).lstrip("#").lower()
    if page_type and page_type != "microsoft.graph.sitepage":
        raise ValueError("Expected microsoft.graph.sitePage, not " + page_type)
    base_url = page.get("webUrl", "")
    asset_map = asset_map or {}
    assets: list[dict] = []
    diagnostics: list[dict] = []
    counts = Counter()
    page_id = str(page.get("id") or "page")

    def asset(original: str, id: str, alt: str) -> str:
        resolved = safe_url(original, base_url)
        if not resolved:
            diagnostics.append({"severity": "warning", "code": "INVALID_ASSET_URL", "nodeId": id, "message": "Missing or unsafe image URL"})
            return ""
        target = asset_map.get(resolved, resolved)
        # Only a known, explicitly bundled demo asset may use a relative URL.
        local = target.startswith("assets/") and ".." not in Path(target).parts
        if target != resolved and not local:
            raise ValueError("Asset mapping must reference an assets/ file")
        assets.append({"id": id, "kind": "image", "originalUrl": resolved, "resolvedUrl": target, "status": "resolved" if local else "external", "altText": alt})
        return target

    def content_part(part: dict, index: int) -> dict:
        part_id = str(part.get("id") or f"part-{index}")
        source_ref = {"webPartId": part_id, "evidence": "synthetic"}
        if part.get("_capturePointer"):
            source_ref["capturePointer"] = str(part["_capturePointer"])
        odata = str(part.get("@odata.type", "")).lower().lstrip("#")
        if odata.endswith("textwebpart") or ("innerHtml" in part and not part.get("webPartType")):
            html = sanitize_html(part.get("innerHtml", ""), base_url)
            counts["richText"] += 1
            return {"id": part_id, "kind": "richText", "props": {"safeHtml": html}, "sourceRef": source_ref, "fidelity": {"status": "approximate", "reason": "Safe HTML subset; styling and inline controls are not reproduced"}}

        part_type = str(part.get("webPartType") or "").lower()
        source_ref["webPartType"] = part_type
        data = part.get("data") or {}
        props = data.get("properties") or {}
        if part_type == IMAGE_ID:
            image_url = processed_value(data, "imageSources", "imageSource") or props.get("imageSource", "") or props.get("src", "")
            alt = str(props.get("altText") or "")
            src = asset(str(image_url), "asset-" + part_id, alt)
            counts["image"] += 1
            if not src:
                return {"id": part_id, "kind": "unknown", "sourceRef": source_ref, "props": {"reason": "Image source missing"}, "fidelity": {"status": "unsupported", "reason": "Image URL missing"}}
            if not alt:
                diagnostics.append({"severity": "warning", "code": "MISSING_ALT_TEXT", "nodeId": part_id, "message": "Image has no alt text; review whether it is decorative"})
            return {"id": part_id, "kind": "image", "content": {"assetId": "asset-" + part_id, "altText": alt, "caption": str(props.get("captionText") or "")}, "props": {"src": src}, "sourceRef": source_ref, "fidelity": {"status": "approximate", "reason": "Source cropping and rendering options not reproduced"}}
        if part_type == QUICKLINKS_ID:
            links = []
            for item in props.get("items", []):
                if not isinstance(item, dict):
                    continue
                url = safe_url(str(item.get("url") or (item.get("sourceItem") or {}).get("url") or ""), base_url)
                if url:
                    links.append({"label": str(item.get("title") or item.get("description") or url), "url": url})
            if links:
                counts["linkList"] += 1
                return {"id": part_id, "kind": "linkList", "props": {"items": links}, "sourceRef": source_ref, "fidelity": {"status": "approximate", "reason": "Quick Links visual variants not reproduced"}}

        counts["unknown"] += 1
        diagnostics.append({"severity": "warning", "code": "UNMAPPED_WEBPART", "nodeId": part_id, "message": "Unsupported or unrecognized web part: " + (part_type or "missing type")})
        return {"id": part_id, "kind": "unknown", "props": {"sourceType": part_type}, "sourceRef": source_ref, "fidelity": {"status": "unsupported", "reason": "No safe semantic mapping"}}

    tree = {"id": page_id + "-root", "kind": "page", "children": []}
    title_area = page.get("titleArea") or {}
    if title_area:
        tree["children"].append({"id": "title-area", "kind": "hero", "props": {"eyebrow": str(title_area.get("textAboveTitle") or ""), "variant": str(title_area.get("layout") or "plain")}, "content": {"text": str(page.get("title") or title_area.get("title") or "Untitled")}, "fidelity": {"status": "approximate", "reason": "Title area layout simplified"}})
    for section_index, section in enumerate(page["canvasLayout"].get("horizontalSections", [])):
        cols = section.get("columns") or []
        total_width = sum(int(c.get("width") or 0) for c in cols)
        if total_width != 12:
            diagnostics.append({"severity": "warning", "code": "INVALID_GRID", "message": f"Section {section_index + 1} uses {total_width} of 12 grid units"})
        section_node = {"id": str(section.get("id") or f"section-{section_index}"), "kind": "section", "order": section_index, "props": {"emphasis": str(section.get("emphasis") or "none")}, "children": []}
        columns = {"id": f"columns-{section_index}", "kind": "columns", "children": []}
        for ci, column in enumerate(cols):
            span = int(column.get("width") or 12)
            column_node = {"id": f"col-{section_index}-{ci}", "kind": "column", "order": ci, "layout": {"widthFraction": min(1, max(1, span) / 12)}, "children": []}
            for pi, part in enumerate(column.get("webparts") or []):
                column_node["children"].append(content_part(part, pi))
            columns["children"].append(column_node)
        section_node["children"].append(columns)
        tree["children"].append(section_node)
    if page["canvasLayout"].get("verticalSection"):
        diagnostics.append({"severity": "warning", "code": "UNSUPPORTED_VERTICAL_SECTION", "message": "Right-side vertical section preserved only as a warning in this PoC"})
    if not page["canvasLayout"].get("horizontalSections"):
        diagnostics.append({"severity": "warning", "code": "NO_HORIZONTAL_SECTIONS", "message": "No horizontal sections available; this does not establish an empty source page"})
    return {"schemaVersion": "0.1.0", "source": {"platform": "sharepoint", "pageModel": "modern", "url": base_url or "https://example.org/unknown", "capturedAt": "2026-10-28T00:00:00Z", "captureMethod": str(page.get("_captureMethod") or "manual-fixture"), "evidenceConfidence": str(page.get("_captureConfidence") or "synthetic")}, "page": {"id": page_id, "title": str(page.get("title") or "Untitled"), "description": str(page.get("description") or "")}, "tree": tree, "assets": assets, "diagnostics": diagnostics, "extensions": {"demo": {"counts": dict(counts), "note": "Adapted public documentation fixture; not a live SharePoint export"}}}


def render_node(node: dict) -> str:
    kind = node["kind"]
    children = "".join(render_node(c) for c in node.get("children", []))
    if kind == "page":
        return children
    marker = f' data-ir-id="{escape(str(node.get("id", "")), quote=True)}"'
    if kind == "hero":
        eyebrow = escape(node.get("props", {}).get("eyebrow", ""))
        return f'<header class="hero"{marker}><div class="wrap"><p class="eyebrow">{eyebrow}</p><h1>{escape(node.get("content", {}).get("text", ""))}</h1></div></header>'
    if kind == "section":
        return f'<section class="section"><div class="wrap">{children}</div></section>'
    if kind == "columns":
        return f'<div class="columns">{children}</div>'
    if kind == "column":
        fraction = float(node.get("layout", {}).get("widthFraction", 1))
        return f'<div class="column" style="--share:{max(0.01,min(1,fraction)):.6f}">{children}</div>'
    if kind == "richText":
        return f'<div class="rich-text"{marker}>{node.get("props", {}).get("safeHtml", "")}</div>'
    if kind == "image":
        c = node.get("content") or {}
        src = escape(node.get("props", {}).get("src", ""), quote=True)
        return f'<figure class="image-card"{marker}><img src="{src}" alt="{escape(c.get("altText", ""), quote=True)}" loading="lazy"><figcaption>{escape(c.get("caption", ""))}</figcaption></figure>'
    if kind == "linkList":
        links = "".join(f'<li><a href="{escape(item["url"],quote=True)}">{escape(item["label"])}</a></li>' for item in node.get("props", {}).get("items", []))
        return f'<nav aria-label="Related resources" class="link-card"{marker}><h2>Helpful links</h2><ul>{links}</ul></nav>'
    if kind == "unknown":
        return f'<aside class="unsupported" role="note"{marker}><strong>Component requires review</strong><p>Unsupported SharePoint web part retained in the migration report.</p></aside>'
    return children


DEMO_CSS = """*{box-sizing:border-box}body{margin:0;background:#f5f7fa;color:#1b2c39;font:16px/1.65 system-ui,-apple-system,Segoe UI,sans-serif} .wrap{max-width:1160px;margin:auto;padding:0 28px}.masthead{background:#fff;border-bottom:1px solid #dae2e9;padding:14px 0}.masthead .wrap{display:flex;align-items:center;justify-content:space-between}.brand{font-weight:760;color:#16456a;font-size:17px}.flag{color:#627688;font-size:13px}.hero{background:linear-gradient(120deg,#0a3d64,#125e7a 70%,#2b818c);color:white;padding:65px 0 72px}.hero h1{font-size:clamp(2.35rem,5vw,4.1rem);line-height:1.1;max-width:850px;margin:10px 0}.eyebrow{text-transform:uppercase;letter-spacing:.19em;font-weight:700;font-size:12px;color:#bce5e0}.section{padding:50px 0}.section:nth-child(odd){background:#fff}.columns{display:flex;gap:30px;align-items:start}.column{flex:calc(var(--share)*12) 1 0;min-width:0}.rich-text h2{font-size:clamp(1.6rem,3vw,2.15rem);line-height:1.3;color:#143d59;margin-top:0}.rich-text a,.link-card a{color:#096a97}.rich-text p{margin:0 0 1em}.rich-text ul{padding-left:1.25em}.image-card{margin:0;background:#fff;border:1px solid #e0e8ee;overflow:hidden;border-radius:15px;box-shadow:0 10px 30px #12365510}.image-card img{display:block;width:100%;height:auto;aspect-ratio:4/3;object-fit:cover;background:#d8eaf2}.image-card figcaption{font-size:13px;padding:11px 16px;color:#526878}.link-card{padding:25px 28px;border:1px solid #e0e8ee;border-radius:15px;background:#fff;box-shadow:0 10px 24px #1b38570c}.link-card h2{font-size:19px;margin:0 0 10px;color:#143d59}.link-card ul{list-style:none;margin:0;padding:0}.link-card li{border-top:1px solid #edf1f5}.link-card a{display:block;padding:10px 0;font-weight:600;text-decoration:none}.link-card a:hover{text-decoration:underline}.unsupported{padding:20px;background:#fff4e1;border-left:4px solid #e49a24;border-radius:6px}.unsupported p{margin:6px 0 0;font-size:13px}.footer{border-top:1px solid #d9e5e9;background:#f6fafb;color:#667989;padding:22px 0;font-size:13px}@media(max-width:750px){.wrap{padding:0 20px}.columns{flex-direction:column;gap:18px}.column{width:100%;flex:none}.hero{padding:48px 0}.section{padding:36px 0}.flag{display:none}}"""


STRUCTURAL_CSS = """*{box-sizing:border-box}body{margin:0;color:#222;background:#fff;font:16px/1.5 sans-serif}.wrap{max-width:1200px;margin:0 auto;padding:0 24px}.hero,.section{padding:24px 0}.hero h1{margin:0}.eyebrow:empty{display:none}.columns{display:flex;align-items:start;gap:20px}.column{flex:calc(var(--share)*12) 1 0;min-width:0}.rich-text{overflow-wrap:anywhere}.rich-text img,.image-card img{max-width:100%;height:auto}.image-card{margin:0}.image-card img{display:block}.image-card figcaption{font-size:.875rem}.link-card ul{padding-left:1.25rem}.unsupported{padding:1rem;border:2px dashed #888}.unsupported p{margin-bottom:0}@media(max-width:720px){.wrap{padding:0 16px}.columns{flex-direction:column}.column{width:100%;flex:none}}"""


def build(source: Path, out: Path, assets_dir: Path | None = None, *, style_mode: str = "structural") -> dict:
    if style_mode not in {"structural", "demo"}:
        raise ValueError("style_mode must be structural or demo")
    doc = json.loads(source.read_text(encoding="utf-8"))
    mappings = doc.pop("_assetMap", {})
    canvas_diagnostics = []
    if isinstance(doc.get("ListItemAllFields"), dict):
        from .canvas import decode_modern_canvas
        doc, canvas_diagnostics = decode_modern_canvas(doc)
    ir = normalize(doc, asset_map=mappings)
    ir["diagnostics"].extend(canvas_diagnostics)
    from .validation import source_to_ir, ir_to_html
    from hashlib import sha256
    source_audit = source_to_ir(doc, ir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "assets").mkdir(exist_ok=True)
    if assets_dir:
        for asset in ir["assets"]:
            dest = asset.get("resolvedUrl", "")
            if dest.startswith("assets/"):
                src_file = (assets_dir / Path(dest).name)
                if not src_file.is_file():
                    raise FileNotFoundError(src_file)
                shutil.copyfile(src_file, out / dest)
    body = render_node(ir["tree"])
    description = escape(ir["page"].get("description", ""), quote=True)
    title = escape(ir["page"]["title"])
    html = (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="description" content="{description}"><title>{title}</title>'
            f'<link rel="stylesheet" href="style.css"></head><body><main>{body}</main></body></html>')
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "style.css").write_text(STRUCTURAL_CSS if style_mode == "structural" else DEMO_CSS, encoding="utf-8")
    ir_text = json.dumps(ir, indent=2) + "\n"
    (out / "page.ir.json").write_text(ir_text, encoding="utf-8")
    counts = Counter()
    def walk(n):
        counts[n["kind"]] += 1
        for child in n.get("children", []):
            walk(child)
    walk(ir["tree"])
    total_webparts = sum(len(col.get("webparts") or []) for section in doc["canvasLayout"].get("horizontalSections", []) for col in section.get("columns") or [])
    supported = sum(counts[k] for k in ("richText", "image", "linkList"))
    report = {"source": str(source), "status": "demo-generated", "styleMode": style_mode, "visualFidelity": "unverified-no-rendered-source-baseline", "webPartsFound": total_webparts, "mappedParts": supported, "unmappedParts": counts["unknown"], "coveragePercent": round(100 * supported / total_webparts, 1) if total_webparts else 100.0, "components": dict(counts), "assets": len(ir["assets"]), "warnings": ir["diagnostics"], "limitations": ["Public documentation-adapted fixture, not an authenticated tenant extraction", "Modern Graph canvas subset only", "Source screenshots/CSS unavailable; generated styling is not a visual replica", "No dynamic behavior migration"]}
    target_audit = ir_to_html(ir, html, {}, out)
    quality = {"version": "1.0", "irSha256": sha256(ir_text.encode("utf-8")).hexdigest(),
               "sourceToIr": source_audit, "irToHtml": target_audit,
               "passed": source_audit["passed"] and target_audit["passed"],
               "visualFidelity": "unverified-no-matched-source-baseline"}
    (out / "quality-report.json").write_text(json.dumps(quality, indent=2) + "\n", encoding="utf-8")
    report["contentAccounting"] = {"passed": quality["passed"],
                                   "sourceSummary": source_audit["summary"], "outputSummary": target_audit["summary"],
                                   "qualityReport": "quality-report.json"}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
