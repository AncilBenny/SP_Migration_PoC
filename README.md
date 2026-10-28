# SharePoint Migration PoC

Research-first, source-agnostic SharePoint page migration project.

**Goal:** extract SharePoint authored page content, layout, web parts, assets, metadata and design decisions into a versioned **Canonical Intermediate Representation (CIR)** that can be rendered as ordinary web pages, React components, other frontend stacks or CMS content without requiring SharePoint at runtime.

**Status:** Research and architecture, with a small **offline evidence-based page classifier**. There is no production SharePoint connector, content crawler, normalized renderer or real tenant migration yet.

## Architecture

    SharePoint Online or Server / public rendered HTML fallback
          -> deployment discovery + per-page family classification
          -> modern Graph / classic wiki / classic webpart / classic publishing adapters
          -> secured source capture and asset/dependency manifest
          -> semantic + layout + design token normalization
          -> versioned CIR
          -> target adapters (React, HTML/CSS, headless CMS and others)
          -> source-to-target quality report

A site can contain **multiple** SharePoint page families. Route per page and reuse a sitewide template/theme catalog. An unknown custom part should generate an explicit review diagnostic, not disappear.

## Start here

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
