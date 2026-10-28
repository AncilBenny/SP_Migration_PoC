# Research 03 — Stylesheets, layouts and generalization

## Objective

Preserve semantic structure, visible hierarchy and reasonable visual fidelity without copying an entire source SharePoint runtime, master page or opaque CSS bundle into each target.

## Four distinct layers

1. **Content**: headings, paragraphs, media, tables, ordered/unordered lists, links, metadata.
2. **Structure**: page shell, navigation, sections, columns, containers, ordering, responsive intent.
3. **Design tokens**: type scale, families, colors, spacing scale, border radii, elevations, widths, breakpoints.
4. **Behavior/data**: interactions such as accordion, tab, search or list queries; static versus dynamic source.

CSS alone cannot tell us which web part produced the HTML. Conversely, a web-part configuration does not describe all actual rendered styles. Combine both evidence sources when legally and technically accessible.

## Extraction and generalization pipeline

A. Identify authoring source: Graph canvas, classic page fields/zones, or a public rendered DOM snapshot.

B. Build a DOM/style observation tree separately from a **source part tree**. Capture stylesheet URLs, cascade order, specificity, CSS variables and computed values at a controlled set of desktop/mobile viewport widths. Avoid treating all CSS as page-owned: include sitewide shell dependencies.

C. Detect recurring style clusters across multiple pages. Propose tokens rather than arbitrarily copying individual pixel values. Example: repeated colors → palette roles (primary, link, surface, accent, danger); repeated heading sizes → type scale.

D. Map authored layout structures to layout primitives; infer responsive behavior from observed breakpoints where API data is absent. Unknown layout properties remain unknown, not guessed.

E. Separate page shell/header/footer/sidebar from content body via repeated-pattern evidence, shared source templates, semantic landmarks and source master/page layout references.

F. Normalize rich text into an AST / safe structured content model, not executable raw HTML. Normalize URLs (base resolution, internal mapping, anchors and file dependencies), alt text, table headers and semantic headings.

G. Emit CIR + a provenance bundle (source IDs, evidence confidence, snapshot hashes) + diagnostic report. Unknown/unsupported controls remain explicit nodes with preserved source references; do not discard.

H. Renderer adapter maps CIR nodes to target components and a small generated stylesheet or design-system token mapping. Validate content, links, headings, assets, responsive layout and a11y. Visual pixel-perfect copying is not required for semantic migration unless explicitly requested.

## Style ownership and precedence

Style layers (higher precedence later; **proposed**, not yet measured on CDPH):
- target base / accessibility defaults
- normalized sitewide theme tokens
- normalized component variants
- page/section style overrides *from observed source evidence*
- explicit item-specific style exceptions

Prefer token references and semantic variants such as callout.warning, card.featured, and heading.level2. Store a measured declaration as a residual style only when no stable token exists and it is safe to reproduce. Keep the original CSS address and selector in the evidence trail rather than making it an output dependency.

## Important anti-patterns

- Copying SharePoint CSS into Next.js wholesale: class names, JS-dependent states and internal assets can be unstable.
- Converting the rendered body to a single HTML blob: loses component boundaries, source part identity, structured content and reuse.
- Flattening all blocks: loses sections, columns, order, responsive and accessibility intent.
- Interpreting a dynamic list web part as a static link list: loses important behavior.
- Dropping unknown web parts: hides content loss.
- Treating site navigation/header/footer as authored content on each page.

## Candidate normalized control taxonomy

Layout: page, siteShell, section, container, columns, column, divider, spacer.

Content: heading, paragraph, richText, list, table, image, video, file, embed, quote.

Composite: hero, card, cardCollection, linkList, navigation, callout.

Interactive/dynamic: accordion, tabs, search, dynamicCollection, form, unknown.

The taxonomy is a starting hypothesis. New types should be introduced only when supported by ≥2 distinct real examples or when needed to preserve a genuinely different semantic/behavioral contract.

## Validation metrics (proposed)

- Text coverage: normalized text units vs source-visible or source-authored text.
- Structural coverage: matched ordered sections/columns/content nodes.
- Asset status: accessible/redirected/failed, alt-text preservation.
- Link fidelity: internal/external/anchor/attachment rewritten or unresolved.
- Unsupported parts: count, type, impact and review queue.
- A11y: heading levels, alt text, accessible labels, tables, landmarks.
- Visual comparison: snapshot diff at selected viewports (for prioritization, not as sole correctness criterion).
- Each normalization decision reports observed, inferred or unresolved confidence.

## Acceptance condition for this research chapter

We can explain for each sampled page: where its body comes from; what its web parts are; which CSS/theme is sitewide; which layout information is author-defined; which behaviors are dynamic; and how each maps to CIR, with evidence links.
