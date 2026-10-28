# SharePoint cleanup → clean portable page IR → HTML / CSS / necessary JS (PoC 01)

A small offline vertical slice for **one source family: Modern SharePoint Site Pages**. The goal is to clean and preserve authored structure, visual intent and supported behavior as a reusable intermediate page model, then generate **standalone semantic HTML + CSS + JS only when interactions require it**. Target-specific component/CMS mapping can be added later without changing source parsing. We are **not** implementing the other SharePoint page families in parallel.

**[Read the fidelity-first architecture and destination-mapping contract](docs/architecture/03-fidelity-first-intermediate-and-mappings.md).**

**[Next milestone: prove same-page content, layout, style and behavior fidelity](docs/roadmap/01-single-page-visual-fidelity-gate.md)** using only publicly available evidence. We will not claim visual parity from an unpaired Graph fixture and rendered website.

## Demo (Python 3.10+, no dependencies or SharePoint login)

```sh
python -m unittest discover -s tests -v
python -m poc build --input poc/samples/modern-demo.json --out demo
python -m http.server 8000 --directory demo
```

Open `http://localhost:8000`. Output includes `index.html`, `style.css`, `page.ir.json`, `report.json` and a demo SVG under `assets/`. The **default structural CSS** keeps content/layout without inventing a site's colors, masthead or footer. If you want the earlier *illustrative demo visual style*, run the build with `--style-mode demo`. Neither option claims pixel-fidelity because no matching source screenshot and CSS were available.

To run against a **compact sample adapted from Microsoft's published GET sitePage response**:

```sh
python -m poc build --input poc/samples/microsoft-graph-doc-example.json --out demo-doc
```

## Current supported input and output

- Input: **JSON shaped like Graph `microsoft.graph.sitePage` expanded with `canvasLayout`**; no API calls and no credentials.
- Extract: `titleArea`, `horizontalSections`, 12-grid columns, `textWebPart.innerHtml`, standard **Image** and **Quick Links** web parts.
- Normalize: semantic `page` → `section` → `columns` → `column` → `richText` / `image` / `linkList`, with source web-part IDs and fidelity flags.
- Output: reusable CIR JSON, standalone responsive HTML/CSS, local demo asset and diagnostics/report. Static input does **not** need an empty JS file; interaction-aware JS generation is a subsequent PoC step.
- Unknown parts: explicit `unknown` blocks plus `UNMAPPED_WEBPART` diagnostics; do not silently discard.
- Safety: basic allow-list rich HTML sanitation, URL scheme filtering, escaping, offline generated output; no arbitrary source script execution. This is **not** a production security boundary.

## Sources and honesty about provenance

The two input samples are **public-documentation-adapted examples**. The schema and field placements come from Microsoft's [sitePage GET](https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0), [sitePage create](https://learn.microsoft.com/en-us/graph/api/sitepage-create?view=graph-rest-1.0), and [standardWebPart](https://learn.microsoft.com/en-us/graph/api/resources/standardwebpart?view=graph-rest-1.0) documentation. The modern showcase's prose, identifiers, Quick Links, and offline illustrative SVG are authored for the demo; **they are not CDPH data or an authenticated SharePoint export**. The compact documentation sample was adapted into parseable JSON from the published illustration.

A public PnP CLI fixture and public classic ASPX source examples are discussed in the companion research PR for later Classic Content and Publishing adapters.

## Verified local demo result

The showcase contains **4 source web parts**, of which **3 map** to CIR controls and **1 remains explicitly unsupported** (75% fixture mapping coverage; **not** a visual accuracy metric). After the structural-default revision, **10 unit tests pass locally**. The migrated page no longer invents a branded masthead/footer; optional demo CSS remains explicitly illustrative. The report labels visual fidelity **unverified** due to missing source-page screenshots/styles. GitHub-hosted CI previously failed and is not confirmed passing.

The draft [CIR v0.1 JSON Schema](schema/page.ir.schema.json) is included for structural review.

## Destination mapping — different client designs from the SAME CIR

**Primary product goal:** clean SharePoint content and presentation into a portable canonical page model that can be translated to *different* client websites and controls. Reproducing the original page closely is one possible output profile; it is **not** a universal requirement. Read [ADR 004 — target mapping profiles](docs/architecture/04-generic-target-mapping-profiles.md).

First generate the source-independent CIR as before, then apply a separate client profile **without running the SharePoint parser again**:

```sh
python -m poc build --input poc/samples/modern-demo.json --out demo
python -m poc map --ir demo/page.ir.json --profile poc/profiles/client-example.json --out demo-client
python -m http.server 8000 --directory demo-client
```

The mapper reads only the CIR, not `canvasLayout` or other SharePoint-specific fields. `linkList` becomes client-style **resource cards**, `hero` becomes a client page header, and the colors/spacing come from the destination profile. Profile choices are a small, safe, versioned catalog of supported components rather than executable templates. The same CIR may instead map to simple links with a different palette.

The output directory includes `index.html`, `style.css`, `page.ir.json`, copied local assets, and `mapping-report.json` (CIR SHA-256, mapped target kinds and warnings). Static pages need no generated JavaScript. Unmapped source web parts are not discarded: they remain visible as review placeholders.

**Quality depends on output intent:** faithful migrations are evaluated against source screenshots/CSS where available; client-target migrations are evaluated against the client's design/mapping specification *plus no-loss content, asset and link accounting*. This example is adapted from public documentation and doesn't prove either full real-site source fidelity or a complete production client system.

**Validation:** 15 offline unit tests pass locally after adding 5 destination-mapping tests (including preservation of the same IR, custom target output, CSS injection rejection, local asset URLs, unsupported part reports, and IR HTML re-sanitization). GitHub CI remains separately unverified.

## New: public CanvasContent1 cleanup and client destination rewrites

One source family only: Modern SharePoint. The PoC now accepts both documented Graph-shaped `sitePage` JSON and the **serialized modern `CanvasContent1`** representation seen in PnP CLI's publicly available fixture.

```sh
python -m poc build --input poc/samples/pnp-canvas-public.json --out demo-pnp
python -m poc build --input poc/samples/modern-internal-links.json --out demo-rewrite
python -m poc map --ir demo-rewrite/page.ir.json --profile poc/profiles/client-example.json --out demo-mapped
python -m http.server 8000 --directory demo-mapped
```

The public PnP fixture decodes control IDs and canvas positions. Its custom web part remains explicitly unsupported; the decoder will not execute its code or hallucinate static content from it. The adapted internal-link sample demonstrates two source URL rewrites to `/knowledge/...` and relocation of the local image from `assets/` to `media/` **only in the client output**. The canonical JSON is byte-for-byte unchanged across the mapping step.

`mapping-report.json` now includes `nodeMappings`, `urlRewrites`, `assetRewrites`, and warnings. All outputs remain **HTML/CSS** for these non-interactive examples; JS is generated only after supported behavior contracts are implemented.

See [the public-source cleanup and destination rewrite milestone](docs/poc/05-public-canvas-and-client-rewrites.md), including original fixture attribution and limits.
## PoC boundaries / next steps

1. The Modern reader **does not** support full rich-text semantics, custom SPFx parts, inline standard parts, vertical sections, live data-bound parts, authentication, page collections, or perfect site style fidelity. The demo reports unsupported parts.
2. Structural CSS is a neutral layout baseline, **not source-measured SharePoint/CDPH styling**. The opt-in demo mode is visually decorative, not a faithful migration. Fidelity will require observed CSS/computed styles and screenshots.
3. Relative image references need an explicit demo asset map or an accessible source URL. This sample bundles a small original illustration to work offline.
4. **Next: stay on Modern only.** The second destination profile is now implemented. Improve cleanup/normalization of a messy public serialized Modern fixture, trace all source elements, add safe URL rewrite mapping, and test target requirements before adding another source family.

No SharePoint plugins or private tenant access are needed to reproduce this demo.
