# ADR 002 — Page-family routing, evidence and secure source capture

Status: proposed research contract, 2026-10-28.

## Two independent classification axes

**Deployment:** SharePoint Online, SharePoint Server with a confirmed version, or unknown. Determines transport/auth capabilities. **Page family:** modern sitePage, classic wiki, classic webpart, classic publishing, other, unknown. Determines how parts/fields/layout are interpreted.

One site can mix page families; do not make adapter selection a per-domain static setting.

## Evidence priority

1. Authenticated source API: typed Graph sitePage with canvas or corresponding SharePoint data model.
2. Validated Microsoft 365 Assessment Tool PageType (only after verifying scan coverage for SharePoint Online classic pages).
3. Authenticated field/template signatures: publishing layout/content fields, wiki content, classic zones, client-side page markers. Requires cross-check.
4. Rendered DOM / server headers / stylesheets: appearance/platform clues only; page-family classification unresolved.
5. URL-only: a SitePages/Pages path or .aspx extension is never decisive.

If two trusted signals disagree, return NEEDS_REVIEW with both evidence items; do not silently choose one. A public rendered page without source records is UNKNOWN and may be **explicitly** processed using the low-confidence public-dom fallback.

## Proposed decision table

| Graph typed modern canvas | Assessment PageType | Verified SharePoint source fields | Action |
|---|---|---|---|
| yes | none | no contradiction | modern adapter |
| yes | WikiPage / WebPartPage / PublishingPage | any | needs-review (conflicting evidence) |
| no | WikiPage | compatible | classic-wiki adapter |
| no | WebPartPage | compatible | classic-webpart adapter |
| no | PublishingPage | compatible | classic-publishing adapter |
| no | none | publishing layout/content type evidence | classic-publishing tentative + review |
| no | none | wiki content evidence | classic-wiki tentative + review |
| no | none | zone manager evidence | classic-webpart tentative + review |
| no | none | public DOM only | unknown; optional snapshot fallback |

A blank CanvasContent1 on an uncustomized modern home page is an expected special case (PnP docs), not proof of empty content.

## Proposed adapter interface (conceptual)

- probe(siteContext, pageRef) -> DetectionEvidence[]
- capture(authorizedReadOnlyContext, pageRef) -> SourceCapture
- parse(SourceCapture) -> SourceNodeTree
- normalize(SourceNodeTree, context) -> CIR
- inspectDependencies(SourceCapture) -> DependencyManifest

Transport adapters for Graph, CSOM/REST and on-prem may be reused by multiple page-family readers. Target renderers must never need a SharePoint API client.

## SourceCapture vs CIR vs VisualEvidence

**SourceCapture** is the restricted/lossless research evidence bundle: origin, version, adapter ID, original API payload/field snapshots, template/stylesheet/asset references, retrieval timestamp, part order and diagnostics. Sensitive paths or data should remain in secured storage, not in committed repository files.

**CIR** is the cleaned and portable semantic/layout tree with source references, design tokens, asset links and explicit fidelity outcomes.

**VisualEvidence** contains permitted rendered screenshots, DOM and computed style observations at defined viewports. It validates source appearance but cannot identify hidden authoring properties reliably.

Example conceptual metadata envelope (not an implemented schema):

    captureVersion: 0.1.0
    origin: { deployment, siteId, pageId, url }
    route: { pageFamily, adapter, evidence[] }
    retrievedAt: ISO-8601
    rawRefs: [path-to-secure-api-json, path-to-permitted-html]
    dependencies: [list, library, termStore, asset, externalService]
    diagnostics: [missing-part, inaccessible-style, ambiguous-detection]

## Required safety and fidelity

- Discover/read only authorized material; no authentication bypass or secret extraction.
- Preserve unknown parts with ID/type/order, sourceRef and unsupported reason.
- Preserve dynamic list/search/user context as explicit dependencies, never substitute a timeless static snapshot silently.
- Normalized HTML must be sanitized; preserve links/alt/table semantics.
- Detect missing/broken assets and unresolved internal links.
- Track page publication state and access boundaries before publishing output.
- Capture should be idempotent and traceable using source IDs plus stable paths.

## Test cases before production adapter coding

- Modern, Wiki, WebPart, Publishing signals each route correctly.
- Conflicting high-confidence signals never choose a wrong adapter.
- Bare .aspx returns unknown.
- Graph modern unmodified Home.aspx does not become an empty migrated page without visual/source verification.
- Missing permission or failed inventory is not reported as zero parts.
- Two pages from the same site can use distinct adapters and share one site-theme/layout catalog.

References:
- https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/assessment-tool-classic-pages
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/assessment-tool-classic-pages-requirements
- https://pnp.github.io/powershell/cmdlets/Get-PnPPage.html
