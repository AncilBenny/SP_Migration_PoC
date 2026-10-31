# Milestone 13 — Reviewed navigation and local Quick Links filtering

## Scope and product contract

The destination behavior compiler translates **explicitly reviewed semantic CIR nodes**, not SharePoint runtime JavaScript. It extends the existing accordion and accessible tabs support with:

- **`toc`:** a no-JavaScript, in-page navigation list compiled from one richText node with 2–20 complete sibling `h2` or `h3` sections. Content remains in the original order under deterministic IDs. Generated navigation is outside the `data-ir-id` content-preservation marker so extra navigation links cannot be confused with migrated source hyperlinks during independent validation.
- **`filterLinks`:** searchable Quick Links, from one `linkList` node with 1–200 safe links. Compatible with both standard list and resource-card target mappings. Initially hidden search UI is revealed only by a fixed, application-owned script. All source links remain visible when JS is absent.

Example reviewed destination profile: `poc/profiles/client-navigation-filter-demo.json`

```json
{
  "behaviorMappings": [
    {"nodeId": "intro-text", "interaction": "toc", "headingLevel": 2},
    {"nodeId": "feature-tabs", "interaction": "tabs", "headingLevel": 2},
    {"nodeId": "links-part", "interaction": "filterLinks"}
  ]
}
```

## Reproduce locally

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m poc build --input poc/samples/modern-interactions-synthetic.json --out demo-navigation-source
python -m poc map --ir demo-navigation-source/page.ir.json --profile poc/profiles/client-navigation-filter-demo.json --out demo-navigation-client --strict
python -m http.server 8000 --directory demo-navigation-client
```

Open `http://localhost:8000`. Check on-page anchor navigation, type into the Quick Links filter, use the tabs keyboard controls, and disable JavaScript to confirm that all links and sections remain readable.

Migration Studio also offers **On-page navigation** and **Searchable Quick Links** under explicitly selected destination behaviors. Incompatible node kinds are rejected.

## Quality and security

- The filter reads **only existing rendered link text**, makes no network requests, and never executes SharePoint-supplied JavaScript, `onclick`, or SPFx runtime.
- No remote search, faceting, data-bound controls, authentic SharePoint filter reconstruction, or cross-page navigation is claimed.
- Unknown or ambiguous rich content is rejected from behavior compilation rather than heuristically repaired.
- Reports retain `sourceRuntimeCopied: false` and mark visual/interaction fidelity as not yet source-verified.
- Unit tests cover invalid mapping types, malformed fragments, immutable CIR, no-JS output, quality accounting, generated script, export ZIP and the Studio service API. Browser acceptance testing on the deployment environment remains required.

References: [W3C accessible navigation](https://www.w3.org/WAI/tutorials/menus/structure/), [MDN hidden attribute and progressive enhancement](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/hidden), [ARIA APG Tabs pattern](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/).
