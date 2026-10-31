# Modern Graph normalization hardening — public-contract research and test gate

Status: **implemented in MVP branch (prototype)**. No SharePoint tenant, credentials, or private pages involved.

## Verified public reference contracts

| Resource | Public Microsoft documentation | Source facts | Engine consequence |
|---|---|---|---|
| `sitePage` | https://learn.microsoft.com/en-us/graph/api/resources/sitepage?view=graph-rest-1.0 | `titleArea` + expanded `canvasLayout` | Treat the Graph page object as a typed source; do not confuse it with the serialized `CanvasContent1` format |
| `horizontalSectionColumn` | https://learn.microsoft.com/en-us/graph/api/resources/horizontalsectioncolumn?view=graph-rest-1.0 | Columns are 1–12 units on a 12-grid | Validate exact integer spans; retain both the fraction and original source span |
| `horizontalSection` | https://learn.microsoft.com/en-us/graph/api/resources/horizontalsection?view=graph-rest-1.0 | Section `layout`, `emphasis` and column relationships | Preserve the source layout and emphasis separately from output CSS |
| `verticalSection` | https://learn.microsoft.com/en-us/graph/api/resources/verticalsection?view=graph-rest-1.0 | It has its own ordered `webparts` | **Never silently drop these controls**; represent a generic sidebar section and mark layout approximation |
| `titleArea` | https://learn.microsoft.com/en-us/graph/api/resources/titlearea?view=graph-rest-1.0 | Image URL/alt, layout, text alignment, gradient flag, author/date visibility | Keep authored properties and an asset record; only render what is supported; don't invent author/date content |
| `standardWebPart` | https://learn.microsoft.com/en-us/graph/api/resources/standardwebpart?view=graph-rest-1.0 | `containerTextWebPartId` links an inline part to a text part | Retain the parent relationship in source provenance and emit a placement warning |
| `webPartData` | https://learn.microsoft.com/en-us/graph/api/resources/webpartdata?view=graph-rest-1.0 | Part properties and server-processed content carry source fields | Keep known image metadata and server-processed links; do not infer behavior from unknown JavaScript |

## Implemented and tested

- Expanded Modern Graph sections no longer discard a vertical section's web parts. The generic CIR captures sidebar placement semantics; both target generators render the preserved content. Source-style placement is **not** claimed faithful.
- Title areas carry the authored `imageWebUrl`, `alternativeText`, layout variant, alignment, gradient setting and author/date flags. A false `showTextBlockAboveTitle` suppresses the visible eyebrow while retaining the raw authored string as provenance. Rendered hero images are validated as output assets, but original cropping/gradients/typography are **not** verified.
- Horizontal columns keep `breakpointHints.sourceGridSpan` and `widthFraction`; malformed spans fail closed rather than being clamped invisibly. Section `sourceLayout` and emphasis remain available for a destination-specific mapping.
- `containerTextWebPartId` is preserved in a source reference and reported as requiring in-text placement review. Unknown inline components are **not** fabricated as successful mappings.
- Unexpanded `webparts` relationships produce an explicit `WEBPART_RELATIONSHIP_NOT_EXPANDED` warning and a source-accounting `needs-review` entry. Duplicate source web-part IDs produce an **error** diagnostic.
- A self-closing rejected script element no longer suppresses subsequent legitimate HTML text in the compact sanitizer. This is a regression fix, **not** a claim of a production-grade HTML security sanitizer.
- Added the reproducible `poc/samples/modern-rich-layout-public-adapted.json` fixture. It is an **original, documentation-adapted example**, not an actual tenant export. Existing public PnP `CanvasContent1` fixture remains available and separately labeled.

## No overclaiming

The supported-content checks are stricter now. They do not establish pixel-level similarity, complete SharePoint webpart support, interaction equivalence, faithful sidebar placement or source-authentic CSS. MVP release decision remains **review-required** (or **blocked** on detected loss/error).

## Next quality gates

1. Validate the IR against a versioned machine-checkable schema, with deterministic node IDs and explicit preservation of source ordering.
2. Use a proven HTML parser/sanitizer design instead of the current demonstration-only allow-list, including security-focused fuzz tests.
3. Improve embedded and nested media/control extraction without losing authored text, links, tables or accessible semantics.
4. Capture *matching* public source/rendered CSS/screenshot evidence when possible; compare output at desktop/mobile viewports.
5. Build destination control mapping coverage fixtures that include typography, breakpoints, title area and sidebar behavior; keep source and target metrics separate.

Do not start classic or publishing readers until these Modern-page gates are sufficiently mature.
