# SharePoint → Intermediate Representation → HTML (PoC 01)

A **working offline proof of concept** for migrating a small subset of *Modern SharePoint Site Pages* into clean JSON and a standalone responsive webpage. The longer research phase (three families total) is documented in the separate draft research PR.

## Demo (Python 3.10+, no dependencies or SharePoint login)

```sh
python -m unittest discover -s tests -v
python -m poc build --input poc/samples/modern-demo.json --out demo
python -m http.server 8000 --directory demo
```

Open `http://localhost:8000`. All output is written to `demo/index.html`, `demo/style.css`, `demo/page.ir.json`, `demo/report.json`, plus a bundled SVG in `demo/assets/`.

To run against a **compact sample adapted from Microsoft's published GET sitePage response**:

```sh
python -m poc build --input poc/samples/microsoft-graph-doc-example.json --out demo-doc
```

## Current supported input and output

- Input: **JSON shaped like Graph `microsoft.graph.sitePage` expanded with `canvasLayout`**; no API calls and no credentials.
- Extract: `titleArea`, `horizontalSections`, 12-grid columns, `textWebPart.innerHtml`, standard **Image** and **Quick Links** web parts.
- Normalize: semantic `page` → `section` → `columns` → `column` → `richText` / `image` / `linkList`, with source web-part IDs and fidelity flags.
- Output: reusable CIR JSON, standalone responsive HTML/CSS, local demo asset and diagnostics/report.
- Unknown parts: explicit `unknown` blocks plus `UNMAPPED_WEBPART` diagnostics; do not silently discard.
- Safety: basic allow-list rich HTML sanitation, URL scheme filtering, escaping, offline generated output; no arbitrary source script execution. This is **not** a production security boundary.

## Sources and honesty about provenance

The two input samples are **public-documentation-adapted examples**. The schema and field placements come from Microsoft's [sitePage GET](https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0), [sitePage create](https://learn.microsoft.com/en-us/graph/api/sitepage-create?view=graph-rest-1.0), and [standardWebPart](https://learn.microsoft.com/en-us/graph/api/resources/standardwebpart?view=graph-rest-1.0) documentation. The modern showcase's prose, identifiers, Quick Links, and offline illustrative SVG are authored for the demo; **they are not CDPH data or an authenticated SharePoint export**. The compact documentation sample was adapted into parseable JSON from the published illustration.

A public PnP CLI fixture and public classic ASPX source examples are discussed in the companion research PR for later Classic Content and Publishing adapters.

## Verified local demo result

The showcase contains **4 source web parts**, of which **3 map** to CIR controls (rich text, image and Quick Links) and **1 remains explicitly unsupported** (75% fixture mapping coverage). This is not an accuracy score or a claim about real SharePoint sites. The test suite has **8 passing unit tests locally**, and a local browser render confirmed the header, links and bundled illustration. GitHub-hosted CI has reported a failure with missing remote logs; it is not confirmed passing.

The draft [CIR v0.1 JSON Schema](schema/page.ir.schema.json) is included for structural review.

## PoC boundaries / next steps

1. The Modern reader **does not** support full rich-text semantics, custom SPFx parts, inline standard parts, vertical sections, live data-bound parts, authentication, page collections, or perfect site style fidelity. The demo reports unsupported parts.
2. CSS is new, portable demonstration styling, **not CDPH or SharePoint CSS**.
3. Relative image references need an explicit demo asset map or an accessible source URL. This sample bundles a small original illustration to work offline.
4. Next: test more public modern Graph fixtures; add Classic Wiki/Web Part and Publishing parsers with matching raw public examples, preserving template and style references; validate the CIR schema rigorously and improve accessibility/content coverage.

No SharePoint plugins or private tenant access are needed to reproduce this demo.
