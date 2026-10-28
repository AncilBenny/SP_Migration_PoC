# MVP research scope — three typical SharePoint page families

Date: 2026-10-28. Decision: Narrow initial implementation to **three** page-family adapters, with one shared Canonical Intermediate Representation (CIR). Earlier wider research chapters remain background, not MVP commitments.

## The three families

| Priority | Family | Typical pages | Approach |
|---|---|---|---|
| 1 | **Modern Site Pages** | Modern SharePoint Online team and communication pages | Microsoft Graph sitePage + canvasLayout; extract title area, sections, columns, text/standard web parts and assets |
| 2 | **Classic Content Pages** | **Wiki + Web Part Pages** | One classic-content reader, with separate internal strategies for rich-text WikiField and classic web-part zones/properties via CSOM/REST |
| 3 | **Classic Publishing / Website Pages** | Publishing sites, traditional website-style pages | Publishing page fields/content types + page layout/master template, web-part zones, navigation, shared CSS/assets |

Wiki and Web Part pages are two distinct authoring formats within the **same second top-level group**; their internals cannot be conflated. CDPH may be a useful publishing-style case study, but its real underlying page model remains unverified.

## Simplified processing pipeline

    Detect page family
      -> Modern Graph reader
      -> OR Classic Content reader (WikiField strategy / zoned WebPart strategy)
      -> OR Publishing reader (fields + page layout/master)
    Each reader -> secured source capture + assets / stylesheet evidence
    Shared semantic/layout/style normalization -> versioned CIR
    CIR -> HTML/React/other component adapters + quality report

Do not hardcode a page type from a .aspx extension or site domain. Public-HTML snapshots are an evidence fallback, **not** a fourth full-fidelity migration adapter.

## In scope for MVP

- Common page content: headings, paragraphs/rich text, links, ordered/unordered lists, tables, images, files, basic media and embeds as safe references.
- Common layouts: sections, containers, columns, zones, ordering, relative widths, basic responsive stacking, page title/hero.
- Common site elements: header, navigation, breadcrumbs, footer, simple cards/callouts and quick links.
- Appearance research: template CSS, fonts, repeated colors, spacing, typography, breakpoints and sitewide design tokens; preserve source references.
- Assets and linking: URL rewrite maps, original/proposed destination paths, alt text, missing asset warnings.
- Standard static web parts. Unknown/custom/interactive parts remain placeholder unknown nodes with ID, original type, position, dependency notes and explicit diagnostics.

## Out of MVP scope (record but do not build specialized support yet)

- On-premises versions and every historical SharePoint edition; initially prioritize authorized SharePoint Online samples.
- Blog, Delve Blog, arbitrary ASPX applications, and unrelated SharePoint administration/data migration.
- Deep support for custom SPFx, Script Editor, third-party components, workflows, Power Apps or InfoPath.
- Full reimplementation of live list/search/people services, personalization/audience targeting, permissions engine or tenant workflows. Record dependencies and downgrade warnings.
- Pixel-perfect reproduction of arbitrary proprietary/custom CSS/JavaScript or server-side code, per-user customization and full revision histories.

## Target experiments — one representative sample each

1. Modern: 1 page using text + image + quick links + 2-column layout. Validate Graph authoring canvas against visible page.
2. Classic Content: 1 representative Wiki or Web Part page containing text, image and embedded/zoned web parts. Verify which internal parsing strategy applies.
3. Publishing: 1 classic website-style page **plus its page-layout/master reference and authorized stylesheets**. Compare field values, shared shell and page body.
4. Normalize all three to the **same** semantic page vocabulary and a small design-token set.
5. Later build **one** basic HTML renderer as an independent proof of portability.

## Research acceptance

Every authored field/visible text block/link/asset and web-part instance either maps into CIR or yields a traceable explicit unsupported diagnostic. Shared header/nav/footer is not repeated as authored page body. Dynamic content is never silently flattened into permanent static data. All actual source access must be read-only and approved, with redaction of sensitive exports.

## Authoritative background

- https://learn.microsoft.com/en-us/sharepoint/dev/transform/assessment-tool-classic-pages
- https://learn.microsoft.com/en-us/sharepoint/dev/solution-guidance/sharepoint-pages-and-the-page-model
- https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0
