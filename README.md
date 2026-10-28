# SharePoint Migration PoC

Research-first, source-agnostic SharePoint page migration project.

**Objective:** extract SharePoint page content, layout, web parts, assets, metadata, and design decisions into a versioned **Canonical Intermediate Representation (CIR)** that can be rendered into ordinary web pages, React components, other frontend stacks, or CMS content without depending on SharePoint at runtime.

**Current status:** Phase 1 — research and architecture. No production extractor or renderer has been implemented yet.

Research documents and draft schema are proposed via a research pull request. This repository will evolve in phases: source analysis → extraction adapters → normalization/CIR → mapping and rendering → validation.

Do not use production credentials or migrate private content without appropriate tenant authorization.
