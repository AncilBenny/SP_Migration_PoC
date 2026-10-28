# PoC increment 05 — public CanvasContent1 cleanup, provenance and client URL/asset mapping

Date: 2026-10-28. Scope: ONE **Modern SharePoint** source family. No tenant access, SharePoint plugin, or private data.

## This is the core outcome

SharePoint/PnP **CanvasContent1** -> decode serialized, HTML-entity-encoded control data -> normalized Modern canvas -> the **same generic CIR** as Graph -> either neutral HTML/CSS or a client-target mapping profile. We explicitly do not build Classic or Publishing readers now.

### Input A: actual publicly published source fixture

- File: `poc/samples/pnp-canvas-public.json`.
- Original: [PnP CLI for Microsoft 365 page-get.mock.ts](https://github.com/pnp/cli-microsoft365/blob/main/src/m365/spo/commands/page/page-get.mock.ts), blob `f1f42408a85769d95ef52e04ef37a000e557576a`, public MIT-licensed project (license retained at `poc/samples/PNP-LICENSE.txt`).
- `ListItemAllFields.CanvasContent1` is copied from the project's **public test fixture**; the wrapper URL/title/source provenance are authored solely for offline testing. It is **not a live SharePoint capture**.
- The fixture includes `data-sp-controldata`, `data-sp-webpartdata`, `data-sp-htmlproperties` and an unsupported custom web part. Our decoder extracts its position/type/id and preserves it as an explicit `unknown` with `capturePointer` and diagnostics, rather than executing arbitrary web-part code or incorrectly turning its processed inner HTML into authored static content.
- The fixture's `pageSettingsSlice` is source metadata, not a visible web part; it is ignored by the authored-body renderer.

### Input B: adapted Modern documentation sample with internal links

- File: `poc/samples/modern-internal-links.json`.
- Synthesized/adapted from published Microsoft Graph Site Page examples with additional authored **internal link test cases**. It is not a tenant export. Relative source links resolve using the originating `webUrl`.
- Source `https://example.org/sites/demo/SitePages/service.aspx` becomes `/knowledge/service.aspx` under the example client profile. A rich-text link to `service.aspx?mode=overview#steps` preserves query/fragment. A bundled image changes from `assets/health.svg` to `media/health.svg` in target output only.

## CLI demo

    python -m unittest discover -s tests -v
    python -m poc build --input poc/samples/pnp-canvas-public.json --out demo-pnp
    python -m poc build --input poc/samples/modern-internal-links.json --out demo-rewrite
    python -m poc map --ir demo-rewrite/page.ir.json --profile poc/profiles/client-example.json --out demo-mapped
    python -m http.server 8000 --directory demo-mapped

The generated `demo-mapped/mapping-report.json` contains:
- `nodeMappings` — each IR node ID, its generic kind, sourceRef and target component.
- `urlRewrites` — node ID, source URL and target URL (only when a URL actually changes).
- `assetRewrites` — node ID and original/target local asset paths.
- `mappingWarnings` — explicit unknown or unsafe components.
- `irSha256` — original input CIR byte hash; the same CIR bytes are copied unchanged to mapped output.

## Mapping profile constraints

- URL rules are **destination-specific**, not stored as changes to source CIR.
- `sourcePrefix` must be an absolute HTTPS URL ending in `/`. Matching compares the exact scheme and host plus a path prefix, preventing lookalike domains and `/sites/demolition` from accidentally matching `/sites/demo/`.
- `targetPrefix` must be an HTTPS URL or root-relative path ending in `/`, with no injected script scheme or open protocol-relative URL.
- Internal rich-text anchors and structured Quick Links receive the same mapping rule.
- `assetDirectory` is limited to a safe, simple output folder name; the example profile uses `media`.
- External links not matching rules remain unchanged. Unsupported controls remain diagnosed.

## What this does NOT yet solve

1. The published CanvasContent1 example has an unsupported custom web part, not a fully reconstructible static article. Its processed HTML is not treated as safe evidence of the entire web-part behavior.
2. Only known canvas control positions and two standard webpart types are decoded. Arbitrary nested canvas fragments, classic zones, mobile positioning and source-generated style overrides are **not** fully supported.
3. Client-target mapping currently outputs independent HTML and CSS only. Rich dynamic behaviors, client CMS API integration, and JavaScript generation are deferred.
4. There is no matching rendered SharePoint screenshot/CSS for the public fixture; **pixel or visual fidelity is unverified**. Client-target redesign is intentional and should be evaluated against *client acceptance requirements*, not a source pixel match.
5. Do not interpret fixture unit tests as production migration coverage. The workflow runs have previously been failing in GitHub; passing status is not claimed unless GitHub confirms it.

## Next single-page PoC gate

Strengthen content-loss accounting in the **same Modern adapter**: block-level visible text inventory; distinguish known content from unsupported web-part text; map image/link metadata to client controls; test a public source DOM+CSS baseline when a matching modern page is publicly accessible. Do not broaden to the other SharePoint families yet.
