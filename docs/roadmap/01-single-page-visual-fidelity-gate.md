# PoC fidelity milestone — one page, same appearance, cleaner output

Status: agreed product direction, **NOT completed**. Date: 2026-10-28. Scope: **one Modern SharePoint source family**, one representative publicly documented source fixture, and where obtainable one matching public rendered-page baseline. Do not begin Classic or Publishing adapters.

## North star

Output a standalone web page with **the same authored content, structure, styling, relative layout, media, responsive behavior and supported interactions** as the source page, while removing SharePoint runtime dependencies and incidental HTML/CSS/JS complexity. The IR is generic and supports downstream client component mappings without re-parsing SharePoint.

**Faithful does not mean pixel-identical source code.** The source and output DOM may be entirely different; the visible outcome and semantically meaningful structure should remain the same. Prefer semantic HTML, maintain accessibility, and preserve behavior intentionally.

## Explicit evidence limitation

Public documentation Graph JSON and open-source fixtures establish SharePoint field syntax, but they generally lack matched rendered HTML/CSS/screenshots for the *same* Modern SharePoint Online page. Live anonymous Modern SharePoint authoring data usually requires authentication. Never claim visual fidelity has been verified unless matched public authoring+rendered baseline exists. Public CDPH HIE pages are usable as website-output design references only; their SharePoint platform is unverified. www.cdph.ca.gov remains inaccessible for direct raw-page inspection in this environment. **Two unpaired public artifacts are not a source-to-target fidelity test**.

## The next four engineering increments

### P0 — Source capture contract and trustworthy baseline

Choose one real public web page with independently retrievable HTML, linked stylesheets, assets and desktop/mobile screenshots. If no such *Modern SharePoint* page can be found, keep separate (A) the actual published Graph/SharePoint authoring fixture for parser validation, and (B) a plain public website screenshot/CSS sample for visual renderer calibration. Explicitly report this separation.

Capture a reproducible evidence manifest: URL, retrieval timestamp, SHA256 of raw HTML, ordered linked CSS/JS/assets, observed DOM landmarks, computed style properties, responsive screenshots at e.g. 1440 and 390 CSS px and viewport/device scale. Keep only authorized/public evidence; avoid copying copyrighted full page content into GitHub except where licensed/appropriate.

### P1 — Clean/normalize with no loss

Build a true cleanup stage for modern serialized SharePoint markup (CanvasContent1 when publicly represented) or typed Graph canvas; do not treat a demo JSON as messy authored HTML. Remove *only* wrappers and attributes proven to be nonsemantic; retain meaningful headings, tables, lists, anchors, images, ordering, widths, alignments, backgrounds, typography and responsive stacking. Preserve unknown webparts with source ID/type/properties reference and a diagnostic.

IR should explicitly distinguish source-supplied values from observed/computed values, from inferred defaults. Use semantic tokens + component-scoped style overrides where needed for visual fidelity; keep the raw capture and measured stylesheet details out of framework-neutral IR.

### P2 — Default clean HTML/CSS/necessary JS generation

Default output: readable semantic HTML, a well-organized CSS stylesheet with variables/layout definitions and only a tiny independent JS module for supported interactions. No source SharePoint scripts, generated runtime class names, invented masthead/footer/branding or unrequested design changes. Produce one portable folder containing index.html, style.css, assets/, optional app.js, page.ir.json and report.json.

Only after fidelity path works, prove one *small* second mapping profile (e.g. linkList -> client-defined HTML/CSS component) consuming the SAME CIR; the source parser must remain unchanged.

### P3 — Automated and visual parity report

Compare source and generated evidence and report:

| Axis | Minimum demo exit criterion |
|---|---|
| Text | 100% of visible source text/ordered headings inventoried and mapped, or explicitly diagnosed |
| Links | 100% of link destinations accounted for; rewritten internal links tested, unresolved links reported |
| Media | Each meaningful image/file asset accounted for, src/alt/crop/dimensions flagged where unknown |
| Structure | Major sections, page order, responsive columns/regions correspond to source, without arbitrary invented content |
| Style | Compare measured fonts, colors, spacing, widths, alignment, borders/backgrounds at chosen viewports; report unverified fields |
| Behavior | Each visible interactive control either behaves the same accessibly, or is explicitly unsupported |
| Cleanliness | No SharePoint runtime required; no arbitrary copied source JS; semantic and maintainable output |
| Visual QA | Capture source and output at the SAME viewport and compare overlays/diff + human inspection; don't fabricate a score without matched source screenshots |

## Demo story

Show original public page/source evidence, cleaned CIR with traceable components, generated HTML/CSS/necessary JS, side-by-side screenshots (only with matched source evidence), and a report identifying exact, approximate, missing and unsupported pieces. This is the product proof—not the number of adapters.

## Current baseline

PoC 01 currently parses a modern Graph-shaped, public-documentation-adapted fixture into generic sections/columns/text/image/Quick Links, outputs static HTML/CSS, and flags unsupported parts. The current neutral `structural` stylesheet is an **unverified placeholder for original styles**, not proof of visual parity. The opt-in `demo` stylesheet is illustrative. Generated JS and client mapping profiles are not implemented. Local tests were reported passing; GitHub CI has reported failures and is not verified green.

## Do not expand scope until

1. A reproducible source evidence manifest or honest paired/unpaired public-fixture story exists.
2. Core content/layout mapping is loss-accounted for on one real/publicly published SharePoint representation.
3. Output HTML/CSS has no invented branding or unsupported silent loss.
4. Style fidelity is either tested against a *matched* baseline or clearly flagged blocked, with a documented plan to obtain evidence.
5. A report makes approximations, unsupported elements and source/evidence confidence obvious.
