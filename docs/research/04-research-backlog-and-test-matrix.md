# Research 04 — Execution backlog, site sampling, and acceptance

> **MVP scope revision (2026-10-28):** Focus only on (1) Modern Site Pages, (2) grouped Classic Wiki/Web Part Pages and (3) Classic Publishing/Website Pages. See [the authoritative scope decision](09-mvp-scope-three-page-families.md). Broader items below (on-prem versions, unusual custom parts, multilingual/complex data) are optional research references, **not implementation commitments**.

Status: research plan v0.1; no authenticated tenant export performed.

## Research work packages

| ID | Question | Method | Evidence artifact | Exit condition |
|---|---|---|---|---|
| R1 | Which page families are present? | Compare Graph page list, classic page library metadata, URLs and templates | Inventory CSV / JSON + classification notes | Each representative page classified with confidence |
| R2 | What web parts and controls exist? | Export modern canvas, classic web-part definitions and custom fields | Page capture bundle, web-part signature catalog | Part list, order and configs mapped or unknown |
| R3 | Where is actual content stored? | Compare API fields / web parts to rendered page | Field-to-DOM traceability matrix | User-visible text/media accounted for |
| R4 | Which layouts/styles are shared? | Compare 3+ pages, templates, CSS links, screenshots and computed styles | Site shell and design token draft | Global / template / per-page ownership noted |
| R5 | What controls are reusable? | Cluster patterns and test CIR mapping | Candidate component catalog | Reusable types supported by evidence |
| R6 | What content depends on SharePoint services? | Trace list, library, search, people and workflow web parts | Dependency inventory | Static vs dynamic vs unsupported clear |
| R7 | How do we validate? | Text/link/asset/a11y checks and screenshot comparisons | Baselines and quality report | Failures detectable and reproducible |
| R8 | Can different outputs consume one CIR? | Build two simple renderers (later phase) | Two renders from one fixture | No source-specific branching in renderer |

## Page sampling matrix

For a real SharePoint tenant:
- Modern informational page: text, image, quick links, section/columns.
- Modern dynamic page: list/library, highlighted content, custom SPFx if available.
- Classic wiki or web-part page: mixed HTML and at least two web parts.
- Classic publishing page: custom page layout and sitewide master theme.
- Edge cases: document embed, table, accordion/tab if present, video, nested layouts, multilingual page, large content, broken asset and an unsupported control.

For CDPH public observation (access pending): program landing page, health information page, department/organization page. These offer visible content archetypes, **not confirmed source page family classification**.

## Minimal authorized sample bundle request

Request *read-only* access to one representative SharePoint Online site **or** a redacted export containing:
1. For modern: Graph sitePage GET JSON including canvasLayout, plus referenced files or metadata where authorized.
2. For classic: page item fields, relevant master/page-layout references, zone/web-part configuration and permitted CSS/assets.
3. For both: source URLs, page type, sample screenshots, linked asset paths, and a business-owner-approved content baseline.

Use a dedicated tenant app / delegated identity with least privilege. SharePoint data never needs to be placed in a public GitHub repository. Samples can be anonymized/redacted before fixture creation.

## Decisions made now

- Research **both** modern and classic; CDPH may be a classic publishing case, but this needs proof.
- Source adapters must be independent of output adapters.
- Keep an evidence-based CIR and a separate raw capture bundle.
- Preserve unknown blocks and expose diagnostics.
- Study CSS and layout as a site-level system, not per-page CSS copy.
- Avoid production extraction until source types and security requirements are verified.

## Explicitly out of scope in Phase 1

No deployment, authenticated tenant scraping, privileged API access, bulk migration, production UI, automated CSS extraction, React renderer, or real CDPH source export.

## Priority next steps

P0. Obtain one authorized sample export (modern or classic) and a representative rendered screenshot.

P0. Confirm one authorized SharePoint Online example each for Modern, Classic Content (Wiki/Web Part), and Publishing. On-premises editions are deferred.

P1. Implement safe capture bundle and inspect parts/types/assets/links on 3 sample pages.

P1. Refine CIR against real exports, document lossy mapping, test schema and validate a simple output.

P2. Build common style-token/layout extraction and accessibility/visual QA; **dynamic list/search reimplementation is deferred**, but dependencies must be flagged.

## Required correctness checks

- Source text/heading/link/asset inventory with corresponding normalized node or explicit exclusion.
- Stable order, layout and hierarchy; shared chrome not duplicated into page body.
- Explicit confidence + diagnostics for guessed/missing mappings.
- No credentials, personal/private information or executable arbitrary script in CIR.
- Repeatable fixtures, schema validation, and deterministic transformations.

## Core references

Microsoft Graph GET sitePage:
https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0

Microsoft assessment for classic pages:
https://learn.microsoft.com/en-us/sharepoint/dev/transform/assessment-tool-classic-pages

Microsoft page models:
https://learn.microsoft.com/en-us/sharepoint/dev/solution-guidance/sharepoint-pages-and-the-page-model

Microsoft PnP page transformation:
https://learn.microsoft.com/en-us/sharepoint/dev/transform/modernize-userinterface-site-pages
