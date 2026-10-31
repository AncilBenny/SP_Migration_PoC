# MVP engine research and quality gates — SharePoint-based migration

**Status:** Engineering baseline / requirements, not a certification of production-readiness. Research checked against Microsoft Learn and PnP public guidance on 2026-10-29. MVP source scope remains **Modern SharePoint**; later source families are researched but NOT implemented in parallel. No authentication, tenant access, or SharePoint plugin.

## Product positioning

A source-independent **canonical page IR** is the durable core. It describes authored content, hierarchy, layout, styles, assets, behavior, identity, and provenance without committing to any destination implementation. From the same IR, migration may (1) closely preserve the source website's look and interactions, or (2) translate into a distinct client design system or CMS. Output is clean HTML/CSS and necessary JavaScript, optionally a client component mapping. No implicit design changes and no silent content loss.

**Quality stance:** "industry-beating" is an aspiration to test against objective evidence, not a claim supported by a 32-test synthetic PoC. We should continuously compare against Microsoft Graph semantics, PnP transformation models, Microsoft 365 Assessment outputs, and real public fixtures. Product labels must reflect actual maturity and unverified visual/behavior fidelity.

## SharePoint engineering evidence (primary references)

| Engine | Reference | Confirmed implication | Engineering requirement |
|---|---|---|---|
| Source capture | Microsoft Graph `sitePage` GET (`?$expand=canvasLayout`) — https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0 | Page content resides in an expanded canvas; API requires authorized access for live tenant pages | Version Graph-shaped intake, detect missing expansion, preserve original capture and API provenance; public fixture tests until auth available |
| Layout | Graph `horizontalSectionColumn` — https://learn.microsoft.com/en-us/graph/api/resources/horizontalsectioncolumn?view=graph-rest-1.0 | Modern horizontal section width spans a 12-unit grid | Stable reading order, span preservation and explicit unsupported placement diagnostics; don't silently coerce malformed grids |
| Title/media | Graph `titleArea` — https://learn.microsoft.com/en-us/graph/api/resources/titlearea?view=graph-rest-1.0 | Title blocks can include image URL, alternative text, layout/gradient and author/published-date preferences | Must model those visual/semantic settings or emit an explicit parity warning; current PoC simplifies these |
| Webpart content | Graph `webPart` endpoints — https://learn.microsoft.com/en-us/graph/api/webpart-list?view=graph-rest-1.0 | Parts can be accessed by ID, section and column | Part identity and original location are critical traceability fields; identity must survive IR normalization |
| Modern SPFx data | SharePoint SPFx property metadata — https://learn.microsoft.com/en-us/sharepoint/dev/spfx/web-parts/guidance/integrate-web-part-properties-with-sharepoint | `isHtmlString`, `isImageSource` and `isLink` instruct SharePoint processing and link fixup | Decoder must distinguish HTML, link and image references, not stringify all `properties` or execute custom JS; verify `serverProcessedContent` |
| PnP actual source | PnP CLI public page fixture (MIT) — https://github.com/pnp/cli-microsoft365/blob/main/src/m365/spo/commands/page/page-get.mock.ts | Public modern `CanvasContent1` includes encoded canvas-control metadata, different from Graph `canvasLayout` JSON | Keep a separate tested source adapter; detect unknown/custom webparts and missing metadata without crashing or loss |
| Mapping model | Microsoft PnP page transformation — https://learn.microsoft.com/en-us/sharepoint/dev/transform/modernize-userinterface-site-pages ; https://pnp.github.io/pnpframework/using-the-framework/pnp-modernization/getting-started.html | Mapping/transform steps are configuration-driven and require per-page validation; PnP source-to-modern destinations are SharePoint-specific | Our target mappings must consume IR, not raw SharePoint. Configurations must be validated, versioned, deterministic and auditable |
| Assessment | Microsoft 365 classic-page assessment — https://learn.microsoft.com/en-us/sharepoint/dev/transform/assessment-tool-classic-pages | Assessment `MappingPercentage` is not proof of successful transformation or content parity | Distinguish support coverage, semantic preservation, destination mapping, and actual visual/behavior fidelity scores |
| Classic future | SharePoint page processing model — https://learn.microsoft.com/en-us/sharepoint/dev/solution-guidance/sharepoint-pages-and-the-page-model | Master pages, page layouts, fields and webparts compose a classic page | Future classic adapters need their own capture contracts; DO NOT flatten publishing layout into rich text |
| Classic future | Microsoft publishing transition — https://learn.microsoft.com/en-us/sharepoint/publishing-sites-classic-to-modern-experience | Classic/master page styling and component structure does not map 1-to-1 to modern pages | Evaluate publishing separately, after Modern source quality gates |

## Engine contracts and non-negotiable quality gates

### 1. Input/source intelligence
- Recognize the source **by evidence**, not `.aspx` suffix or page appearance.
- Preserve and distinguish Graph `canvasLayout`, serialized `CanvasContent1`, and source provenance.
- Never fetch or parse unauthorized private pages. Inputs in this MVP are uploaded local JSON and public fixtures.
- Bound input bytes, nested depth, and total elements; reject malformed types without crashing local server.
- Golden fixtures: official Graph page examples, MIT-licensed PnP serialized canvas, synthetic edge cases; no fabricated production tenant export.

### 2. Semantic cleanup and canonical IR
- Preserve source order, IDs, headings, paragraphs, tables, images, links, typography-impacting layout settings and component boundaries.
- Remove SharePoint wrappers only after proving their semantics/appearance can be represented in CIR.
- Source references and evidence confidence attached to normalized nodes, with exact/approximate/unknown states.
- Version a JSON Schema and migration policy. Validate against shape, invariants and malicious input; add property-based and differential tests.
- IR must not depend on target CSS classes, React components, or specific client branding.

### 3. Target mapping intelligence
- One CIR, multiple explicit target profiles; default faithful migration is **not** required when the client expects a different site.
- Safe configurable URL and asset rewrites; record every changed/unresolved URL and artifact.
- Mapping profile keys, styles and controls are allow-listed. Avoid arbitrary executable templates or script injection.
- Unknown source webparts are visible as `needs-review`, never counted as migrated successfully.
- Preserve IR bytes between outputs; mapping should be deterministic and reversible where appropriate.

### 4. Fidelity and verification
- Independent inventories across source → IR → output for text, heading hierarchy, links, images, controls, layout and important metadata; failure injection tests are mandatory.
- A passing **supported-content** check is not the same as migration approval. If unknowns or unverified crucial assets remain, mark **review required**.
- For same-design migration: matched source/output browser captures at desktop and mobile sizes; compare typography, colors, spacing, geometry, responsive flow and supported interactions. Until matched samples exist, `visualFidelity` MUST remain `unverified`.
- For client-design migration: check component contracts, content retention, link/asset integrity, accessibility and destination style expectations instead of measuring pixel similarity with SharePoint.
- Track sampling coverage, supported behavior, known limitations, false-positive tests, and severity-specific release gates.

### 5. Reliability, security and accessibility
- Strict bounded inputs and errors, no external URL fetching in local MVP, no arbitrary source JavaScript execution, CSP/sandboxed previews, no upload to cloud.
- Unit, integration and HTTP/API tests (including corrupted source, malicious HTML and export path handling), repeatable CI on Windows and Linux.
- Before production: HTML sanitizer audited/standards-based, threat model, independent security review, accessible/semantic output checks (WCAG 2.2 AA target), performance/load benchmarking and regression on real permitted test pages.
- No production deployment until CI is green and all P0 and P1 failures are resolved. Current GitHub-hosted failures are an unresolved gate, even if local Python tests pass.

## MVP evidence labels (implemented vs planned)

| Engine area | Current maturity | Next exit criteria |
|---|---|---|
| Modern Graph source adapter | `prototype` | Official + PnP fixtures, malformed/unknown variants, high source coverage, cross-format differential fixtures |
| CanvasContent1 adapter | `prototype` | Bounded parser, more encoded metadata varieties, inline components, nested layout, unknown error accounting |
| Generic CIR | `research-draft` / `prototype` | Published schema v1, provenance/behavior/styles contracts, structural validation |
| Target mapping & URL/asset rewrite | `prototype` | Client component registry, compatibility checks, deterministic multi-profile tests, real asset resolution strategy |
| Rich HTML cleanup | `experimental` | Proven semantics-preserving transformations, security-audited sanitizer, nested tables/lists/inline content |
| Content validation | `prototype` | Source/IR/output completeness gates + property/integration tests + rendering checks |
| Visual + interaction fidelity | `not-verified` | Matched source + destination screenshots and interaction tests; no synthetic accuracy claims |
| Local Migration Studio UI | `MVP scaffold` | Integration/API smoke tests, user import/preview/export workflow, accessibility review |

## Development cadence

1. **Now:** create local-only MVP shell around proven PoC, expose evidence-aware capability labels and conservative release decisions. Test browser API and export.
2. **Then:** consolidate source parser contracts, strengthen schema validation, add more official Graph and PnP real-format fixtures, implement missing layout/title/content variants.
3. **Then:** grow target mapping rules and make user-configured source-to-target controls reviewable; inspect CSS/HTML/JS output structure and improve accessibility.
4. **Then:** matched visual verification and deterministic batch flows on approved sources. Do not claim an industry advantage before measured comparisons.

## Explicit limitations of our public-only approach

Public `cdph.ca.gov` style websites can supply an output design/visual reference when accessible; **they do not prove their backend is SharePoint**. Public SharePoint Online modern authoring response is typically not anonymously available. There is no authenticated tenant access. A complete original-vs-migrated SharePoint visual comparison requires a matched authorized sample or a genuinely public bundled authoring + rendered baseline. No plugins are required for the current public-fixture MVP.
