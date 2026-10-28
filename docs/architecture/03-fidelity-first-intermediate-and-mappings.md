# ADR 003 — Clean, fidelity-first intermediate model and destination mappings

**Status: accepted PoC goal (2026-10-28); implementation is partial.** This supersedes an earlier impression that the product is a general SharePoint-to-React or SharePoint-to-anything renderer. We are starting with ONE Modern SharePoint source format.

## Product goal

Convert messy SharePoint-authored web pages into CLEAN, PORTABLE page structure, preserving appearance and behavior as far as supported by evidence. The default target is a straightforward independent **HTML + CSS + necessary JavaScript** webpage. The same cleaned intermediate data can later map into a client's expected components or CMS structure without re-parsing the original SharePoint page.

Do not begin three SharePoint adapters in parallel. Validate the shared clean core on one Modern source first. Other readers, when justified, only adapt different source data into this same contract.

## Two explicit output intentions

| Intent | Default? | Behavior |
|---|---|---|
| faithful-migration | YES | Clean semantic HTML, maintain source content/order/relative layout, recreate measured styles and supported behavior, no invented components or branding |
| client-mapping | opt in | Use an explicit user-defined mapping profile, e.g. a normalized linkList -> client's ResourceLinks component; declare any style/behavior differences |

The CIR contains neither React component names nor a client's brand class names. Mapping profiles are destination-specific and versioned.

## Pipeline and ownership

1. **Source capture:** Keep the source API/markup/field properties and optional rendered snapshots in a restricted auditable capture bundle (not final HTML).
2. **Extraction/cleanup:** Parse source structure; decode HTML entities and URLs; identify content vs SharePoint-generated wrappers, webpart placeholders, zones, assets, nav and layout. Do not delete a wrapper until its semantic/layout effect has been understood.
3. **Canonical IR:** Semantic document tree, ordered layout (including grid fractions), structured content/rich text, asset/link identities, styles, behavior definitions, and source provenance/fidelity diagnostics. All kinds are generic and framework-independent.
4. **Output mapping:** Render default HTML+CSS+JS or use a client mapping registry for desired controls. Destination adapters NEVER read raw SharePoint API data.
5. **Verification:** Compare source vs output on content, links, assets, heading semantics, interactions and responsive screenshots when actual source screenshots/CSS exist. Emit quantitative or qualitative issues; no fake perfect-fidelity score when source observations are absent.

## Minimal CIR contract to refine during the ONE-source PoC

- `page` — URL/title/description, content language, metadata and optional shared-shell reference.
- `tree` — explicit ordered semantic blocks (section, columns, heading, paragraph, richText, image, linkList, card, etc.), stable source/node IDs and hierarchy.
- `layout` — widths, ordering, alignment and meaningful breakpoint behavior; preserve source grid span in capture.
- `styles` — small semantic design tokens AND scoped observed overrides for properties critical to fidelity; not raw SharePoint classes.
- `assets` — source URL, safe resolved destination, alt, dimensions/crop when available, status.
- `behaviors` (future schema revision) — safe intent, trigger, state, accessibility and dependency; do NOT copy raw SharePoint JavaScript.
- `sourceRef`/`fidelity` — each mapped component's origin, preservation status, approximations and unsupported reasons.
- `diagnostics` — unmapped parts, unresolved styles, broken assets/links, missing interactions, weak source evidence.

Do not add speculative required schema properties prematurely. The current `schema/page.ir.schema.json` v0.1 has `tree`, `layout`, `styles`, `designTokens`, `assets`, provenance and diagnostics; its behavior/mapping contract is still a design proposal.

## A concrete mapping example

Source: Quick Links webpart with two links, configuration and ordering.

Normalize ONCE into the following conceptual structure:

    {
      kind: linkList,
      id: links-01,
      items: [{label: A, href: /a}, {label: B, href: /b}],
      layout: {variant: compact},
      sourceRef: {webPartId: original-guid}
    }

Default HTML mapping: accessible `<nav><ul><li><a>...</a></li></ul></nav>` + scoped CSS; JavaScript only if the source interaction needs it.

Client mapping example (later, **not yet implemented**): `linkList -> MySite.LinkGroup` with explicit prop mapping. This is a destination setting, NOT a SharePoint parser change.

## Fidelity versus clean code

- **Keep:** content, heading levels, semantic tables/lists, media/link identity, meaningful section/column arrangement, accessibly supported interactions, shared shell where source evidence supports it, and visual design rules that materially affect appearance.
- **Replace:** meaningless SharePoint `div` wrappers, runtime script dependencies, generated class names, safe-to-eliminate nested tables used purely for layout, obsolete IDs and redundant inline styles.
- **Preserve as overrides if necessary:** unique widths, spacing, background, typography, image crop, special placement and responsive behavior when faithfully reproducing the design needs them. Tokens alone may be insufficient.
- **Never invent:** client masthead, footer, branding, fake menus, stock content, visual scores or interactive behavior. The PoC's earlier demo added a branded header/footer; the revised default renderer removes this.
- **Never silently remove:** unrecognized controls, content, link destinations or layout regions. Emit an explicit unknown control plus diagnostics.

## JavaScript policy

Plain content pages should normally output HTML and CSS only. If a supported source feature is interactive, represent behavior semantically and generate a small, independent JS module with progressive enhancement and keyboard accessibility. Never execute or migrate arbitrary SharePoint source scripts. Unsupported dynamic features should be visible in the report.

## What the current Modern PoC proves (and does not)

**Proves locally:** one Graph-shaped public-documentation-adapted fixture -> generic layout/content CIR -> standalone HTML and CSS; explicit unknown webpart and asset references; tests. The new `structural` stylesheet is the default, and the old illustrative branded CSS is opt-in with `--style-mode demo`.

**Does not yet prove:** actual SharePoint DOM cleanup of a production page, matching-source CSS extraction, high-fidelity responsive rendering, source JavaScript behavior translation, or client component mapping. The sample is not a real CDPH authoring export; no source screenshot exists to compare against.

## Single-source acceptance criteria before extending adapters

1. Demonstrate a messy **public Modern source fixture** being decoded/cleaned, keeping all authored content and source order.
2. IR validated, explicitly independent of the output framework, with source references and unsupported warnings.
3. Generate **independent HTML + CSS** without fake navigation/footer or SharePoint runtime; JS only if observed interactions require it.
4. Test a separate target-mapping profile consuming the SAME CIR without changing source parsing (may be a tiny test profile).
5. Document how appearance was preserved, approximated or unverified, with before/after comparisons only when source visual evidence is available.

**After these gates**, consider another SharePoint page family, not before.
