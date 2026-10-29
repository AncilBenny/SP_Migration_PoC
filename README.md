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

For **authorized operator-driven Graph file staging**, register an approved **single-tenant public desktop client**, then use MSAL browser-based login with a delegated read scope. The default is `Files.Read`; this adapter rejects all broad, write and `.default` scopes. `Sites.Selected` additionally requires resource grants and approved consent—requesting a scope does **not** prove access.

```powershell
python -m pip install -r requirements-auth.txt
# Set MIGRATION_ENTRA_TENANT_ID and MIGRATION_ENTRA_CLIENT_ID via your approved local process.
python -m poc graph-auth-check
python -m poc graph-stage --plan path/to/authorized-plan.json --out private-staged --allow-download-host your-approved-download-host.example --auth-mode entra-delegated
```

`graph-auth-check` makes **no network calls**, prints no identifiers or tokens, and explicitly reports that permissions remain unverified. An existing env-token mode remains available for separately authorized operators. Synthetic metadata fixtures are **not valid live Graph download plans**. See [least-privilege design, operator steps and limitations](docs/mvp/07-entra-least-privilege-authentication.md). This is an operator tool, **not a hosted enterprise identity system**.
