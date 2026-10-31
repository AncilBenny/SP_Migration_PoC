# Milestone 11 — reviewed CSS selector-to-component mapping

**Status: local/offline compiler enhancement, review-required, not production visual fidelity.**

## Why we added this

Actual SharePoint / SPFx stylesheets frequently depend on runtime wrappers, brand styles and Microsoft-specific selectors. Copying those to a completely different website results in dead rules and collisions; discarding everything loses visual intent. The new **reviewed selector mapping** translates a known source selector into a stable destination component selector. The canonical IR is unchanged, and source CSS is never executed.

The operator supplies a local stylesheet and a versioned JSON manifest. This demo uses authored synthetic selectors, not customer SharePoint exports.

## JSON mapping contract

```json
{
  "version": "1.0",
  "mappings": [
    {"sourceSelector": ".ms-rtestate-field > h2", "targetComponent": "content.heading2"},
    {"sourceSelector": ".ms-wpheader h2", "targetComponent": "page.title"}
  ]
}
```

The compiler accepts only known target component identifiers. These resolve through a **fixed registry** of renderer-owned selectors in `poc/css_workbench.py` (e.g. `.target-body h2`, `.target-header h1`, `.target-resource a`). Source selectors are matched exactly after basic normalization; **they never become output selectors**. No arbitrary CSS, JavaScript, selector interpolation or imports can be provided through the mapping JSON.

Rules that reference target components absent from the generated HTML are withheld. Unmapped source selectors and unsafe declarations stay blocked or review-required. The same conservative CSS declaration/property and media-condition validation from milestone 09 still applies. Inputs are capped at 200 KB CSS and 64 mapping entries.

**No automatic application:** review candidates live in `reviewed-candidates.css`, `css-review.json`, and `selector-mapping-review.json` in the export. Generated `index.html`, `style.css`, and `page.ir.json` are not modified. A developer must evaluate the proposed styles against the client design system and original source before promotion.

## Run locally (Windows PowerShell)

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m poc build --input poc/samples/modern-demo.json --out demo
python -m poc map --ir demo/page.ir.json --profile poc/profiles/client-example.json --out demo-client
python -m poc css-workbench --css poc/samples/modern-selector-component-demo.css --selector-map poc/profiles/modern-selector-component-map.json --html demo-client/index.html --out demo-selector-review
python -m studio --port 8765
```

In the Migration Studio **Styles & scripts** tab, generate a client output, then attach a source `.css` and optional `.json` selector map.

## Research and remaining limitations

- [Microsoft SPFx CSS guidance](https://learn.microsoft.com/en-us/sharepoint/dev/spfx/css-recommendations)
- [MDN CSS specificity](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_cascade/Specificity)
- [tinycss2 syntax parser](https://doc.courtbouillon.org/tinycss2/latest/api_reference.html)

Next product gates: computed source/target CSS comparison; responsive cascade ordering; accessibility; behavior compilation; and real browser fidelity baselines. Mappings remain review-only until those gates are independently verified.
