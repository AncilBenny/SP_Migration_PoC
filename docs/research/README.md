# SharePoint page migration — research index

Date: 2026-10-28. **MVP is limited to three page families**: Modern Site Pages; grouped Classic Wiki/Web Part content pages; Classic Publishing/Website pages. [Decision and acceptance criteria](09-mvp-scope-three-page-families.md). Other source types in the research chapters are background and future possibilities, not build commitments. Current status: desk research plus an **offline classifier spike**, not a production extractor. No authorized tenant export or live CDPH DOM/CSS inspection yet.

## Research chapters

1. [SharePoint page models and extraction](01-sharepoint-page-models.md): Modern vs classic, available APIs, fields, parts and known limits.
2. [CDPH public case study](02-cdph-public-site-observations.md): search-indexed public page archetypes and evidence limitations.
3. [Stylesheets, layout and generalization](03-styles-layout-normalization.md): content vs structure vs design tokens vs behavior.
4. [Research backlog and test matrix](04-research-backlog-and-test-matrix.md): scope, evidence and acceptance criteria.
5. [Separate source adapter research](05-adapter-research-matrix.md): modern Graph, classic Wiki/Web Part/Publishing, on-prem and HTML fallback.
6. [Semantic component and dynamic-data study](06-components-and-dynamic-data.md): preliminary webpart->CIR mappings, custom and live dependencies.
7. [Repeatable layout/CSS capture protocol](07-style-and-layout-capture-protocol.md): site shell, style tokens, viewports and evidence capture.
8. [Next research experiments](08-next-research-experiments.md): real-sample collection requirements and go/no-go criteria.
9. **[MVP scope — three page families](09-mvp-scope-three-page-families.md)**: current authoritative boundary for implementation priority.

## Architecture artifacts

- [ADR 001 — Canonical Intermediate Representation](../architecture/01-canonical-intermediate-representation.md)
- [ADR 002 — Classification and secure capture contract](../architecture/02-classification-and-capture-contract.md)
- [Draft JSON Schema](../../schema/page.ir.schema.json) and [synthetic CIR example](../../examples/page.ir.example.json)
- [Offline classifier spike](../../research_spike/classify.py), [synthetic tests](../../tests/test_classify.py), [input fixture](../../examples/route-evidence.synthetic.json)

## Proposed architecture

SharePoint deployment/profile discovery -> **page-family adapter** -> restricted source capture -> semantic/layout/style normalization -> versioned CIR -> target adapters.

Use **three top-level readers**: Modern Graph, grouped Classic Content (WikiField/WebPart strategy), Classic Publishing. One SharePoint site can contain multiple families; **never hardcode per-site/page-family assumptions**. CDPH is a public case study; its real source page family, stylesheets, master and webpart definitions have not been verified.

## Offline research spike

From repository root:

    python -m unittest discover -s tests -v
    python -m research_spike.classify examples/route-evidence.synthetic.json

These use synthetic data only. Neither command accesses SharePoint. A classifier route is only as reliable as the authenticated evidence supplied to it.

## Current evidence status

Microsoft / PnP documentation has confirmed modern Graph canvas and title area, classic page models, classic Assessment Tool limitations, CSOM WebPartManager, and the role of publishing templates. The CDPH public research is limited to indexed content and an indexed SharePoint SOAP service path; direct page/CSS retrieval failed. **No real-site mapping has yet been validated.**

## Next evidence requirement

Obtain a read-only authorized modern sitePage JSON and a redacted classic wiki/webpart/publishing sample including original webpart properties and layout; compare with rendered screenshots to validate source-to-CIR mapping. Do not add unredacted tenant captures to GitHub.
