# PoC 01 — Content accounting and target output verification

**Scope:** One Modern SharePoint source format only; public Microsoft Graph–adapted test data and a publicly available PnP CLI CanvasContent1 fixture. No private SharePoint, tenant authentication, or plugin.

## Why this phase matters

A successful HTML render is not proof of a successful migration. This phase records what happened to each supported content/control element across **source → CIR → destination HTML**. It deliberately leaves unsupported parts as `needs-review` instead of pretending to migrate them.

Two independent checks run:

1. **Source → CIR:** Inspect the original typed/decoded source control list; compare page title, rich text, headings, safe hyperlinks, Quick Links, images and explicitly unsupported web parts with normalized CIR nodes. Inline images and rejected unsafe links are flagged for review. The capture decoder is not a complete SharePoint rich-text/runtime parser.
2. **CIR → target:** Parse the *generated HTML file*, identify components by `data-ir-id` (stable generic CIR node IDs), check retained text, heading levels, link URLs after approved client rewrites, image src/alt, and whether local assets physically exist. This is independent of the mapping counters. Unknown components receive an explicit review state.

The output includes `quality-report.json` alongside the existing `report.json` or `mapping-report.json`. Status meanings:

| Status | Meaning |
|---|---|
| `preserved` | The supported semantic fields under test match source/IR/HTML. Client URL changes are accepted if they follow the selected profile. |
| `needs-review` | Unsupported control, unsafe source link, or other evidence that cannot truthfully be called lossless. Migration may be incomplete. |
| `lost` | A supported text/link/heading/image/control is demonstrably missing or changed from the expected normalized data. |

`passed: true` means **no detectable `lost` items in the supported checks**; it does not mean `needs-review = 0`, nor prove pixel fidelity, JavaScript interactions, CSS, screen reader output, authenticated links, or full source semantic equivalence.

## Run in Windows PowerShell

```powershell
python -m unittest discover -s tests -v
python -m poc build --input poc/samples/modern-internal-links.json --out demo-rewrite
python -m poc map --ir demo-rewrite/page.ir.json --profile poc/profiles/client-example.json --out demo-mapped --strict
python -m poc validate --ir demo-rewrite/page.ir.json --html demo-mapped/index.html --profile poc/profiles/client-example.json
python -m http.server 8000 --directory demo-mapped
```

Open `http://localhost:8000`. Inspect `demo-rewrite/quality-report.json` and `demo-mapped/quality-report.json` for node-by-node accounting. `poc validate` writes `demo-mapped/quality-check.json` and exits nonzero if it detects lost content; it does **not** re-run the source adapter.

The reference fixture has **four preserved supported components** (page header, rich text, image, Quick Links) and **one unknown part requiring review**. This is fixture-level semantic accounting, not a real-site success percentage.

## Mutation tests

New tests deliberately delete or change a link, heading, embedded asset and node marker and verify detection. Additional tests cover a lost source control, unsafe link filtering, and the public PnP CanvasContent1 fixture's unknown part. `tests/test_validation.py` runs offline with Python's standard library.

## What remains

- Rich-text inline images, complex embeds, tables/forms, and dynamic controls require more field-level mappings.
- Layout and visual validation need **matched** source and target rendered screenshots and measured CSS; none is claimed here.
- Stronger content similarity checks will need DOM semantics beyond this lightweight HTML parser.
- Source and target URL reachability are not checked without network access.
- Do not treat `data-ir-id` as a guarantee of fidelity: this validation also inspects the actual text, headings, URLs, image metadata and local asset files within each marked node.
- CI has previously reported failures with inaccessible logs, so test status must distinguish verified **local** execution from GitHub-hosted results.
