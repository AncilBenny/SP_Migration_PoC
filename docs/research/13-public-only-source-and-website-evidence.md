# Research 13 — Public-only evidence from real websites and published SharePoint files

Date: 2026-10-28. **No tenant access, SharePoint plugin, authentication, scraping behind a login, or private exports.** This document uses directly inspected public GitHub source files and publicly viewable CDPH pages. Derived metadata is machine-readable in `examples/research/public-evidence-derived.json`.

## Evidence classification — avoid overclaiming

- **public_source_page_file:** a publicly committed ASPX publishing page file with actual serialized page metadata. Shows what the file stores, but not how it renders now, nor a full API export.
- **open_source_page_layout/template:** a published ASPX page layout or Web Part Page template. Shows placeholders, web-part zones, fields and CSS registration, but NOT authored live web-part instances.
- **published_test_fixture:** a PnP CLI fixture containing SharePoint-shaped response data. Useful for parser tests but NOT a verified live production capture.
- **live_public_rendered_page:** public site textual/rendered page observed through the research browser. Supports content/semantic analysis ONLY unless the SharePoint authoring model is independently verified.
- **fetch failure:** inability to retrieve a page is not evidence that the page lacks content or is not SharePoint.

## Finding A: Modern page authoring example (public fixture)

Source: https://github.com/pnp/cli-microsoft365/blob/main/src/m365/spo/commands/page/page-get.mock.ts (blob f1f42408a85769d95ef52e04ef37a000e557576a).

The fixture's modern page ListItemAllFields contains `ClientSideApplicationId`, `PageLayoutType`, `CanvasContent1` and `LayoutWebpartsContent`. Its CanvasContent1 is serialized markup with attributes such as `data-sp-canvascontrol`, `data-sp-controldata`, `data-sp-webpartdata` and `data-sp-htmlproperties`. This is an important **alternative source format** to Graph `canvasLayout` and must not be mistaken for equivalent JSON.

**Extraction consequence:** PoC Modern reader should begin with Graph `sitePage` `canvasLayout` (documented API), but a future SharePoint REST/PnP path may need to safely decode HTML-encoded control JSON embedded in CanvasContent1. Keep a separate decoder with tests; do not execute scripts or blindly parse HTML as a modern Graph response. Modern public tenant authoring data is generally unavailable anonymously.

Relevant Microsoft Graph documentation: https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0. Microsoft states that the API requires an Authorization bearer token and `$expand=canvasLayout` provides authored content.

## Finding B: Classic Wiki page (public fixture)

Same PnP CLI fixture includes a classic page with a populated `WikiField`, `CanvasContent1 = null`, and a `<table id="layoutsTable">`. That layout contains a full-width first row followed by two approximately 49.95%-width cells and an embedded `layoutsData` marker with the value `true,false,2`. Three `div_<GUID>` webpart-placeholder identifiers appear.

**Extraction consequence:** classic Wiki must parse the structural **layout table** and embedded references before rich text is flattened. Avoid treating the table as authored data table for the new web page; it is an authoring layout artifact. Embedded placeholders imply part positions, not a complete part definition; web-part metadata is a separate needed input.

## Finding C: Classic Web Part Page layout (public template)

Source: https://github.com/Puzzlepart/prosjektportalen/blob/master/templates/root/Resources/SitePage.txt (blob 91bab1b83d68ce8def5c274c6a71d2684df01dfe).

The Page directive uses `~masterurl/default.master`. The body declares two `WebPartPages:WebPartZone` controls with IDs `LeftColumn` and `RightColumn`. Source HTML uses CSS classes for 12-unit responsive layout (`ms-sm12`, `ms-md12`, `ms-lg12`, `ms-xxl8`, `ms-xxl4`) and contains both a style block and a script block.

**Extraction consequence:** Capture the zone IDs/order and template grid hints; do not infer actual webpart instance data from the zone definitions. Do not ship the source script into CIR or assume CSS classes provide computed breakpoint behavior without measured styles.

## Finding D: Classic Publishing page file (public source page)

Source: https://github.com/bhanurao/lhe-map/blob/master/Pages/lheByRegion.aspx (blob fae531c20ec3d6a313afad704015711ec4102077).

This public ASPX file inherits `Microsoft.SharePoint.Publishing.TemplateRedirectionPage`, references a custom master via `~masterurl/custom.master`, and exposes a `PublishingPageLayout` field naming `homepage.aspx` plus a serialized `PublishingPageContent` field. The field contains rich-text webpart placeholder markup.

**Extraction consequence:** A publishing instance alone does not contain the full visual layout or sitewide chrome. It references template assets. We need the *matching* page layout/master and CSS from the same site to claim fidelity; those are not available here.

## Finding E: Publishing page layout file (public open-source template)

Source: https://github.com/pnp/PnP-Transformation/blob/master/Reference%20Material/Contoso.Intranet/Contoso.Intranet/SP/Modules/MOPageLayouts/ContosoWelcomeLinks.aspx (blob 61a059378d8ede75549e5e19394f3459ef311f4d).

This `PublishingLayoutPage` directly names field controls `Title`, `PublishingPageImage`, `PublishingPageContent`, `SummaryLinks`, and `SummaryLinks2`. It defines Web Part Zones `TopColumnZone`, `LeftColumnZone` and `RightColumnZone`, and registers `pagelayouts15.css` plus `editmode15.css`; it contains breadcrumb markup.

**Extraction consequence:** page content fields, layout slots, web-part zones and CSS are distinct layers; the normalizer must preserve their relationship. **Do not join this layout with the publishing page instance from Finding D: they originate from different sites/repositories.**

Additional independent page layout example: https://github.com/SPRWD/BookSourceCode/blob/master/Chapter%207%20-%20Page%20Layouts/_catalogs/masterpage/spectergroup/about-pagelayout.aspx has field controls `PublishingPageImage` and `PublishingPageContent` and registers `HeaderStyleDefinitions`, `pagelayouts15.css` and `editmode15.css`.

## Finding F: Actual visible CDPH pages (site technology unverified)

- https://hie.cdph.ca.gov/ : a navigable informational page with major headings, paragraph content, an ordered sequence of questions/steps, bullet lists, a 4-column public-health registry information table, cross-links to `.aspx` pages on www.cdph.ca.gov, and footer/navigation links.
- https://hie.cdph.ca.gov/faq.html : long FAQ page with question/category links, many heading + paragraph answer blocks and lists. The observed textual representation is NOT enough to establish interactive accordions or web-part types.
- https://portal.cdph.ca.gov/en-US/ : distinct CDPH portal with publicly visible search/cards; referenced assets from a Power Apps domain. Do not assume the portal uses SharePoint or that the primary CDPH website and portal share the same authoring model.
- https://www.cdph.ca.gov/ and a representative Program Landing page: direct fetch returned HTTP 502 from the available research browser; public search indexing is not a substitute for live DOM/CSS measurements.

**Extraction consequence:** the first two are good actual **semantic-output** examples (heading, list, link list, table, FAQ sections, nav/footer), but NOT confirmed SharePoint inputs. They cannot supply a valid SharePoint source-capture sample without independent verification.

## Public-only access boundary

SharePoint Online site content generally requires identity/authentication. Publicly readable websites can reveal rendered structure but not the authenticated Graph canvas or classic webpart properties. Microsoft guidance: https://learn.microsoft.com/en-us/sharepoint/external-sharing-overview . Public examples and openly committed files are the reliable source of authoring structure for this access-constrained research.

## Traceability matrix: verified fact -> CIR target

| Public evidence | Source construct actually observed | Normalization target | Confidence & missing piece |
|---|---|---|---|
| PnP modern mock | CanvasContent1 and nested serialized webpart fields | page -> sections/parts via safe serialized decoder | file-backed fixture; Graph canvas mapping separately documented |
| PnP classic mock | WikiField layout table and three part markers | section -> rows/columns -> richText or linked webpart | file-backed fixture; no full embedded webpart definitions |
| Puzzlepart template | LeftColumn / RightColumn zones | layout zones/columns | template-backed; no instances or computed CSS |
| Publishing ASPX page file | PublishingPageLayout & PublishingPageContent | page.templateRef / richText | public page-file-backed; referenced template absent |
| PnP publishing layout | field controls and three zones | template fields / slots + zone layout | template-backed; no same-site page instance |
| CDPH HIE home | heading/list/table/nav/link visible structure | heading/list/table/navigation | rendered-only; SharePoint backend unverified |
| CDPH HIE FAQ | heading/FAQ blocks and topical links | heading/section/linkList | rendered-only; interaction unknown |

## What remains before calling real-data research complete

**Public-only PoC-ready:** We now have representative published source formats for all three categories and public rendered page semantics. We can build decoders and tests against these **source files/fixtures** and a generic HTML output renderer. This is sufficient to START a technical PoC.

**Not yet evidenced:** one modern Graph page response with matching rendered output and source assets from a real tenant; a matched classic/publishing page + template + CSS bundle; accurate CDPH public site DOM/CSS; source-vs-target pixel/behavior comparison. These cannot honestly be claimed from public material available today.

Research recommendation: stop waiting for private SharePoint access. Start a **public-fixture-based PoC** with explicit fidelity/provenance flags. Make real-tenant verification an external integration gate rather than a blocker for core parser architecture.
