# Milestone 08 — Clean presentation compiler (Modern SharePoint only)

## Product goal

The goal is **maintainable output**, not relocating SharePoint's markup and script baggage into a different repository. Different destination clients choose their own design system, or preserve vetted source formatting. Both paths use the **same versioned CIR** and report deliberate styling/behavior omissions.

## What the first compiler actually does

1. Parse rich HTML from Modern Graph `textWebPart.innerHtml` (including public-format adaptations). A strict rich HTML serializer handles safe content markup.
2. Use `tinycss2` to parse inline CSS declarations into structured tokens. Retain only an explicitly reviewed set of typography/color/spacing properties with constrained values. Never copy arbitrary selectors, `@import`, `url()`, positioning, animation, CSS functions, escaped values, `!important` or CSS custom properties.
3. Deduplicate by **canonical property/value hash**, generating `mig-s-xxxxxxxxxxxx` classes and deterministic `source-styles.css`. Preserve rules in `richText.props.styleRules`, independent of the source framework. The renderer validates each declaration and recomputes the hash **even for independently supplied CIR**.
4. Inventory source `<script>`, `<style>`, external `<script src>`, `<link rel="stylesheet">`, inline event handlers, and embeds by **count only**. The report never contains raw code or temporary signed URLs. Raw JavaScript is **not copied or executed**.
5. Export `presentation-report.json` for source and destination. It captures compiler policy, rules emitted/omitted, review-required behavior, and the explicit limits of the scan.
6. Let each destination profile set `stylePolicy`: `target` (default: client's design system controls appearance; source classes intentionally removed) or `source-safe` (emit reviewed source formatting in a separate stylesheet). Structural output uses `source-safe`.

### CLI/local interface

```powershell
python -m pip install -r requirements-dev.txt
python -m studio --port 8765
```

Select **Styles & scripts cleanup**. Under **Authored stylesheet policy**, compare **Use client design system** versus **Preserve safe source formatting**, then open the new **Styles & scripts** tab. Exported ZIP includes `presentation-report.json` and, for source-safe content with declarations, `source-styles.css`.

Offline build:

```powershell
python -m poc build --input poc/samples/modern-styles-scripts-demo.json --out demo-styles
```

Optional CLI comparison of client-redesign vs. safe source typography:

```powershell
python -m poc map --ir demo-styles/page.ir.json --profile poc/profiles/client-example.json --out demo-client-design
python -m poc map --ir demo-styles/page.ir.json --profile poc/profiles/client-example-source-safe.json --out demo-preserved-typography
```

The first output intentionally uses client design tokens; the second retains reviewed rich-text source declarations. Both include a presentation report, and the second includes `source-styles.css`.

The sample is synthetic and Graph-shaped: it is *not* a verified SharePoint tenant capture.

## Fidelity/security gates (not yet met)

- **Source CSS files:** SPFx SCSS/CSS Modules, site themes, custom action injection, style tags, external sheets, global CSS specificity and `@media` queries are *not* imported or evaluated. They require typed source adapters, dependency capture and browser-computed-style evidence, not broad allowlisting.
- **Behavior:** Scripts/events are inventory only. We will map known behavior to reviewed components with explicitly authored JS where required, using interaction/effect tests. Arbitrary JS rewriting is out of scope.
- **CSS safety:** This is a narrow declaration compiler, **not** a general-purpose browser CSS sanitizer. A full security review and maintained HTML sanitizer are still prerequisites for production untrusted data.
- **Visual parity:** Preserving a CSS declaration does **not** prove visual fidelity. The source page's cascade, font availability, DOM structure, responsive rules, and component scripts matter. Target-redesign policy does not claim source fidelity by design.
- **Scale:** Current limits include 4 KB per source style attribute, 256 distinct style rules per page, 1 MB rich HTML per part. Exceeding limits stops compilation or triggers omission/review, rather than attempting unsafe heuristics.

## Research sources

- [Microsoft — SPFx Sass/CSS and locally scoped modules](https://learn.microsoft.com/en-us/sharepoint/dev/spfx/web-parts/get-started/connect-to-sharepoint)
- [MDN — CSS cascade and specificity](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Cascade)
- [MDN — CSS cascade layers](https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Styling_basics/Cascade_layers)
- [OWASP — XSS Prevention (sanitization and post-sanitization mutation)](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [OWASP — DOM-based XSS Prevention (untrusted JS must not be executed)](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html)
- [tinycss2 parser documentation](https://doc.courtbouillon.org/tinycss2/latest/)

## Next technical focus

A **style-dependency graph** that captures user-provided CSS bundles/URLs under an operator-approved acquisition policy, finds selector usage against a captured DOM, preserves media queries where verified, extracts design tokens/components, and reports visual differences across viewports. Then a **behavior compiler** driven by approved behavior descriptors, not source JS. Each engine must have source fixtures, adversarial tests, measurable quality reports and browser parity checks before release.
