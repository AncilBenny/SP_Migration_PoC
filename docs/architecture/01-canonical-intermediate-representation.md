# Architecture decision 001 — Canonical Intermediate Representation (CIR)

Status: **proposed, research draft**, 2026-10-28.

## Problem

A generic SharePoint-to-web migration must not require a SharePoint runtime or a specific target UI framework. Source APIs differ (Graph modern, CSOM/PnP classic, public rendered HTML as fallback); target component libraries will also change. If adapters write React or target HTML directly, all source differences leak into every destination.

## Decision

Build a versioned **Canonical Intermediate Representation (CIR)**: one normalized semantic page tree with layout, content, assets, references, design tokens, source provenance and fidelity diagnostics.

    SharePoint adapters (Graph / classic APIs / public HTML)
        -> source-specific capture bundle (lossless, access controlled)
        -> source-specific parsers
        -> semantic + layout normalization
        -> CIR v0.1
        -> target adapters (React, static HTML, headless CMS, other)

Retain the raw capture separately for audit and remapping. CIR is **not** a lossless copy of the SharePoint internal schema; it is clean and target-agnostic. Provide traceable source refs and diagnostics to prevent silent information loss.

## Contract principles

1. **Semantic blocks**: heading, paragraph, image, table, linkList, hero, callout, etc., not source CSS classes or SharePoint GUID names.
2. **Layout tree**: section → columns → column → nested content, preserving ordering, relative widths, and known responsive hints.
3. **Content plus behavior**: text/image/link data is portable. Data-bound parts need a dynamicCollection/search/etc. descriptor, not just a frozen screenshot.
4. **Styles as tokens**: design tokens and layout variants separate from content; recorded unnormalized CSS lives in evidence, not output.
5. **Provenance**: each page/node can identify source type, original URL, source part ID/type, extraction method and confidence.
6. **Diagnostics**: unsupported web parts are explicit unknown nodes; fidelity/status and warnings quantify migration gaps.
7. **Accessibility and safety**: structured headings and link labels, alt text, tables and sanitized rich text; no arbitrary executable source JS.
8. **Versioning**: schemaVersion is required; backward-compatible extensions are under extensions. Changes that redefine meaning require a schema version bump.
9. **No leaked secrets**: separate secure raw source capture from publishable CIR. Do not embed tokens, internal endpoint credentials, ACL dumps or private binary blobs in public output.
10. **Idempotence**: stable node IDs should derive from stable source IDs when available; otherwise stable path/order mapping. Content hashes assist change detection without exposing content unexpectedly.

## Draft document fields

- schemaVersion — explicit CIR schema version.
- source — sourcePlatform, pageModel, sourceUrl, capture method, timestamp, optionally source site/page ID and provenance.
- page — page id, title, description, page URL, locale, publication state and metadata.
- tree — root page node with ordered child nodes.
- designTokens — optional extracted theme token buckets.
- assets — referenced media/files and retrieval/resolution status.
- diagnostics — mapping gaps, warnings and severity.
- extensions — namespaced future source/target annotations.

See schema/page.ir.schema.json and examples/page.ir.example.json. Those are **proposed fixtures**, not exported from any real CDPH or SharePoint tenant.

## Node mapping contract

A node has id, kind and optional children. It may have:
- content: portable text segments and metadata, not executable untrusted DOM;
- props: typed component-level parameters, preferably schema-refined by control kind later;
- layout: column span, width fractions, alignment, responsive hints;
- styles: token references and semantically named variant;
- sourceRef: original page field / webpart / DOM selector path, source part type/ID;
- fidelity: exact, approximate, unresolved or unsupported, with reason.

A dynamicCollection node should distinguish source binding from currently rendered items. Source-specific query details may live in a secure capture bundle and a restricted extension; the public CIR should contain a portable data connector contract if possible.

## Example conceptual mapping

    SharePoint modern canvas
      horizontalSection (layout=twoColumns)
        column width=8 -> textWebPart: H2 + paragraph
        column width=4 -> standardWebPart (Image)
              |
              v
    CIR page
      section
        columns
          column (widthFraction=0.6667)
            heading (level=2)
            paragraph
          column (widthFraction=0.3333)
            image (assetId=hero-image-01)

This mapping is illustrative, not a CDPH inspection result. Some rich text must remain a richText node until splitting into headings/paragraphs is validated; never split blindly if it breaks tables, inline widgets or ordering.

## Open architecture questions

- Which source web-part families require dedicated data-bindings or behavior mappings?
- How should rich-text AST, inline links and tables be represented consistently across renderers?
- What is the minimal generic set of controls without losing important semantics?
- How do we version siteShell/navigation, page templates and repeated components separately?
- Should normalized snapshot state be shipped for dynamicCollection fallback?
- Which audience/site permissions must accompany migrated pages? Never assume public snapshot implies public source authorization.

## Testable exit criteria (for Phase 2)

- 1 modern page and 1 classic/publishing page can be captured with permission and represented with a source bundle and CIR.
- Validation confirms ordering, headings, sections, links and media references.
- Unknown components yield visible diagnostics; none vanish silently.
- Two completely different output adapters can render the same fixture (e.g. HTML and React) without modifying extraction logic.
- Reprocessing the same capture yields identical CIR aside from explicit capture timestamps.
- All output content is sanitized, and credentials/private data do not appear in the deliverable.

This is an architecture proposal; it is **not** an implemented parser, migration utility, or Graph connector.
