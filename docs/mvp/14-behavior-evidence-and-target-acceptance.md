# Milestone 14 — Evidence-based behavior discovery and destination acceptance

## Problem

Graph `sitePage` canvas content exposes text and web-part configuration, **not necessarily the runtime experience**. SPFx components can rely on runtime bundles, remote API calls, React state, application services, or custom scripts. It is unsafe to guess an interaction merely because a rich text block has several headings or contains links. The previous compiler intentionally required explicit author approval; this milestone makes that distinction visible in the product.

## Source evidence inventory

`poc.behavior_evidence.discover_source_interactions(ir)` records per-node:

- `runtime-evidence`: counts from the sanitized source fragment's `sourceCodeAudit` (`inlineScripts`, `externalScripts`, `inlineEventHandlers`, `unsupportedEmbeds`). The **purpose of the script is unknown**; this is review-only.
- `unresolved-web-part`: unknown controls requiring manual investigation, not migrated behavior.
- `structural-candidate`: multiple headings suitable for **reviewed** accordion/tab/on-page navigation, or a Quick Links list suitable for **reviewed** filtering. **These are not original-SharePoint interaction claims.**

Entries contain CIR `nodeId`, available `sourceRef` and evidence class. This inventory uses only the normalized CIR and never executes scripts.

## Destination static contract audit

`compare_destination_behavior(ir, html, profile, report)` independently parses emitted HTML. It verifies the mapped node has **exactly one interactive root**, panel/count structure, labels/search controls and inclusion of the vetted `behavior.js` for JavaScript controls. This catches dropped or altered elements, even when the compiler still claims it mapped them. Incorrect target markup blocks rendering; it does **not** modify the CIR.

Every result retains `sourceBehaviorVerified: false` and `browserExecutionVerified: false`. Passing static markup checks means **only** that the generated structure matches the approved mapping's contract.

`behavior-evidence.json` is part of both the `poc map` CLI output and Migration Studio ZIP export. The Studio's *Behavior evidence* tab shows full source clues, approved destination controls and unresolved controls; the quality report keeps the source-versus-destination distinction.

## Optional isolated Chromium acceptance

Run from repo root after building and mapping:

```powershell
python -m poc build --input poc/samples/modern-interactions-synthetic.json --out demo-source
python -m poc map --ir demo-source/page.ir.json --profile poc/profiles/client-navigation-filter-demo.json --out demo-target --strict
python -m pip install playwright
python -m playwright install chromium
python -m poc behavior-browser --ir demo-source/page.ir.json --html demo-target/index.html --profile poc/profiles/client-navigation-filter-demo.json --mapping-report demo-target/mapping-report.json --out demo-target/behavior-browser-report.json
```

The harness strips the known generated script reference, **rejects unknown script-bearing/browser-executable markup**, blocks all network access and injects only the compiler-owned reviewed `BEHAVIOR_JS`. It exercises tabs via click and arrow-key focus, native accordion toggling, filtering and clearing search, and navigation links at desktop (1440px) and mobile (390px). The browser test is optional because GitHub's standard CI does not install Chromium.

The report is called `behavior-browser-report.json`. It reports **destination interactions only**. The original SharePoint site was not observed in a browser, and appearance/behavior parity is **unverified**. No private tenant export or credentials are required.

## Source grounding and remaining limits

- [Microsoft Graph canvasLayout](https://learn.microsoft.com/en-us/graph/api/resources/canvaslayout?view=graph-rest-1.0): public modern page structure and web-part relationships, not full client-side runtime state.
- [SPFx client-side JS dependencies](https://learn.microsoft.com/en-us/sharepoint/dev/spfx/web-parts/guidance/use-existing-javascript-libraries): bundles and external dependencies may be needed at runtime.
- [W3C ARIA APG accordion](https://www.w3.org/WAI/ARIA/apg/patterns/accordion/) and [Disclosure](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/): reference interaction and keyboard expectations.

**Remaining release gates:** matched browser captures and observed interaction scripts from *authorized* source pages, target browser automation in CI, coverage of actual SPFx properties and data-dependent controls, broader accessibility testing and security review. No assertion of original-source parity from synthetic/public documentation samples.
