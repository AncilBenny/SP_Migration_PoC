# Research 10 — Field-level extraction blueprint for the three MVP families

Date: 2026-10-28. Scope: **source evidence, extraction design and portable output**. These are documented API/property paths, not data observed from CDPH or a customer tenant.

## A — Modern Site Pages (first priority)

**Discovery (authorized):** Microsoft Graph list sitePages on a known site. The read request for an individual sitePage is:

    GET https://graph.microsoft.com/v1.0/sites/{site-id}/pages/{page-id}/microsoft.graph.sitePage?$expand=canvasLayout

Graph GET sitePage documentation confirms the expanded canvas relationship and the published page metadata. Graph list webparts supports page/column/vertical-section scopes. Least-privileged permission listed for GET sitePage is Sites.Read.All (review environment-specific permissions). The client should handle result pagination and network retry/throttling; no tenant has been queried.

### What to read and why

| Source path or key | Purpose | Draft CIR target | Special handling |
|---|---|---|---|
| id, webUrl, name, title, description, publishingState | Identity, URL, metadata | page/source provenance | Publishing state informs output publication safety |
| titleArea.layout, imageWebUrl, alternativeText, textAboveTitle, showAuthor, showPublishedDate | Page banner/title presentation | page title area / hero, asset | Do not duplicate a heading embedded in the body |
| canvasLayout.horizontalSections[] | Ordered layout rows | section | Preserve id, original index, emphasis |
| section.layout / emphasis | Column template and background variant | section.layout / semantic styles | Map only known layouts, flag unknownFutureValue |
| section.columns[].width | **12-unit grid span**, integer 1–12 | column.layout.widthFraction = width/12 | Preserve original width in secure source capture; verify sum per row; do not equate unit with px |
| columns[].webparts[] | Content ordered within columns | CIR child nodes | Assign stable node ID from page/part ID and source path |
| canvasLayout.verticalSection | Separate optional right-side region | section / aside-like layout | Preserve lateral relationship, don't append unmarked at end |
| textWebPart.id / innerHtml | Rich authored text | richText or parsed heading/paragraph/list/table | Sanitize HTML. The rich-text AST split must preserve inline order |
| standardWebPart.id / webPartType / data | Standard web-part identity and payload | semantic component or explicit unknown | Match by **webPartType GUID + property contract**, not visible title |
| standardWebPart.containerTextWebPartId | Parent text webpart for inline standard part | inline attachment reference | Critical: avoid duplicating inline media/controls as separate block |
| data.properties | Instance configuration | component properties | Type-specific; do not assume all images/links are here |
| data.serverProcessedContent.imageSources/links/htmlStrings/searchablePlainTexts | Processed URLs, rich content and textual indexing | assets, URLs, normalized text evidence | Inspect typed arrays, resolve relative URLs, don't silently omit |
| data.dataVersion | Source payload version | provenance / parser selector | Different data versions may need distinct property mappers |

Important: the Graph example for GET sitePage uses an @odata.type of "microsoft.graph.sitePage" without a prefix; other schema examples use "#microsoft.graph.sitePage". Our classifier accepts both. A verified typed-endpoint response may omit @odata.type when OData metadata suppression is configured, so caller-verification is represented separately.

### Verified concrete image example

Microsoft's webparts list response includes an Image standardWebPart with webPartType GUID d1d91016-032f-456d-98a4-721247c305e8, properties such as altText, captionText, imgWidth/imgHeight, and an image source in serverProcessedContent.imageSources. This is a **documented example**, not a guarantee that every tenant/image format uses exactly the same fields or GUID version.

Proposed image mapping:
- webPartType matches verified image type -> inspect properties and processed source URL;
- resolve image URL using source site origin (no blind string prefixing);
- emit image with altText, caption, linked asset record and sourceRef;
- if imageSource missing, emit unknown or unresolved image with asset diagnostic rather than inventing a URL;
- preserve crop/focal data if actual properties expose it; do not hallucinate missing crop values.

### Documented Graph sources

- https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/resources/sitepage?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/resources/titlearea?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/resources/horizontalsectioncolumn?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/resources/textwebpart?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/resources/standardwebpart?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/webpart-list?view=graph-rest-1.0
- https://pnp.github.io/powershell/cmdlets/Get-PnPPageComponent.html (uncustomized Home.aspx caveat)

## B — Classic Content Pages (second priority)

One top-level Classic Content reader, **two content strategies**, because WikiField and zoned WebPart pages are structurally different.

**B1 — Wiki**
- Read the Site Pages list item (approved SharePoint REST/CSOM/PnP).
- Capture field named WikiField where present, plus Title, identifier, file URL, template/layout metadata and modification/publishing state.
- Parse rich text into HTML AST, handling images, tables, embedded controls, link anchors and order.
- Include webpart manager definitions when embedded parts are present and preserve their positions/IDs. Don't count a referenced part as both raw visible HTML and a separate normal node.

**B2 — Web Part Page**
- Read classic page file, master/page template if relevant, and a LimitedWebPartManager in Shared personalization scope.
- Inventory each part's ID, type, ZoneId, ZoneIndex, title, visibility/closed state, and needed serialized properties/asset references (depending on API availability).
- Preserve zone grouping/order and map into CIR sections/columns based on template and rendered evidence.
- If properties require a separate read or permission, mark unknown rather than assuming an empty part.

Read-only example PnP commands (for an *already authorized* connection; not executed):

    Get-PnPListItem -List "Site Pages" -Id 123 -Fields "Title","WikiField"
    Get-PnPWebPart -ServerRelativePageUrl "/sites/example/SitePages/Example.aspx"

Exact library title, item ID and URL must be discovered, not hardcoded. PnP Get-PnPWebPart returns definitions on a classic SharePoint Online page; it does not by itself prove every serialized property or page template has been exported. Microsoft 365 Assessment Tool classicpages.csv and classicpagewebparts.csv give supplemental inventory, not a complete page capture.

References:
- https://pnp.github.io/powershell/cmdlets/Get-PnPListItem.html
- https://pnp.github.io/powershell/cmdlets/Get-PnPWebPart.html
- https://learn.microsoft.com/en-us/dotnet/api/microsoft.sharepoint.client.file.getlimitedwebpartmanager?view=sharepoint-csom
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/assessment-tool-classic-pages
- https://learn.microsoft.com/en-us/sharepoint/dev/solution-guidance/sharepoint-pages-and-the-page-model

## C — Classic Publishing / Website Pages (third priority)

**A publishing page is NOT a single blob of body HTML.** It is page fields + page layout + master page/site shell + optional fixed parts and zones. Microsoft PnP publishing transform mapping specifically models Header, MetaData, WebParts, WebPartZones and FixedWebParts. That is very useful prior art for our independent CIR.

- Capture page identity/fields and content type; identify its associated layout (e.g. PublishingPageLayout where present).
- Capture shared master/site chrome and related CSS assets as a site/template catalog **once**, subject to authorization.
- Capture page-layout control placement and field names, not just visible text: examples documented in the PnP mapping model include PublishingPageContent, PublishingPageImage, ArticleByLine and PublishingContact.
- Capture zone webpart definitions/positions and any fixed parts from the template. Keep template-defined fixed parts separate from authored part instances.
- Produce a page body that *references* a layout template ID and a siteShell/theme ID. One template should be reusable for multiple pages; do not copy the full rendered header/footer into every page.
- If a custom page layout cannot be mapped, report unresolved fields/placement and fall back to semantic text/content inventory. Do not pretend a guessed single-column layout is exact.

References:
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/modernize-userinterface-site-pages-model-publishing
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/modernize-userinterface-site-pages-layout
- https://learn.microsoft.com/en-us/sharepoint/dev/solution-guidance/sharepoint-pages-and-the-page-model

## Cross-cutting extraction requirements

1. Access: read-only; no generated tokens, tenant credentials, private user data or secrets in this repo.
2. Traceability: raw capture pointer, original field/part ID, source URL, layout position and evidence confidence on every mapped node.
3. Safety: sanitize rich HTML and URLs, never re-execute Script Editor/custom source code.
4. Content coverage: every authored field/part either converts or produces an explicit unknown/unsupported diagnostic.
5. Dependencies: list/search/content queries, user context, external APIs and file permissions are recognized but not reimplemented in MVP.
6. Sitewide vs page-owned: navigation, footer and template CSS extracted once into site profile; page body remains content-only.
7. Rendering independence: the output CIR does not contain React or SharePoint runtime types in its public block kinds.

## Concrete next experiment

An approved Graph JSON for a real modern two-column page with title area, text and image is enough to test the first adapter's **content + 12-grid layout + asset** mappings. One classic Wiki/Web Part page and one publishing page + template then validate the other two. A CSS/DOM snapshot alone cannot verify the authored field/part types.

This research document specifies field-level design but **does not claim any production capture or migration was performed**.
