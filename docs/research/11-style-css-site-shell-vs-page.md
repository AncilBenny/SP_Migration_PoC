# Research 11 — Website-style layouts, CSS and template normalization

Date: 2026-10-28. Scope: three MVP page families. This chapter proposes **how to collect and generalize CSS/layout evidence**, not actual measured CDPH styles.

## First insight: layout has two related structures

**Authored structure**: fields, webparts, sections/columns or template placeholders. Discovered from Graph and classic page/layout definitions.
**Rendered structure**: the actual responsive order, spacing, widths, colors and appearance after master pages, CSS, scripts and themes. Requires permitted browser/snapshot inspection.

A screenshot cannot prove authoring webparts; a list of webparts cannot prove final rendered CSS. The two are compared, not conflated.

## Three ownership levels

| Ownership | Examples | Frequency | Normalized result |
|---|---|---|---|
| Site shell | Header/footer, global navigation, logo, breadcrumbs | Once per site or shell variant | siteShell / navigation references |
| Page layout/template | Publishing hero/body/sidebar slots, wiki text layout, webpart zones, modern section pattern | Once per unique template/signature | template ID and ordered layout tree |
| Authored content | Page heading, text, images, cards, links, webpart properties | Per page | semantic CIR body and provenance |

Two classic publishing articles can share one master and page layout but have different PublishingPageContent/PublishingPageImage values. The system should store one shell, one layout and two page bodies—not two full duplicated HTML screenshots.

## Verified classic CSS discovery locations and properties

Microsoft's classic branding guidance describes:
- Master Page Gallery, commonly at _catalogs/masterpage, containing master pages, layouts, CSS/images/custom branding.
- Classic seattle.master and its corev15.css, and oslo.master/oslo.css in appropriate contexts.
- Style Library stylesheet content and registration in page/master markup.
- Web.AlternateCSSUrl for site CSS and Web.SiteLogoUrl for a logo where configured.
- CSS registration and cascade order, plus page- and component-specific overrides.

**These are SharePoint conventions, NOT verified CDPH file names.** Microsoft warns that classic branding does not apply to Modern SharePoint Online in the same way and that relying on generated SharePoint class names and HTML structure is unstable.

Sources:
- https://learn.microsoft.com/en-us/sharepoint/dev/solution-guidance/use-css-to-brand-pages
- https://learn.microsoft.com/en-us/sharepoint/dev/solution-guidance/portal-branding
- https://learn.microsoft.com/en-us/sharepoint/dev/solution-guidance/sharepoint-pages-and-the-page-model

## Modern styling capture

Modern Graph gives section.layout, section.emphasis, section.columns[].width and titleArea layout/alignment. These are **structural/authoring properties**, not a complete styling stylesheet.

- section emphasis -> semantic surface variant, only if validated.
- 12-grid column width -> fractional width; preserve original span in source evidence.
- titleArea -> banner/hero variant; avoid double-rendering main page title.
- observed typography/colors/spacing -> optional design-token candidates.
- custom CSS and generated SharePoint class names are not runtime dependencies of the destination.

Sources:
- https://learn.microsoft.com/en-us/graph/api/resources/horizontalsection?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/resources/titlearea?view=graph-rest-1.0

## Reproducible CSS/visual research manifest (proposed)

For each permitted page and viewport capture:
1. Site/page ID, source URL, capture timestamp, browser viewport/device scale and source mode.
2. Linked stylesheets in load order, URL, hash, and known owner (master, layout, site, page, unknown).
3. Representative computed styles for body text, headings, links, banner, navigation, tables, content width and cards.
4. DOM/accessibility tree landmarks, visual region bounding boxes, component boundaries and authored part IDs if traceable.
5. Breakpoint/media behaviors at proposed 390, 768 and 1440 CSS px.
6. Assets, font source, image alternative text, relative URL resolution, missing links, focus/keyboard behavior.
7. Confidence label on every relationship: API confirmed, visually observed, inferred or unresolved.

This is a restricted **VisualEvidence** artifact, not executable CIR. Do not copy arbitrary source JavaScript and CSS into the target.

## Design token derivation

Group repeated observed values across >=3 pages into semantic tokens (color.text, color.link, space.section, type.heading, width.content, breakpoint.stack). Keep original CSS path/selector in an audit bundle. Do not invent a breakpoint or theme value from a single image.

## CDPH observation status

Direct fetch retried 2026-10-28 for https://www.cdph.ca.gov/ and the public Program Landing example; both returned HTTP 502 through the research browser. Thus **no live CDPH CSS, DOM, webparts, specific master/page layout, or measured style values were obtained**. Indexed public content remains a candidate archetype, not proof of actual SharePoint page family.

## Focused style experiments

A. Modern 2-column page: compare Graph section/column/title area with rendered mobile/desktop.
B. Classic Wiki/Web Part: compare WikiField/zones and classic master with rendered layout.
C. Publishing: compare page layout fields and zones, master header/footer and CSS across two pages using the same template.

**Exit gate:** every visual region is attributed to shell, template or authored content and labelled observed/inferred/unresolved. Common styles are reusable tokens; all structural exceptions remain explicit.
