# ADR 004 — Generic destination mappings after source cleanup

**Status:** implemented as a small HTML/CSS proof of concept. **Scope:** one Modern SharePoint public-documentation-adapted fixture. The public samples are not a live tenant migration.

## Product principle

We are not primarily reconstructing SharePoint. We are extracting a clean, framework-neutral representation that can be translated into a **different client destination**. Faithfully reproducing the original site is a supported destination choice, not the only outcome.

```
SharePoint source  ->  clean semantic CIR  ->  target mapping profile  ->  HTML / CSS / optional JS
                                 |                        |
                                 |                        + Client resource portal, different visual design
                                 + source-style fidelity mode (when source style evidence exists)
```

Source adapters know SharePoint; the CIR and destination mapping engine do **not**. Target choices never modify source extraction. A single cleaned page can be regenerated for different clients.

## Implemented now

The `poc/mapping.py` destination mapper reads only a saved CIR JSON file and a versioned `poc/profiles/client-example.json`. The profile chooses semantic target components, approved colors, typography family, content width, gap and labels. The example turns generic `linkList` into a responsive **resource-card collection** and `hero` into the client's page header, with no SharePoint-specific markup in the target HTML.

```
python -m poc build --input poc/samples/modern-demo.json --out demo
python -m poc map --ir demo/page.ir.json --profile poc/profiles/client-example.json --out demo-client
python -m http.server 8000 --directory demo-client
```

The two transformations share exactly the same `page.ir.json` bytes. The second command does not call source `normalize()`. `demo-client/mapping-report.json` includes a SHA-256 of that CIR, mapped control counts and unsupported controls. Local referenced assets are bundled, and final HTML is sanitized a second time to guard against a manually edited IR.

### Current mapping vocabulary

| Generic CIR kind | Supported destination mapping | Current example |
|---|---|---|
| `hero` | `pageHeader` | Client page banner with H1 |
| `richText` | `contentBody` | Accessible content wrapper; keep clean headings/lists/links |
| `image` | `media` | Client-styled figure, alt text and caption |
| `linkList` | `resourceCards` or `simpleLinks` | Resource cards; optional simple list alternative |
| `unknown` | `reviewNote` | Explicit visible placeholder and mapping warning |
| `page`, `section`, `columns`, `column` | Fixed generic layout renderer | Preserve section ordering and source-relative width fractions |

This is a **bounded safe mapping vocabulary**, not an arbitrary HTML/JS plugin system. New client components will be added through explicit, tested renderers. Profile data cannot inject raw HTML tags, executable scripts or unvalidated CSS. Any unknown CIR node remains a diagnostic instead of being silently omitted.

## Two different quality goals

- **Source-fidelity output:** compare original page content/layout/style/behavior with the generated HTML/CSS/JS, given matching source evidence. The current neutral `structural` renderer is not a pixel-fidelity claim.
- **Client-target output:** compare generated page with the **client's requested design and component spec**, while preserving required source content, links, assets and meaning. Source-pixel similarity is not an appropriate metric when the destination intentionally differs.

### Common non-loss acceptance criteria

1. Every source-authored item is mapped or appears as an explicit unsupported diagnostic; no silent content loss.
2. Headings, text, list/table semantics, link destinations, media alternatives and source order are preserved unless the client's written mapping changes them.
3. Each CIR node keeps source provenance and traceability; destination component choices are versioned separately.
4. URLs and assets are rewritten intentionally, with checks for broken/restricted references.
5. Interactions are modeled as safe behavior contracts when required; raw SharePoint JavaScript is never copied blindly. Static pages can generate **HTML/CSS without a JS file**.
6. A client target with a different layout/theme is tested against that target contract, not mislabeled as a faithful visual replica.

## Next engineering increment (one source only)

The next milestone after this profile-based demonstration is **control-level mapping traceability**: collect/normalize a more representative public Modern serialized markup example (`CanvasContent1` or documented Graph control payload), compare all source blocks against IR, and add declarative URL remapping plus target quality checks. Only then broaden the component catalog or begin additional SharePoint adapters.

## Research basis

Microsoft/PnP already use configurable transformation mappings and cross-site URL mapping in their SharePoint-to-SharePoint workflow. We borrow the *separation of mapping from extraction*, not their SharePoint-specific target representation.

- https://learn.microsoft.com/en-us/sharepoint/dev/transform/modernize-userinterface-site-pages-model
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/modernize-userinterface-site-pages-webparts
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/modernize-userinterface-site-pages-termmapping
- https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0