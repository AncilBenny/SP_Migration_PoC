# Phase 1 — SharePoint page migration research

Date: 2026-10-28. Status: initial desk research and draft architecture; no tenant export or authenticated page scraping yet.

## Study map

1. [SharePoint page models and extraction surfaces](01-sharepoint-page-models.md) — modern vs classic, APIs, fields, web parts and limitations.
2. [CDPH public case study](02-cdph-public-site-observations.md) — observed search-indexed archetypes, SharePoint evidence and explicit direct-fetch limitations.
3. [Stylesheet/layout generalization](03-styles-layout-normalization.md) — separating content, structure, design tokens and behavior.
4. [Research backlog and test matrix](04-research-backlog-and-test-matrix.md) — how to test against real samples and declare readiness.
5. [Canonical Intermediate Representation decision](../architecture/01-canonical-intermediate-representation.md) — proposed portable contract and fidelity rules.
6. [Draft JSON Schema](../../schema/page.ir.schema.json) and [synthetic example](../../examples/page.ir.example.json).

## Central hypothesis

**Input adapters → audited capture → semantic normalization → portable CIR → independent renderers.** Different SharePoint models should map into the same conceptual blocks without losing source provenance, ordering or unsupported-part information.

## What is verified vs pending

**Verified from Microsoft documentation**: modern Graph sitePage canvas and webPart representation; classic master page/page layout/zone differences; limited supported Graph web-part writes; classic assessment taxonomy. **Observed via indexed public material**: CDPH has public ASPX content archetypes and an indexed SharePoint SOAP service path. **Not verified**: CDPH's live DOM, CSS, actual SharePoint edition/page type, master pages, individual web parts, component dimensions or computed styles (direct fetch failed).

## Do next

Obtain an approved/redacted SharePoint page export for one modern and one classic/publishing page, then compare the source parts, rendered screenshot and CIR. Confirm source formats before implementing access adapters. Any HTML-driven observation must be compliant, rate-limited and treated as potentially incomplete.
