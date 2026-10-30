# Milestone 09 — external CSS workbench and browser-render gate

**Status:** offline implementation / reviewed candidates only. This is **not** a complete SharePoint stylesheet transformation, SPFx execution environment, or a visual-fidelity pass.

## Why this exists

The previous compiler converted a small set of safe **inline** declarations to reusable classes. Real SharePoint sites may also use branding CSS, page-layout CSS, theme variables, SPFx component styles, responsive media queries, linked stylesheets and JavaScript. Copying these uncritically to a different client website creates fragile layouts, global selector collisions and security risks. Deleting them unconditionally can change appearance or behavior.

Microsoft/MDN CSS references explain that `@media`, `@supports`, `@container`, `@layer` and `@import` affect rule applicability and ordering, and the cascade cannot be inferred from a subset of selectors alone. tinycss2 parses CSS *syntax*, not computed styles or browser semantic matching. Primary references:

- https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Syntax/At-rules
- https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Cascade/Introduction
- https://doc.courtbouillon.org/tinycss2/latest/api_reference.html
- https://playwright.dev/python/docs/screenshots

## `css-workbench` contract

The operator supplies a local CSS file explicitly. **No URL fetching occurs**, including `@import`. The source input is size-limited (200 KB) and parsed using tinycss2. The analysis records basic rule counts, rejected features, candidate color tokens, observed output tags, supported media conditions and a SHA-256 digest for reproducibility. Unsafe or unsupported selector text is represented by a hash in the report, not copied into the compiled sheet.

Only plain semantic HTML tag selectors (`p`, `h2`, `p a`, etc.) with at most two descendant relationships are accepted. A conservative property whitelist reuses the existing inline declaration sanitizer. Simple `(max-width: Npx)` and `(min-width: Npx)` conditions are kept as responsive blocks; complex media, nested conditions, container/supports queries, CSS layers, fonts, imports, custom properties, arbitrary SharePoint selectors, pseudo-selectors and `url()` dependencies are **review-only**. Styles are scoped to `:is(.rich-text,.target-body)` and are **not** automatically linked into any generated page. `reviewed-candidates.css` and `css-review.json` are review artifacts only. Report status is always `review-required`.

This should evolve into a design-token analyzer, selector mapping registry, lossless dependency graph and browser CSSOM comparison. The current restrictions are intentional safeguards, not claims of support for arbitrary authored CSS.

## Browser gate contract

`browser-audit` uses optional Chromium/Playwright to render the **generated page only**, at desktop (1440px) and mobile (390px) widths. It disables page JavaScript and aborts all HTTP requests; relative CSS is injected from the local output directory and safe local image bytes are inlined as data URLs. It records screenshot hashes, image loading state, heading counts, first-heading computed text style, and horizontal overflow. It is a **structural smoke test**, not a matched screenshot comparison or interaction evaluation. Live SharePoint visual fidelity and browser accessibility audit remain separate future gates.

## Windows commands

```powershell
python -m poc build --input poc/samples/modern-styles-scripts-demo.json --out demo-styles
python -m poc map --ir demo-styles/page.ir.json --profile poc/profiles/client-example.json --out demo-client
python -m poc css-workbench --css poc/samples/public-stylesheet-review-demo.css --html demo-client/index.html --out css-review
# Optional browser tooling (Chromium or Playwright managed browser also needed):
python -m pip install playwright
python -m playwright install chromium
python -m poc browser-audit --html demo-client/index.html --out browser-review
```

Migration Studio also offers a CSS file review in the **Styles & Scripts** tab after output generation. The review files are included in subsequent ZIP exports but deliberately do not change the rendered page.

## Acceptance gates demonstrated

- Validates and bounds CSS and HTML input sizes; never executes source scripts or source CSS imports.
- Preserves narrow responsive `min-width`/`max-width` conditions and property order within emitted reviewed candidates.
- Keeps source/CIR and existing HTML immutable during stylesheet review.
- Exports decisions and explicitly labels unsupported constructs.
- Tests malicious CSS/selector cases and measures output at two viewports in Chromium, when installed.
- **Not approved:** visual parity, real SharePoint stylesheet loading, computed source CSS matching, SPFx component script migration, and production CI (until remote workflows pass).
