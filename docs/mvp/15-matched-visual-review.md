# Milestone 15 — Matched visual review (screenshot evidence, not automatic fidelity approval)

## Why

Migration Studio already validates supported semantic content, asset references, emitted CSS, and the **destination** interactions. This milestone adds an explicit **source-versus-output visual review** that does not confuse a cleanly compiled destination with a faithful replica of the SharePoint original.

A reviewer who is authorized to view the source page provides a **PNG full-page screenshot** captured at a known CSS viewport width. The source page is not fetched by the tool, and source JavaScript never executes in Migration Studio. The destination output is captured offline using Chromium's static HTML/CSS renderer, with **JavaScript disabled and all network requests blocked**. Source and destination screenshots must be aligned to the **same width** and are never resized to conceal differences.

## Local Studio workflow

1. Run `python -m pip install -r requirements-visual.txt`, then `python -m playwright install chromium` (or use an installed Chromium browser). On Windows, run these from the repo root.
2. Start `python -m studio --port 8765` and analyze a Modern page, then **Generate destination**.
3. In **Visual comparison**, choose `1440` or `390` pixels. Supply a source PNG screenshot captured at the **same width** in a browser on the original page, under comparable state, fonts, consent banners, viewport scaling and content data. Prefer full-page captures. Use only screenshots you are authorized to handle.
4. Select **Compare source and destination**. The Studio builds a fresh Chromium capture of the selected generated output using the existing offline browser-audit harness. The local UI displays an amber region where full-page heights differ and red changed pixels where channels differ beyond threshold 24.
5. Review **largest changed tiles**, whole-image geometry mismatch, altered pixels within the overlapping area, unresolved source components, and behavioral evidence separately. Repeat with the other viewport.
6. Export the ZIP. **Only `visual-review.json` numeric metrics and image SHA-256 fingerprints are packaged**. Neither the supplied baseline, output screenshot nor derived heatmap is bundled. The canonical IR is unchanged.

This is a local prototype. Review uploaded screenshot sensitivity before handing around the browser tab or export; the heatmap preview does derive from the original image and remains in the page while it is displayed. The project and report live in process memory until restart. A full quality workflow will need reviewer sign-off, source screenshot capture metadata, deterministic rendering controls, and provenance validation.

## CLI workflow

```powershell
python -m pip install -r requirements-visual.txt
python -m playwright install chromium
python -m poc browser-audit --html demo-target/index.html --out browser-review
python -m poc visual-compare --source-png authorized-source-desktop.png --target-png browser-review/desktop.png --viewport-width 1440 --out visual-review
python -m poc visual-compare --source-png authorized-source-mobile.png --target-png browser-review/mobile.png --viewport-width 390 --out visual-mobile-review
```

CLI writes a `visual-review.json` and `difference-heatmap.png`. It does not copy the original screenshot into the review output directory. The heatmap **may still contain derived source information**, so handle it at the original screenshot's sensitivity level. The generated target may require image dependencies to be present in the same directory as `index.html`.

## Comparison contract

- Required **single-frame PNG**, up to 5 MB per image for CLI; Studio UI restricts uploads to 1.5 MB.
- Dimensions bounded to 100–3000 width, 100–16000 height, up to 18 million pixels; the width must equal the declared viewport. Studio supports `390` and `1440`; the standalone API/CLI also accepts `768` and `1024`.
- RGB channel difference is computed in the overlapping area, using the **maximum per-channel delta**; threshold defaults to 24 (0–100 supported). Large pixels with a higher channel delta are marked changed.
- Height differences contribute an **unmatched fraction**, not cropped or resized away. The combined metric separately accounts for changed overlap pixels and unmatched rows.
- Reports identify up to ten high-change 256 × 256 tiles and the changed overlap bounding rectangle. No CSS selector or element attribution is inferred from pixels.
- A visually identical screenshot still yields `releaseApproved: false`, `reviewRequired: true`, `sourceBaselineVerified: false`, and `fidelity: not-verified-human-review-required`.
- Static capture uses JS disabled. Browser behavior acceptance remains a separate gate and original SharePoint source behavior remains unverified until supported by actual observations.

## Quality gates and boundaries

**Testable now:** size/decode constraints; strict viewport alignment; exact-image zero-change sanity test; changed-pixel bounding regions; full-page height mismatch; export privacy; unchanged CIR; desktop offline browser capture.

**Not proven by this milestone:** pixel-perfect fidelity to the original site, screenshot authenticity, accessible behavior parity, correct links/assets not present in captures, anti-aliased/font consistency across environments, matched dynamic state, or production security readiness. Diff scores have no universal good/bad threshold; reviewers must reconcile acceptable target redesign with required source preservation.

**Future work:** baseline capture provenance (`source URL`, authorized capture date, browser/version/fonts/state); opt-in controlled capture through an approved connector (not credentials in the repo); DOM/component-level region mapping; automated reviewer annotations/sign-off; independent testing on approved real pages.
