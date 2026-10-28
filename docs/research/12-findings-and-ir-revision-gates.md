# Research 12 — Findings, intermediate-model gaps and next evidence gate

Date: 2026-10-28. This is the latest summary for the three-family MVP. Real source export tests are still pending.

## Findings that change our design

1. **Modern = authored grid + separate title area.** Column width is a span of a 12-unit grid, not pixels. The title area may have its own image, alignment, byline/publishing-date presentation and must not be blindly concatenated to body text.
2. **Inline modern parts exist.** Graph standardWebPart.containerTextWebPartId can indicate a standard part embedded in a rich text part. Preserve parent/inline ordering, avoid duplicate rendering.
3. **Modern data is versioned and distributed.** A webpart may have properties, dataVersion and serverProcessedContent with imageSources/links/htmlStrings/searchablePlainTexts. Never parse only data.properties.
4. **Classic Wiki and Web Part pages can share a capture stack but have different authoring semantics.** WikiField is HTML with embedded parts; a zoned web-part page is primarily zones, ordered definitions and type-specific properties.
5. **Publishing is template-bound.** Shared master/site shell, reusable page-layout fields and per-page content must be separated. The old PnP publishing transformation model provides field->slot/metadata/part mapping examples.
6. **Classic CSS is not a portable runtime dependency.** Master Page Gallery, Style Library, corev15.css and custom URLs are evidence of original appearance. Modern SharePoint branding differs. Extract measured design tokens rather than relying on CSS class names.
7. **Web-part behavior is not always static content.** Unknown custom or list-backed elements require dependency reports and explicit unsupported blocks in this MVP.

## CIR v0.1 gaps discovered — proposed next revision (NOT YET IMPLEMENTED)

| Gap | Why it matters | Proposed future field/contract | Gate before updating schema |
|---|---|---|---|
| site shell reuse | Publishing pages share nav/footer/master | page.siteShellRef and siteShell registry | Two approved publishing pages share a template |
| template reference | Page-level layout is reusable | page.templateRef and reusable layout registry | Actual page-layout source inspected |
| title area ownership | Modern title-area must not duplicate body heading | page.titleArea or typed hero relation | One real Graph sitePage with rendered comparison |
| inline rich-text components | standardWebPart may be inline | inline node anchors + parent part ID | Real inline standardWebPart example |
| width evidence | Graph width spans 12-unit grid | normalized fraction plus capture's native span | Verify real 2- and 3-column pages |
| URL mapping | External/internal links and assets need rewrite | asset manifest + link rewrite mapping | Actual public and tenant URLs tested |
| behavior fallback | dynamicCollection requires source connection | dependency manifest + downgrade mode | One source list-bound part examined |
| template/visual evidence | computed CSS differs from source part model | VisualEvidence bundle separate from CIR | Authorized stylesheet/screenshot samples collected |

Do not make all these speculative fields mandatory in the schema prematurely. Evolve v0.1 based on validated source fixtures and design review.

## Traceability research samples

See examples/research/three-family-traceability.synthetic.json:
- One Modern page with titleArea, 8+4 columns, text and documented Image webpart-style property locations.
- One Classic Wiki page with HTML field and embedded part reference.
- One Classic zoned Web Part Page with a custom unknown part.
- One Publishing page with shared master/layout and field-to-slot mapping.

The sample dataset has **four synthetic scenarios** across **three top-level families**, **15 expected source-to-CIR mappings** and **three explicit diagnostics**. Its fields/content are synthetic and it is NOT evidence that a CDPH or tenant page was migrated. An offline test checks fixture assumptions; no extraction engine currently consumes the cases.

## Validation required before implementation approval

- Real modern Graph page: consistent source ID/order, 12-grid fractions, title ownership, image URL and alt.
- Real classic content page: WikiField or zone ordering, embedded part positions and source properties.
- Real publishing page: page layout, master, fields and header/footer deduplication.
- CSS/HTML snapshots: compare source authoring structure to rendered desktop/mobile, links and assets.
- Fail closed on unsupported components, unresolved links, missing assets or ambiguous page type.
- All source exports authorized, stored securely, and redacted before fixtures are committed.

## Technical research reference links

- https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/resources/horizontalsectioncolumn?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/resources/standardwebpart?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/webpart-list?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/modernize-userinterface-site-pages-model-publishing
- https://learn.microsoft.com/en-us/sharepoint/dev/solution-guidance/use-css-to-brand-pages

## CI limitation

The GitHub workflow for the offline classifier/fixture checks has reported failures on research commits, but the GitHub job-log retrieval endpoint returned a missing-log 404 for the latest investigated job. The cause has **not** been established from available logs. Do not state CI is passing until a successful run is observed. Code and documentation research can be reviewed independently; repairing CI is the next engineering hygiene task.
