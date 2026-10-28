# SharePoint cleanup → clean portable page IR → HTML / CSS / necessary JS (PoC 01)

A small offline vertical slice for **one source family: Modern SharePoint Site Pages**. The goal is to clean and preserve authored structure, visual intent and supported behavior as a reusable intermediate page model, then generate **standalone semantic HTML + CSS + JS only when interactions require it**. Target-specific component/CMS mapping can be added later without changing source parsing. We are **not** implementing the other SharePoint page families in parallel.

**[Read the fidelity-first architecture and destination-mapping contract](docs/architecture/03-fidelity-first-intermediate-and-mappings.md).**

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

## PoC boundaries / next steps

1. The Modern reader **does not** support full rich-text semantics, custom SPFx parts, inline standard parts, vertical sections, live data-bound parts, authentication, page collections, or perfect site style fidelity. The demo reports unsupported parts.
2. Structural CSS is a neutral layout baseline, **not source-measured SharePoint/CDPH styling**. The opt-in demo mode is visually decorative, not a faithful migration. Fidelity will require observed CSS/computed styles and screenshots.
3. Relative image references need an explicit demo asset map or an accessible source URL. This sample bundles a small original illustration to work offline.
4. **Next: stay on Modern only.** Improve the cleanup/normalization of a messy public fixture, add source-style evidence when available, and prove a second destination mapping from the **same CIR**, while ensuring no source content silently disappears. Only then plan another source family.

No SharePoint plugins or private tenant access are needed to reproduce this demo.
