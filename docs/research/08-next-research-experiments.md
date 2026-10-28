# Research 08 — Practical experiments and authorized input request

Date: 2026-10-28. Follow-up to 05–07 and ADR 002. Research remains incomplete until actual source evidence is compared with rendered output.

## Priority experiment E1 — Modern Graph

Authorized read-only SharePoint Online site with a modern text + image + Quick Links page. Record Graph sitePage GET with expanded canvas, page metadata, titleArea, ordered part IDs, dependencies, and one desktop/mobile screenshot. Export in restricted storage; redact prior to fixtures. Compare source canvas ordering and content with rendered visible page. Expected result: proposed CIR nodes with provenance and loss reports. Verify blank homepage special case separately.

Graph docs: https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0

## E2 — Classic Wiki

An authorized classic WikiPage with text plus embedded web parts. Gather a verified Assessment PageType (SharePoint Online only), WikiField, layout, embedded part inventory and rendered page. Compare text order, embedded part location and media. Expected result: wiki text + embedded parts represented without dropping either.

## E3 — Classic Web Part Page

An authorized WebPartPage with multiple zones, hidden/closed part state and one list-bound webpart. Gather zone IDs, ordered definitions, type/serialized properties and a rendered screenshot. Expected result: layout/parts mapping preserves original order; dynamic list query marked as dependency.

## E4 — Publishing

An authorized PublishingPage plus master page, page-layout definition, content-type fields, assets and 2 pages sharing the layout. Expected: one shared shell/template descriptor and two separate authored body trees with traceable field-control placement.

## E5 — Layout / CSS

Using 3 representative pages from the same authorized site, collect stylesheet order, key computed styles and 3 viewport screenshots. Separate global chrome from page-specific components. Produce candidate token values backed by actual observed evidence. No exact CDPH CSS conclusions yet.

## E6 — Dynamic/custom

Choose one custom SPFx part or classic custom part and one list library part. Inventory type GUID/class, serialized properties, dependencies, audience/personalization, how frequently output updates, snapshot timestamp. Expected: explicit reimplementation contract or unsupported node; no blind script execution.

## Authorized data request (minimum)

- Source page URLs and page family, if known.
- Read-only Graph sitePage JSON export for one modern page (including canvasLayout).
- SharePoint classic Assessment CSV for one wiki, webpart and publishing page if available; optionally webpart properties in **redacted** form.
- Layout/master references and field data for a publishing example.
- Permitted desktop and mobile screenshots, stylesheet file paths and image references.
- Any custom webpart source or property schema (if organization permits sharing), otherwise just redacted type/property metadata.
- Approval for access/storage and desired redaction rules. Do NOT include passwords, auth tokens, certificates or confidential user data.

An authorized export is **not needed** to review the current architecture and offline classifier, but it is needed to claim that real source content can be migrated.

## Test readiness / risk gate

- Coverage: no source part/field omitted without a diagnostic.
- Layout: section/zone order captured, shared template handled separately.
- Assets: each reference resolved or flagged.
- Dynamic: connector or deliberate approved snapshot downgrade recorded.
- Security: raw captures protected, output sanitized, permissions/publishing status reviewed.
- Fidelity: text, links, media, metadata and responsive behavior tested.
- Source type: conflicts produce manual review and never accidental wrong adapter selection.

## Scope of current offline spike

Run: python -m unittest discover -s tests -v

Run: python -m research_spike.classify examples/route-evidence.synthetic.json

The classifier reads an **existing metadata JSON file only**; it does not authenticate, inspect, scrape or migrate SharePoint. Its classification flags assume the caller has correctly verified field/API evidence. It is a provisional routing test, not production readiness.
