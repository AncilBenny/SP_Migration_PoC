# SharePoint Migration PoC

Research-first migration project for the **three common SharePoint page experiences**: Modern Site Pages, Classic Wiki/Web Part Pages (one grouped adapter with two parsing strategies), and Classic Publishing/Website Pages.

**Goal:** extract SharePoint authored page content, layout, web parts, assets, metadata and design decisions into a versioned **Canonical Intermediate Representation (CIR)** that can be rendered as ordinary web pages, React components, other frontend stacks or CMS content without requiring SharePoint at runtime.

**MVP scope:** [Three page-family adapters only](docs/research/09-mvp-scope-three-page-families.md). Unusual SharePoint editions, specialized ASPX/Blog pages, custom SPFx and live business services are deferred, with explicit unsupported diagnostics.

**Status:** Research and architecture, with a small **offline evidence-based page classifier**. There is no production SharePoint connector, content crawler, normalized renderer or real tenant migration yet.

## Architecture

    Authorized SharePoint Online pages
          -> per-page family detection
          -> Modern Graph reader / Classic Content reader (Wiki or Web Part strategy)
             / Classic Publishing reader (page/layout/master)
          -> secured source capture and asset/dependency manifest
          -> semantic + layout + design token normalization
          -> versioned CIR
          -> target adapters (React, HTML/CSS, headless CMS and others)
          -> source-to-target quality report

A site can contain **multiple** supported SharePoint page families. Public HTML remains observation-only fallback; supporting every on-premises edition is not the MVP.  Route per page and reuse a sitewide template/theme catalog. An unknown custom part should generate an explicit review diagnostic, not disappear.

## Start here

- **[MVP scope: exactly three page families](docs/research/09-mvp-scope-three-page-families.md)**
- [Research index and page-model findings](docs/research/README.md)
- [Adapter-by-page-family research matrix](docs/research/05-adapter-research-matrix.md)
- [Architecture decision: detection and capture](docs/architecture/02-classification-and-capture-contract.md)
- [Architecture decision: canonical IR](docs/architecture/01-canonical-intermediate-representation.md)
- [CIR v0.1 draft JSON schema](schema/page.ir.schema.json) and [synthetic sample](examples/page.ir.example.json)
- [Evidence collection experiments](docs/research/08-next-research-experiments.md)

## Offline classification spike (no network access)

Requires Python 3.10 or newer. From repository root:

    python -m unittest discover -s tests -v
    python -m research_spike.classify examples/route-evidence.synthetic.json

The input JSON is **synthetic**. The spike demonstrates cautious classification from trusted evidence: modern Graph, verified classic assessment, or authenticated page fields; conflicting data triggers manual review. Bare .aspx URLs remain unknown.

## Research boundaries

No source SharePoint access or CDPH live stylesheet analysis has been completed. Any sensitive source capture must be authorized, restricted, sanitized and kept out of this repo. No production credentials, unredacted private content or source JavaScript should be committed.


## Phase 3 field-level research

- [Three-family source field extraction blueprint](docs/research/10-three-family-source-field-blueprint.md): Graph properties, 12-unit grid, classic WikiField and zone definitions, PublishingPageContent/PageLayout.
- [CSS / layout / shared site-shell investigation](docs/research/11-style-css-site-shell-vs-page.md): where to find classic theme CSS, how to observe responsive design and deduplicate templates.
- [Latest findings and CIR revision gates](docs/research/12-findings-and-ir-revision-gates.md): concrete schema gaps and real-sample evidence needed.
- [Four synthetic source-to-CIR traceability cases](examples/research/three-family-traceability.synthetic.json): modern, classic Wiki, classic Web Part and publishing examples. Not real tenant content.

**CI status:** Research checks have reported a failure; remote job logs were unavailable during investigation. Do not treat automated checks as passing until a successful run is visible.


## Public-only evidence research (no SharePoint account required)

- [Public SharePoint source + CDPH website evidence](docs/research/13-public-only-source-and-website-evidence.md) — directly inspected public Wiki fixture, Modern CanvasContent1 fixture, Web Part Page source template, Publishing ASPX page and layout, and live CDPH HIE pages.
- [Derived evidence manifest](examples/research/public-evidence-derived.json) — reproducible URLs, GitHub source blob hashes, measured structural facts and explicit limitations; no copyrighted page bodies copied.
- [Public-evidence research checks](tests/test_public_evidence.py) — guards against treating public HTML as confirmed SharePoint and against combining unrelated page+layout sources.

**Access boundary:** Modern SharePoint Online usually requires authentication and cannot be treated as a public anonymous site. The initial PoC can use public source files and open-source fixtures. This research does not require a SharePoint plugin or access to a private tenant. The actual www.cdph.ca.gov pages still returned HTTP 502 during direct fetches; hie.cdph.ca.gov pages were viewable but their backend is unclassified.

**Evidence status:** Public real source files and visible public content found for architecture study; no verified same-site source + stylesheet + rendered output triplet, and no source-to-target migration run yet.