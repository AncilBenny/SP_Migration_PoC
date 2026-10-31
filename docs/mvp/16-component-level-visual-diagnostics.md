# Milestone 16 — Reviewable component-level visual differences

## Purpose

The screenshot comparison already shows pixels that differ between a supplied source-page PNG and an independently generated target-page PNG. A heatmap by itself cannot tell a destination developer where to start. This milestone **links affected target pixel regions back to rendered CIR nodes and destination components**, with explicit limits on attribution.

## What is measured

1. The offline Chromium audit (`python -m poc browser-audit`) captures the generated target in static HTML/CSS mode, with JavaScript disabled, external requests blocked, no browser authentication, device pixel ratio 1, and fixed desktop/mobile widths.
2. It captures bounded layout rectangles for at most 200 rendered elements with compiler-owned `data-ir-id` attributes, plus a small **target-only** computed-style probe (`fontSize`, `lineHeight`, `display`). It never records DOM text or source scripts.
3. A pixel comparison against an operator-supplied source PNG requires the same viewport width. It calculates the count/fraction of pixels with a maximum per-channel delta above the threshold inside each target element rectangle. Pixel coordinates are unscaled document coordinates.
4. Optional destination `mapping-report.json` supplies the node's target component name (for example `contentBody`, `resourceCards`, `media`). The renderer's existing node mappings remain source-independent.
5. `componentDifferences.topAffectedNodes` ranks affected rendered nodes by changed pixel count. Its entries include `nodeId`, destination component, target bounding rectangle, a computed-style probe, affected pixel counts, unmatched target rows, and a **generic inspection hint**, not a claimed correction.
6. `unattributedChangedPixels` counts changes outside all captured target node rectangles. This may represent body/background/layout issues or missing generated content. It **does not** determine why source content is absent.

## Commands

```powershell
python -m pip install -r requirements-visual.txt
python -m playwright install chromium
python -m poc build --input poc/samples/modern-demo.json --out demo-source
python -m poc map --ir demo-source/page.ir.json --profile poc/profiles/client-example.json --out demo-target
python -m poc browser-audit --html demo-target/index.html --out browser-review
python -m poc visual-compare --source-png authorized-original-mobile.png --target-png browser-review/mobile.png --viewport-width 390 --browser-report browser-review/browser-audit.json --mapping-report demo-target/mapping-report.json --out review-mobile
```

The CLI refuses a browser report unless its screenshot SHA-256 matches the provided target PNG. It refuses malformed node geometry, duplicate node IDs, invalid component labels, excess metadata, and missing viewport geometry. `--mapping-report` requires `--browser-report`. Without the optional audit files, the original pixel-only CLI continues to work.

In Migration Studio, import a Modern page, generate the destination, open **Visual comparison**, and supply an authorized source PNG at 1440 or 390 px. It captures the target offline and returns node findings inside the same `visual-review.json`; the operator can inspect the JSON in the UI or export. The source screenshot, target screenshot, and difference heatmap **are not exported** from Studio. The CLI explicitly writes a heatmap in its review directory, which may retain sensitive derived source information and should be handled accordingly.

## Key quality safeguards

- **Geometric overlap is not causal attribution.** A descendant, ancestor, or neighboring element may overlap a change caused by CSS cascade, fonts, viewport, media-loading behavior, an overlay, or a missing source component. Nested/overlapping rectangles may double-count changes in individual rows; do not sum their per-node counts as a total. The separate `unattributedChangedPixels` uses the union of covered rectangles.
- Exact image matching does not prove source-page authenticity, semantic content preservation, interaction equivalence, accessibility, or production readiness. Human review remains required even at zero changed pixels.
- The baseline is operator-supplied, not captured or authenticated by this tool. A source DOM/CSS baseline does **not** exist here; the `targetStyleProbe` is not a before/after style diff. The target page's JS is disabled in the screenshot audit, so target dynamic-interaction visual states are outside this scope.
- The diagnostic only has rectangles for rendered `data-ir-id` elements. Unmapped source controls, absent target controls, pseudo-elements, or the root background may remain unattributed.
- Source screenshots are never treated as instructions or sent to a remote service by this capability. Do not upload private screenshots to an untrusted machine or public issue.

## Evidence / acceptance gate

Local checks cover unchanged pages, deliberately changed content and background pixels, target page-height mismatch, overlapping/invalid rectangles, injected test screenshots without invented geometry, CLI screenshot-hash validation, DOM geometry capture with isolated Chromium, deterministic source IR, and export privacy. CI unit tests can run without Chromium; real browser tests are optional when the runner has Chromium available. Full source-vs-target fidelity remains unverified until authorized, matched source screenshot evidence and review sign-off exist.
