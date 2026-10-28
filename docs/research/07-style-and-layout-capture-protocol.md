# Research 07 — Repeatable stylesheet, layout and component evidence collection

Date: 2026-10-28. Protocol to execute on authorized sites. **Not yet executed on CDPH**.

## Objective

Build a reusable site-level style model from multiple representative pages while preserving authored structure and not relying on raw SharePoint class names at render time.

## Capture layers, not just a screenshot

1. **Authoring**: Graph canvas sections/columns and part data, or classic page fields/zones/layout template references. Gives authoritative order and content ownership.
2. **Shared shell**: master page or common site navigation/logo/breadcrumb/footer/header, repeated over pages. Keep separate from page body.
3. **Design system**: stylesheet sources and cascade ordering, CSS custom properties, typefaces, reusable colors/spacing/widths, media queries and style variants.
4. **Rendered behavior**: permitted DOM snapshot and screenshot at at least desktop/tablet/mobile widths, accessible headings and control interactions.
5. **Assets**: URL/ID, alt text, dimensions/crop, permissions, local rewrite and broken links.

## Study procedure for each page

A. Record URL, retrieval time, source access mode, content type, page family evidence, source library/item ID, publication context, template association where available.

B. Export authorized API source: canvas or fields/webparts with part types/positions. Document list/service dependencies. Do not infer hidden webpart names from HTML classes.

C. When permitted and reachable, capture rendered HTML and screenshot at three controlled viewport widths (e.g. 1440, 768, 390 CSS px, fixed device scale), noting actual dimensions. Save stylesheet link order, CSS custom properties, media rules and computed styles for representative headings, links, tables, banners, sidebars and cards.

D. Cluster repeated components across at least three pages; classify repeated header/footer/breadcrumb/navigation as global site shell, publishing layout zones/field controls as template-owned and content nodes as page-owned.

E. Derive design tokens and semantic component variants. Keep original CSS evidence separately; do not copy all SharePoint JS or CSS into output. Record uncertainty for inferred visual rules.

F. Compare mobile/desktop order and stack behavior to source layout; don't invent breakpoints that cannot be observed.

G. Emit evidence: page body outline, zone/section tree, CSS/theme inventory, link/asset inventory, interaction inventory, accessibility notes, proposed token catalog and source-to-CIR mapping.

## Candidate tokens

- color roles: text, link, primary, surface, border, attention/status
- type: font family, font scale/weight, line height
- space: shared section/column gaps and internal spacing rhythm
- geometry: max-width, grid fraction, alignment, border radius
- responsive: observed breakpoint behaviors and column stacking
- component variants: callout, panel/card, navigation, table, button

Use actual computed styles and template evidence; candidate tokens without observed backing are hypotheses.

## Required comparisons

| Comparison | Question |
|---|---|
| Three pages, same site | What is shared shell versus content? |
| Two pages, same publishing layout | Which positions come from the template versus author fields? |
| Same page, two viewports | Which columns collapse/reorder and how? |
| Authored part vs visible DOM | Was content transformed by SharePoint, scripts or template code? |
| Dynamic collection vs current HTML | Is content live, audience-aware or static? |
| Source vs target preview | Are hierarchy, links, assets and accessibility preserved? |

## Known limitation

The earlier attempt to directly fetch CDPH pages/styles failed; no concrete CDPH stylesheet names, measured sizes, selectors or component boundaries are verified. Do not cite this protocol as evidence that measurements were obtained.

## Exit criteria

With permitted captures, identify sitewide shell, layout templates, authored page regions, major token groups and responsive variants. Every style claim must have an observed source or remain clearly labeled inferred/unresolved.
