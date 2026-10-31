# Milestone 12 — Explicit, accessible behavior compilation

## Product decision

Destination interactions are **compiled from an explicitly reviewed CIR node mapping**, not scraped/copied from SharePoint JavaScript. Source scripts and event handlers are inventory-only evidence. A custom SharePoint Framework (SPFx) web part can depend on data, services, and runtime APIs not present in exported HTML; no automatic runtime replacement is claimed.

Supported v0.1 target behaviors:

| Target | Source requirement | Output | Browser behavior |
|---|---|---|---|
| Accordion | 2–20 top-level sibling `h2` or `h3` + nonempty content runs in one richText node | Native `<details><summary>` with original content once | Keyboard and open/close native; **no JS** |
| Tabs | Same explicit richText structure | Semantic section headings + tab container | `behavior.js` enhances on DOMContentLoaded, builds tab controls with `textContent`, keeps headings/content readable without JS |

A reviewable profile field `behaviorMappings` specifies the node ID, interaction type, heading level and initially displayed panel. **No auto-detection or AI guesses are used.** The renderer fails closed for unknown nodes, non-richText kinds, malformed HTML, nested heading ambiguity, empty panels, and unsupported interaction types. The source-independent CIR remains byte-identical.

Example (partial client profile):

```json
{
  "version": "1.0",
  "id": "client-behavior-demo",
  "behaviorMappings": [
    {"nodeId": "intro-text", "interaction": "accordion", "headingLevel": 2, "initialIndex": 0},
    {"nodeId": "feature-tabs", "interaction": "tabs", "headingLevel": 2, "initialIndex": 0}
  ]
}
```

The full runnable profile is `poc/profiles/client-behavior-demo.json`; the source is `poc/samples/modern-interactions-synthetic.json`. **Both are self-authored demonstration data, not captured SharePoint behavior.**

## Run

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m poc build --input poc/samples/modern-interactions-synthetic.json --out behavior-source
python -m poc map --ir behavior-source/page.ir.json --profile poc/profiles/client-behavior-demo.json --out behavior-target --strict
python -m http.server 8008 --directory behavior-target
```

Open `http://127.0.0.1:8008/`. `behavior-target/behavior.js` exists only for tab mappings. `mapping-report.json` records each compiled behavior, the node ID, panel count and pending browser review; `quality-report.json` still reports unsupported source controls and unverified fidelity.

Migration Studio exposes a **select-one-node** interaction option in client mapping, so an operator can review a rich-text node and select accordion or tabs. Full multi-node selection is available via JSON destination profiles/CLI. The local Studio preview iframe intentionally prohibits script execution; tabs display their **progressive, unenhanced** headings and sections there. Use an exported standalone site for interactive-browser testing. This is a deliberate safety limitation, not an indication the site script is missing.

## Accessibility and code quality

- Accordions rely on native HTML details/summary (with headings inside summary), not proprietary SharePoint scripts.
- Tab enhancement uses a small deterministic, compiler-owned `behavior.js`, manual activation on Enter/Space, focus movement with Left/Right/Home/End, one selected tab in the tab sequence, `aria-controls` and `aria-labelledby`.
- JS only uses `textContent` for tab labels, `createElement`, DOM event listeners and ARIA attributes. It never evaluates source strings, fetches external code, or injects source `innerHTML`.
- **Progressive enhancement:** if scripting is unavailable, all tab panels and original headings remain visible. If the tab runtime cannot initialize a group, no content is hidden.
- CSS is scoped to `mig-*` behavior classes; it is human-readable and appended only when behavior is configured.
- Target URLs, links and assets pass through the existing destination rewrite and sanitizer boundaries before behavior compilation.

Primary references:

- [W3C WAI-ARIA APG: Accordion](https://www.w3.org/WAI/ARIA/apg/patterns/accordion/)
- [W3C WAI-ARIA APG: Tabs](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/)
- [W3C WAI-ARIA APG: Tabs with manual activation](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/examples/tabs-manual/)
- [Microsoft SharePoint Framework client-side web parts](https://learn.microsoft.com/en-us/sharepoint/dev/spfx/web-parts/overview-client-side-web-parts)

## Quality gate

- Existing engine tests + new explicit behavior mapping, malformed HTML, hostile config and immutable IR tests must pass.
- The standalone demo must pass browser click/keyboard checks at 1440 and 390 pixels with **no** JS errors or horizontal overflow. An offline JS-disabled run must confirm that all tab panels remain visible.
- **Not a replacement for source interaction fidelity checks:** we did not observe a source SharePoint interaction, custom SPFx runtime, live tenant, assistive technology compatibility, or visual parity. Those need matched source/destination evidence and real manual/a11y review before deployment.
- CI must be green for the actual branch head. A prior green run does not prove a subsequent commit passes.
