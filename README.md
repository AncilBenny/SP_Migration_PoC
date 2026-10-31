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

## MVP product shell: Migration Studio (local-only)

Run on Windows PowerShell or macOS/Linux **from the repository root**:

```powershell
python -m unittest discover -s tests -v
python -m studio --port 8765
```

Open **http://127.0.0.1:8765/**. The app offers: public sample or local JSON import (3 MB max), IR inspection, structural/client-mapped target selection, component mapping for Quick Links, brand color and heading settings, sandboxed generated preview, validation report and downloadable HTML/CSS/assets/IR ZIP. The preview and export are generated locally; no tenant access or plugin is needed. Projects are in memory and cleared on restart. **This is a local MVP scaffold, not a deployed service.**

The `/api/capabilities` endpoint lists engine maturity and research evidence. `quality-report.json` distinguishes passing **supported-content checks** from **release approval**: migration outputs stay `review-required` when fidelity has not been independently verified, and become `blocked` when supported content/assets are actually lost. An unsupported web part always needs manual review.

Read [Engine research and quality gates](docs/mvp/01-engine-research-and-quality-gates.md) for Microsoft Graph, PnP, SharePoint page model and assessment sources; implementation gaps and product readiness conditions are tracked explicitly. Our goal is to build competitive, research-backed engines, **not to claim that the current public-fixture prototype is production-grade**. GitHub CI failure remains unresolved; local Python unit/API tests are not a substitute for CI, browser fidelity, security audit or approved real-site tests.

## MVP engine hardening: versioned CIR v0.2 and audited rich text

New source runs generate **CIR 0.2.0** (Draft 2020-12 schema at
`schema/page.ir.v0.2.schema.json`), with fail-closed contract validation
at rendering/mapping boundaries. **Rebuild older `page.ir.json` files** from
source; `0.1.0` files are deliberately not silently upgraded. `poc/contracts.py`
checks node IDs, safe bounded trees, layouts, required content and assets.

The audited rich-text serializer now preserves safe inline images, figure
captions, table headers and bounded cell spans, and reports removed markup /
URLs plus unresolved inline image asset handling. It is not a full browser
sanitizer; production security reviews and a maintained HTML5/DOM sanitizer
remain necessary. Neither output path claims pixel-perfect source fidelity.

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m poc build --input poc/samples/modern-rich-layout-public-adapted.json --out demo-modern
python -m poc map --ir demo-modern/page.ir.json --profile poc/profiles/client-example.json --out demo-target
python -m studio --port 8765
```

[See the evidence, contract and explicit remaining release gates](docs/mvp/03-cir-v02-contract-and-richtext.md).


## MVP destination roots and asset dependencies

Client profiles now support typed `rootMappings` for **page, image and document** links, with optional `.aspx` removal for page URLs. The `poc/profiles/cdph-root-routing-example.json` profile demonstrates a common source root mapped into three different destination roots (illustrative only). Configure roots directly in Migration Studio under **URL roots · pages / images / documents**. Old `urlMappings` profiles remain supported.

`dependency-manifest.json` records verified bundled bytes and explicitly unverified remote URLs. `acquisition-plan.json` lists what the page would need to fetch. Public-file acquisition requires an explicit allowlist and is **not** performed during web preview or export:

```powershell
python -m poc pull --ir demo/page.ir.json --profile poc/profiles/cdph-root-routing-example.json --out pulled-assets --plan-only
python -m poc pull --ir demo/page.ir.json --profile poc/profiles/cdph-root-routing-example.json --out pulled-assets --allow-host www.cdph.ca.gov
```

The second command is an opt-in public HTTPS fetch, not a tenant-authenticated SharePoint migration. It never uploads to the target host. See [asset routing, acquisition and security limitations](docs/mvp/04-dependency-routes-public-pull.md).

## Graph driveItem asset resolution (offline MVP)

The optional `graph-plan` command reconciles referenced page images and documents
against **supplied Microsoft Graph v1.0 driveItem metadata**. It is separate
from the public-only HTTP puller and does **not** ask for tokens, contact a
SharePoint tenant, or claim any assets were downloaded or published.

```powershell
python -m poc build --input poc/samples/modern-cdph-routes-demo.json --out demo-graph
python -m poc graph-plan --ir demo-graph/page.ir.json --drive-items tests/fixtures/graph-drive-items-offline-demo.json --profile poc/profiles/cdph-root-routing-example.json --out demo-graph/graph-acquisition-plan.json
```

The self-authored fixture deliberately resolves **3 of 4** file references;
the remaining `.docx` is explicitly unresolved. `poc.graph_assets.stage_graph_files`
supports an injected **authorized** byte provider for isolated integration tests,
with SHA-256 and post-write verification; it includes **no live Graph OAuth or
file-download implementation**. See
[`docs/mvp/05-microsoft-graph-driveitem-asset-resolver.md`](docs/mvp/05-microsoft-graph-driveitem-asset-resolver.md).

## MVP milestone 06: authorized Graph transport and verified local publication

A **server-side, opt-in** `GraphBinaryFetcher` now supports Microsoft Graph `/drives/{driveId}/items/{itemId}/content`, supplying the bearer token only to `graph.microsoft.com`. Temporary 302 download redirects require an **exactly allowlisted public HTTPS hostname**, have **no Authorization header**, and are never stored. DNS is checked for public-only addresses and pinned to the TLS connection; redirects, proxies, and oversized responses are blocked. Microsoft Graph throttling receives bounded Retry-After/backoff handling.

`python -m poc graph-stage` stages real Graph bytes only when an independently authorized token is available through the specified environment variable; no credentials are built in or required for public-fixture tests. `python -m poc graph-publish-local` then copies verified staged bytes into a local destination package and **reads them back for SHA-256 verification**. A local package is **not** evidence of a live website/CDN/cloud publication; this remains a separate adapter and integration gate.

See [Graph transport security and publication states](docs/mvp/06-authorized-graph-transport-and-publication.md). All network tests in this branch use injected mock transport; **no live SharePoint tenant** was contacted. Never commit tokens, signed URLs or private tenant exports.

## Optional Entra delegated authorization (MVP milestone 07)

For **authorized operator-driven Graph file staging**, use an approved **single-tenant public desktop client registration**, a browser-based MSAL login, and a delegated read scope. The default is `Files.Read`; all broad, write and `.default` scopes are rejected by this narrowly scoped adapter. `Sites.Selected` requires independent admin consent and resource-level assignment; a requested scope is **not proof** of access.

```powershell
python -m pip install -r requirements-auth.txt
# Set MIGRATION_ENTRA_TENANT_ID and MIGRATION_ENTRA_CLIENT_ID outside the repository.
python -m poc graph-auth-check
python -m poc graph-stage --plan path/to/authorized-plan.json --out private-staged --allow-download-host your-approved-download-host.example --auth-mode entra-delegated
```

`graph-auth-check` makes **no** network requests and never returns a token. The existing environment-token staging option remains available for separately authorized integrations. **Do not use synthetic Graph catalog IDs for a live stage.** See [MSAL & least-privilege design, operator requirements and limitations](docs/mvp/07-entra-least-privilege-authentication.md). This is a local operator adapter, **not a hosted enterprise identity system**.

## MVP milestone 08 — Clean website presentation compiler

The local Studio now has a **Styles & scripts cleanup** sample, an **Authored stylesheet policy** selector, and a **Styles & scripts** report tab. Safe inline rich-text styles are parsed with `tinycss2`, deduplicated into deterministic classes, and optionally exported as `source-styles.css`. The default client mapping **intentionally uses client styles**, while structural output preserves reviewed source formatting. Scripts, handlers, and embedded stylesheets are inventoried for manual mapping and are never copied as executable output. Every output receives `presentation-report.json`.

Install compiler dependency: `python -m pip install -r requirements-dev.txt`. This is a **narrow inline-declaration compiler**, not full SPFx CSS extraction, stylesheet dependency processing, arbitrary JavaScript translation, visual-parity verification, or production-ready HTML sanitization. For architecture, limits, and research evidence see [docs/mvp/08-clean-presentation-compiler.md](docs/mvp/08-clean-presentation-compiler.md).


## Stylesheet workbench and responsive browser gate (MVP milestone 09)

In addition to compiling safe **inline** formatting, the product now accepts **explicitly supplied external stylesheet files** for offline analysis. `css-workbench` identifies simple semantic CSS candidates, limited responsive media rules, safe properties and color tokens; it reports SharePoint-specific selectors, fonts, imports, scripts and complex conditions for review. It never fetches source CSS URLs or applies the proposed output automatically.

```powershell
python -m poc css-workbench --css poc/samples/public-stylesheet-review-demo.css --html demo-client/index.html --out css-review
```

Open `css-review/css-review.json` (decisions) and `css-review/reviewed-candidates.css` (reviewable scoped CSS). Migration Studio's **Styles & Scripts** tab includes a CSS upload/review workflow, adding these files to the export without modifying the actual page.

An optional browser check renders generated output at desktop and mobile sizes without executing JS or making outbound requests:

```powershell
python -m pip install playwright
python -m playwright install chromium
python -m poc browser-audit --html demo-client/index.html --out browser-review
```

Outputs `desktop.png`, `mobile.png`, `browser-audit.json`. This is **not** a source-screenshot parity or accessibility test. See [Milestone 09 CSS workbench and browser gate](docs/mvp/09-css-workbench-and-browser-gate.md).


## MVP milestone 11: reviewed SharePoint CSS selector → destination component mapping

CSS from an actual SharePoint source can use runtime-specific selectors that are meaningless on a different client's website. The `css-workbench` now optionally accepts an **explicit, versioned selector mapping manifest** (`--selector-map`), converting those rules into safe, maintainable component-owned candidate styles. Source selectors never appear in generated CSS. Target components must be recognized and present in the generated HTML; unsafe declarations and unrecognized selectors remain review-only. **No source CSS is auto-applied.**

```powershell
python -m poc build --input poc/samples/modern-demo.json --out demo
python -m poc map --ir demo/page.ir.json --profile poc/profiles/client-example.json --out demo-client
python -m poc css-workbench --css poc/samples/modern-selector-component-demo.css --html demo-client/index.html --selector-map poc/profiles/modern-selector-component-map.json --out css-component-review
```

The sample selectors and style content are **synthetic illustrative examples**, not a verified customer SharePoint stylesheet. In the local Migration Studio UI, attach the `.css` and optional `.json` selector map in **Styles & scripts**. Exports include the review manifest and candidates but do not change the page or CIR. Details: [CSS selector/component mapping, safety and fidelity limits](docs/mvp/11-css-selector-component-mapping.md).

## MVP milestone 12: explicit behavior compiler (accessible accordions and tabs)

Target profiles can now include a reviewed `behaviorMappings` list. Each entry names a **CIR richText node** with 2–20 simple top-level `h2`/`h3` sections and requests an `accordion` or `tabs` target. We do **not** migrate SharePoint scripts or infer behavior from arbitrary source code. Unsupported structures fail with a clear message; the CIR stays unchanged.

```powershell
python -m poc build --input poc/samples/modern-interactions-synthetic.json --out behavior-source
python -m poc map --ir behavior-source/page.ir.json --profile poc/profiles/client-behavior-demo.json --out behavior-target --strict
python -m http.server 8008 --directory behavior-target
```

Open http://127.0.0.1:8008/ for the standalone interactive demo. Native accordions need no JS; tab mappings generate one fixed `behavior.js` file with keyboard interactions and a no-JS fallback. In Migration Studio, choose the **Accessible behaviors** sample, inspect its rich-text nodes and select an explicit interaction under destination settings. The sandboxed Studio iframe intentionally does not run JavaScript; export the page to test the actual tab behavior.

The sample is synthetic and its accordion/tabs are **intended destination behaviors**, not a measured copy of a real SharePoint runtime. Visual parity, custom SPFx behavior, and assistive-technology compatibility still require review. Read [Milestone 12 research and validation](docs/mvp/12-accessible-behavior-compiler.md).

## MVP milestone 13: page navigation and filtered Quick Links

An explicitly reviewed `behaviorMappings` profile can now produce a **no-script table of contents** from a safe rich-text heading sequence and a **progressively enhanced Quick Links filter** from an existing link-list node. The filter's JavaScript is application-owned and only operates on already-rendered links; it does not copy SharePoint scripts or call remote services. Generated navigation stays outside the source-content validation marker, preserving independent content accounting. The source CIR remains immutable.

```powershell
python -m poc build --input poc/samples/modern-interactions-synthetic.json --out demo-navigation-source
python -m poc map --ir demo-navigation-source/page.ir.json --profile poc/profiles/client-navigation-filter-demo.json --out demo-navigation-client --strict
python -m http.server 8000 --directory demo-navigation-client
```

See [reviewed navigation and filtering contract](docs/mvp/13-reviewed-navigation-and-filtering.md). This is a reviewed destination interaction prototype, not automatic reconstruction of arbitrary SPFx behavior. Browser acceptance and matched source fidelity remain release gates.

## MVP milestone 14 — Behavior discovery and independently checked output

After compiling a target, inspect `behavior-evidence.json` or the **Behavior evidence** tab in Migration Studio. The report distinguishes source script evidence, structural authoring candidates, unsupported web parts, approved destination mappings and static HTML contract failures. No source scripts are executed or copied, and heading structure alone never proves tabs or accordions existed in SharePoint.

An optional offline Chromium command checks the generated destination's controls at desktop and mobile widths; see [Behavior evidence and target acceptance](docs/mvp/14-behavior-evidence-and-target-acceptance.md). Source-versus-destination behavior and visual parity remain **unverified** without a matched original-page baseline.
