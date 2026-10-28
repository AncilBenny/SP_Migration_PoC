"""Offline parser for public Modern SharePoint CanvasContent1 list-item fixtures.

Parses HTML-entity-encoded, JSON-bearing SharePoint canvas control attributes.
It does not evaluate JavaScript, load network content or claim full canvas fidelity.
This decoder is a source adapter; the generic CIR remains destination-agnostic.
"""
from __future__ import annotations

from collections import OrderedDict
from html import escape, unescape
from html.parser import HTMLParser
import json
from typing import Any

from .engine import IMAGE_ID, QUICKLINKS_ID

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def _json_attr(value: str, name: str) -> dict[str, Any]:
    """Parse SharePoint's HTML entity encoded JSON attribute, never execute it."""
    try:
        result = json.loads(unescape(value))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid {name} JSON in SharePoint canvas") from exc
    if not isinstance(result, dict):
        raise ValueError(f"Expected object in {name}")
    return result


class CanvasParser(HTMLParser):
    """Extract controls and attached webPartData from nested canvas HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.active: list[tuple[int, dict]] = []
        self.controls: list[dict] = []
        self.rte_depth: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs)
        if "data-sp-controldata" in attrs:
            ctrl = {"control": _json_attr(attrs["data-sp-controldata"], "data-sp-controldata"),
                    "webpart": None, "rte": [], "sourceIndex": len(self.controls)}
            self.controls.append(ctrl)
            self.active.append((self.depth, ctrl))
        if self.active:
            ctrl = self.active[-1][1]
            if "data-sp-webpartdata" in attrs:
                ctrl["webpart"] = _json_attr(attrs["data-sp-webpartdata"], "data-sp-webpartdata")
            if "data-sp-rte" in attrs or "data-sp-rte-paragraph" in attrs:
                self.rte_depth = self.depth
            if self.rte_depth is not None and self.depth > self.rte_depth and tag not in {"script", "style"}:
                supported = {"p", "a", "strong", "em", "b", "i", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "table", "tr", "td", "th"}
                if tag in supported:
                    href = f' href="{escape(str(attrs["href"]), quote=True)}"' if tag == "a" and attrs.get("href") else ""
                    ctrl["rte"].append(f"<{tag}{href}>")
        if tag not in VOID_TAGS:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag not in VOID_TAGS:
            self.depth = max(0, self.depth - 1)
        if self.active and self.rte_depth is not None and self.depth > self.rte_depth:
            if tag in {"p", "a", "strong", "em", "b", "i", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr", "td", "th"}:
                self.active[-1][1]["rte"].append(f"</{tag}>")
        if self.rte_depth is not None and self.depth <= self.rte_depth:
            self.rte_depth = None
        while self.active and self.depth <= self.active[-1][0]:
            self.active.pop()

    def handle_data(self, data: str) -> None:
        if self.active and self.rte_depth is not None:
            self.active[-1][1]["rte"].append(escape(data))


def decode_modern_canvas(source: dict) -> tuple[dict, list[dict]]:
    """Decode a Modern SharePoint REST/PnP list-item public fixture to a Graph-like canvas.

    Returns page source and loss-accounting diagnostics. Output can be passed to
    the SAME generic normalize() as Graph input. Only known control positions
    and supported standard web parts are translated; all others remain unknown.
    """
    if not isinstance(source, dict):
        raise ValueError("Expected modern SharePoint page fixture object")
    fields = source.get("ListItemAllFields")
    if not isinstance(fields, dict) or not isinstance(fields.get("CanvasContent1"), str):
        raise ValueError("Expected ListItemAllFields.CanvasContent1 as string")
    if not fields.get("ClientSideApplicationId") and not fields.get("PageLayoutType"):
        raise ValueError("Modern page evidence missing: ClientSideApplicationId/PageLayoutType")
    if len(fields["CanvasContent1"]) > 5_000_000:
        raise ValueError("CanvasContent1 exceeds offline fixture limit")

    parser = CanvasParser()
    parser.feed(fields["CanvasContent1"])
    parser.close()
    sections: OrderedDict[int, OrderedDict[int, list[dict]]] = OrderedDict()
    widths: dict[tuple[int, int], int] = {}
    diagnostics: list[dict] = []
    for item in parser.controls:
        ctrl, wp = item["control"], item["webpart"]
        if "pageSettingsSlice" in ctrl:
            continue
        pos = ctrl.get("position") or {}
        try:
            sec, zone, span = int(pos.get("sectionIndex", 1)), int(pos.get("zoneIndex", 1)), int(pos.get("sectionFactor", 12))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid SharePoint canvas layout coordinates") from exc
        if not 1 <= span <= 12 or sec < 0 or zone < 0:
            raise ValueError("Invalid SharePoint canvas grid span/position")
        section = sections.setdefault(sec, OrderedDict())
        parts = section.setdefault(zone, [])
        widths[(sec, zone)] = span
        part_id = str(ctrl.get("id") or (wp or {}).get("id") or f"canvas-{item['sourceIndex']}")
        source_path = f"ListItemAllFields.CanvasContent1/control[{item['sourceIndex']}]"
        if wp:
            webpart_type = str(ctrl.get("webPartId") or wp.get("id") or "").lower()
            if webpart_type in {IMAGE_ID, QUICKLINKS_ID}:
                part = {"@odata.type": "#microsoft.graph.standardWebPart", "id": part_id,
                        "webPartType": webpart_type,
                        "data": {"properties": wp.get("properties") or {},
                                 "serverProcessedContent": wp.get("serverProcessedContent") or {},
                                 "dataVersion": wp.get("dataVersion")},
                        "_capturePointer": source_path}
            else:
                part = {"@odata.type": "#microsoft.graph.standardWebPart", "id": part_id,
                        "webPartType": webpart_type or "unrecognized", "data": {"properties": {}},
                        "_capturePointer": source_path}
                diagnostics.append({"severity": "warning", "code": "CANVAS_UNRECOGNIZED_PART", "nodeId": part_id,
                                    "sourcePath": source_path,
                                    "message": "Custom/unrecognized CanvasContent1 part retained as unknown"})
        elif ctrl.get("controlType") == 4 and item["rte"]:
            part = {"@odata.type": "#microsoft.graph.textWebPart", "id": part_id,
                    "innerHtml": "".join(item["rte"]), "_capturePointer": source_path}
        else:
            part = {"@odata.type": "#microsoft.graph.standardWebPart", "id": part_id,
                    "webPartType": "unknown-canvas-control", "data": {"properties": {}},
                    "_capturePointer": source_path}
            diagnostics.append({"severity": "warning", "code": "CANVAS_UNRECOGNIZED_CONTROL", "nodeId": part_id,
                                "sourcePath": source_path, "message": "Canvas control could not be safely decoded"})
        parts.append((int(pos.get("controlIndex") or len(parts)), part))

    graph_sections = []
    for sec, zone_map in sections.items():
        columns = [{"id": str(zone), "width": widths[(sec, zone)],
                    "webparts": [p for _, p in sorted(parts, key=lambda x: x[0])]}
                   for zone, parts in sorted(zone_map.items())]
        graph_sections.append({"id": f"canvas-section-{sec}", "columns": columns})
    title = str(fields.get("Title") or source.get("Title") or "Untitled")
    result = {"@odata.type": "#microsoft.graph.sitePage",
              "id": str(source.get("id") or fields.get("Id") or "public-canvas-fixture"),
              "webUrl": str(source.get("webUrl") or "https://example.org/unknown"),
              "title": title, "description": str(fields.get("Description") or ""),
              "titleArea": {"layout": "plain", "title": title},
              "canvasLayout": {"horizontalSections": graph_sections},
              "_captureMethod": "pnp",
              "_captureConfidence": "synthetic" if source.get("_provenance", {}).get("kind") != "verified-tenant" else "api"}
    return result, diagnostics
