# Migration Studio — CIR v0.2 boundary and rich-text safety increment

**Scope:** one Modern SharePoint page source adapter, with two independent
output modes. This increment does not imply production security certification
or browser-rendered source fidelity.

## Evidence basis

- [Microsoft Graph sitePage](https://learn.microsoft.com/en-us/graph/api/resources/sitepage?view=graph-rest-1.0) describes the Modern SharePoint page and the canvasLayout relationship.
- [Microsoft Graph canvasLayout](https://learn.microsoft.com/en-us/graph/api/resources/canvaslayout?view=graph-rest-1.0) distinguishes horizontal and vertical page sections.
- [Microsoft Graph sitePage update](https://learn.microsoft.com/en-us/graph/api/sitepage-update?view=graph-rest-1.0) documents supported standard and text web parts; **the API's supported update list is not a guarantee of fidelity for all existing web parts.**
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) specifies the schema format. Use `jsonschema` with the FormatChecker for CI structural/format assertions.
- [OWASP XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet) explicitly recommends a well-maintained browser-focused sanitizer such as DOMPurify. **Our Python allow-list serializer is conservative PoC cleanup, not a substitute for production browser sanitizer security reviews.**

## Contract

- The generator writes `schemaVersion: "0.2.0"` and publishes `schema/page.ir.v0.2.schema.json`. The historical `schema/page.ir.schema.json` remains the **research-only v0.1 draft**, not the active output contract.
- `poc/contracts.py` enforces version, required records, a bounded tree, globally unique node IDs, valid node kinds/layout geometry, diagnostic types, and a safe local asset path shape at renderer boundaries. It **does not** silently repair an invalid IR.
- The `poc map` and Studio rendering paths reject invalid or outdated CIR. The source inspector can retain duplicate-ID diagnostics without claiming that the broken IR is renderable.
- `jsonschema` is a development/CI dependency and checks generated CIR against Draft 2020-12. The service still runs offline with Python standard-library dependencies; production deployments should add the authoritative schema validator at every untrusted input boundary.
- There is **no blind 0.1 → 0.2 conversion**: old demo CIR should be rebuilt from the original public source, because version upgrades must preserve provenance.

## Rich HTML transformation

- Reviewed semantic elements include headings, paragraphs, lists, tables, table headers, figures, captions, and linked/inline images. Table headers keep their safe `scope`, and table cells keep bounded positive `rowspan`/`colspan`.
- Source HTML never runs scripts, inline event handlers, embedded documents, SVG, MathML, or executable style markup. URLs are limited to safe HTTP(S), mailto links, fragments, and accepted ordinary relative references. Image sources cannot be mailto or opaque URLs.
- Rich-text cleanup records diagnostic `RICH_TEXT_CLEANUP_REVIEW` when content/attributes/URLs are stripped. Inline images are retained in HTML but receive `INLINE_IMAGE_ASSET_REVIEW`: **the tool has not downloaded, licensed, or verified remote images**.
- The destination URL rewriter reserializes the sanitized HTML and preserves the reviewed image and table attributes instead of accidentally discarding them.
- The independent content validator checks actual HTML image URLs after destination rewrite; it does not claim browser layout, computed styles, accessibility, custom SPFx behavior, or source-versus-output pixel fidelity.

## Release gates still missing

1. A production-grade HTML5 parser and actively maintained DOM-based sanitizer; corpus fuzzing against browser parser edge cases and dependency patching.
2. Original SharePoint-side asset extraction including permission/rights, download integrity, offline packaging and link health.
3. Full CIR semantic cross-references (node/asset relationships), target component registry and migration plans between schema versions.
4. Matched original/target renders, responsive layout tests, keyboard/accessibility and interaction parity checks.
5. Authenticated tenant capture in a separate adapter when specifically authorized, not as a prerequisite for these public-only tests.
6. GitHub Actions must pass reliably; local green tests are not a production release verdict.

## Repeatable local checks

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m poc build --input poc/samples/modern-rich-layout-public-adapted.json --out demo-modern
python -m poc map --ir demo-modern/page.ir.json --profile poc/profiles/client-example.json --out demo-target
python -m studio --port 8765
```

To test rejection, replace `schemaVersion` in a copied IR with `0.1.0` and run `poc map`; it should return an actionable `CIR_CONTRACT_INVALID` error. Do not edit production data in place.
