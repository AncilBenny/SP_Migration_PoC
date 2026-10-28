# SharePoint → Intermediate Representation → HTML (PoC 01)

A working public-fixture PoC for **one Modern SharePoint source**: clean IR, then independent HTML/CSS output mappings. Faithful source reproduction is one possible output; most client migrations can instead map the same generic controls into different destination components and styling. This demo uses only public documentation-adapted sample data.

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

Four web parts in the demo: three mapped, one unsupported and reported (75% fixture mapping coverage, not a production accuracy score). Eight tests passed locally. The browser preview also rendered correctly. GitHub Actions has an unresolved failure, with logs unavailable.

The draft CIR JSON Schema is available in the linked GitHub PoC branch.

## Client destination mapping — different target website from the same IR

The default `build` command produces a neutral structural HTML/CSS page, with no invented site masthead or footer. The migration engine can instead translate the **same** CIR to a different client's component choices, colors and layout without re-parsing SharePoint:

```sh
python -m poc build --input poc/samples/modern-demo.json --out demo
python -m poc map --ir demo/page.ir.json --profile poc/profiles/client-example.json --out demo-client
python -m http.server 8000 --directory demo-client
```

The `map` command reads `page.ir.json` only. The client profile creates resource cards from generic linkList content, applies target-specific styling, and writes `mapping-report.json` including a SHA-256 of the unchanged IR. Unknown source web parts remain visible as review notes. The source parser isn't imported by this conversion stage. See `docs/architecture/04-generic-target-mapping-profiles.md`.

**Evidence boundary:** public-documentation-adapted sample and locally generated HTML/CSS, no real SharePoint tenant, no source screenshot style comparison, and no verified live-site visual parity. Static content needs no JavaScript. Mapping a target profile is distinct from preserving the exact SharePoint look.

## PoC boundaries / next steps

1. The Modern reader **does not** support full rich-text semantics, custom SPFx parts, inline standard parts, vertical sections, live data-bound parts, authentication, page collections, or perfect site style fidelity. The demo reports unsupported parts.
2. The default CSS is deliberately structural, **not a measured CDPH/SharePoint visual replica**; client-target styling is configured separately.
3. Relative image references need an explicit demo asset map or an accessible source URL. This sample bundles a small original illustration to work offline.
4. Next: stay with one Modern source; validate messy public `CanvasContent1` cleanup, destination link/asset rewriting and node-level mapping coverage. Classic/Publishing adapters are deferred until this core path is solid.

No SharePoint plugins or private tenant access are needed to reproduce this demo.

## Next stage: actual public CanvasContent1 and destination URL / asset mapping

The `poc/canvas.py` adapter extracts encoded modern SharePoint control metadata from a **public PnP CLI fixture**, preserves original source-control pointers, and records unknown custom parts without executing their embedded behavior. The included public `poc/samples/pnp-canvas-public.json` is sourced from PnP CLI's MIT-licensed test fixture, not a live tenant export.

The optional client mapping profile has two URL prefixes and an `assetDirectory` setting. The adapted internal-link demo rewrites `/sites/demo/SitePages/service.aspx` to `/knowledge/service.aspx` and relocates `assets/health.svg` to `media/health.svg` while retaining the exact CIR input bytes and recording every rewrite in `mapping-report.json`.

```sh
python -m unittest discover -s tests -v
python -m poc build --input poc/samples/pnp-canvas-public.json --out demo-pnp
python -m poc build --input poc/samples/modern-internal-links.json --out demo-rewrite
python -m poc map --ir demo-rewrite/page.ir.json --profile poc/profiles/client-example.json --out demo-mapped
python -m http.server 8000 --directory demo-mapped
```

All 24 tests pass locally. CSS visual fidelity remains unverified without matched source renders. See [PoC increment notes](docs/poc/05-public-canvas-and-client-rewrites.md).

## Content-loss validation (PoC milestone 06)

We now generate a **node-by-node `quality-report.json`** for both structural and client-mapped output: original source controls are matched to CIR, then the *actual generated HTML* is checked against CIR for text, heading structure, links (including rewritten internal URLs), images, local assets and unsupported controls. `preserved`, `needs-review` and `lost` are distinct; `passed` means no detected losses in this limited semantic subset, **not** full visual fidelity or zero manual work.

PowerShell-friendly commands (one command per line):

```powershell
python -m poc build --input poc/samples/modern-internal-links.json --out demo-rewrite
python -m poc map --ir demo-rewrite/page.ir.json --profile poc/profiles/client-example.json --out demo-mapped --strict
python -m poc validate --ir demo-rewrite/page.ir.json --html demo-mapped/index.html --profile poc/profiles/client-example.json
```

Run `python -m unittest discover -s tests -v` for positive **and deliberately broken-output** tests. The validate command writes `demo-mapped/quality-check.json` and exits with code `1` if an expected component, link, heading, image or bundled asset is missing; it does not re-run the SharePoint parser. Details, limits and statuses are in [Content accounting and output checks](docs/poc/06-content-loss-and-target-validation.md).
