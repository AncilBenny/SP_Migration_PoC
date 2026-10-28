# Research 01 — SharePoint page models and extraction surfaces

Research date: 2026-10-28. Scope: evidence-backed foundation for **SharePoint → canonical intermediate representation (CIR) → framework-independent output**, *not* an in-SharePoint modernization tool.

## Decision: separate source adapters, one output model

There are at least three materially different sources. A URL ending in .aspx alone does **not** classify the page.

| Page family | Authoring / storage model | Source extraction first choice | Core challenges |
|---|---|---|---|
| Modern SharePoint Online site pages | Site Pages library, title area, sections, columns and web parts | Authorized Microsoft Graph sitePage with expanded canvasLayout | Custom SPFx parts, unsupported API cases, dynamic/list-backed data |
| Classic wiki / web-part pages | Wiki HTML or web-part zones and web-part instances | Authorized SharePoint APIs / CSOM / PnP, export layout + web-part settings | Mixed HTML and controls, zones, display templates, personalization |
| Classic publishing pages | Master page, publishing page layout, content-type fields and optionally zones | Authorized SharePoint APIs / CSOM / PnP, inspect field values and layout templates | Content versus chrome, master-page CSS, XSLT, custom controls, reused sitewide assets |

Microsoft's page-model guidance describes classic master pages, publishing page layouts, wiki text areas and web-part zones. Modern pages use a different section/column/web-part canvas model. See sources S1, S2 and S3 below.

## Modern SharePoint data surface (confirmed from Microsoft docs)

- List site pages and GET a sitePage via Microsoft Graph. GET /sites/{site-id}/pages/{page-id}/microsoft.graph.sitePage?$expand=canvasLayout exposes authored canvas, including horizontal sections, column widths and web parts. Source S2.
- The returned page contains metadata such as ID, webUrl, name, title, description, pageLayout, publishingState, and a canvasLayout. The canonical model must preserve provenance and page publication state where available. Source S2.
- Web-part representations include textWebPart (rich content via innerHtml) and standardWebPart (webPartType GUID and data). Do not identify a standard web part solely by display title. Sources S4 and S5.
- Authorized application/delegated Graph calls require SharePoint site permissions; Microsoft lists Sites.Read.All as the least-privileged permission for GET sitePage in the documented API. Prefer a read-only extraction identity. Source S2.
- Graph page creation/updates restrict supported web parts; therefore, successful Graph read access does not prove that every custom/legacy part can be rebuilt via the Graph write API. Our output is not intended to be a Graph write roundtrip. Source S6.
- Older SharePoint API/CSOM page data includes CanvasContent1 and additional page fields. These are **source-specific inputs**, not our public CIR contract. Source S3.

Illustrative Graph discovery request (requires authorization, not executed in this study):

    GET https://graph.microsoft.com/v1.0/sites/{site-id}/pages/{page-id}/microsoft.graph.sitePage?$expand=canvasLayout
    Authorization: Bearer <token>

## Classic site extraction surface (confirmed / proposed)

Classic rendering combines master page + content page + authored fields or web parts. Publishing page layouts are based on content types. A robust adapter must discover:
1. Publishing page field values: Title, description, content HTML and image/link fields, layout reference, author/date, taxonomy.
2. Web-part zone tree and each part's type ID, class, properties, data bindings and order.
3. Shared master-page chrome: header, navigation, footer and global components. Do NOT duplicate these into every page body.
4. Master pages, page layouts, stylesheet and asset dependencies. These are candidates for a **theme/layout catalog**, not a blindly copied CSS bundle.
5. Related list/library items, attachments, URLs and permissions; retain references even when a destination cannot reproduce an interaction.

Microsoft's Classic pages assessment catalogs WikiPage, WebPartPage, PublishingPage, BlogPage and ASPXPage with differing readiness and transformation routes (S7). Do not assume PnP can transform arbitrary custom publishing pages automatically.

## Normalization principle: semantic-first with source preservation

Example mappings (hypotheses until exercised against actual source exports):

| Source element | CIR element | Notes |
|---|---|---|
| Rich HTML text | richText, heading, paragraph, list, table | Parse/sanitize; preserve links and marks |
| Image or media part | image / video + asset | Retain src, alt, caption, crop and provenance |
| Hero/banner | hero or container + image + heading | Use semantics only when supported by evidence |
| Quick Links / Summary Links | linkList / navigation / cardCollection | Decide by content/function, not CSS class |
| Zone/section/column | section / columns / column | Preserve order, widths and responsive intent |
| List/library-backed part | dynamicCollection or unknown | Preserve query/config/data dependency; a static HTML snapshot is not equivalent |
| Custom code or unknown part | unknown + typed source metadata + diagnostics | Never silently discard; review manually |
| Master-page/sitewide navigation | siteShell/navigation | Separate from page body; one shared definition |

## Limitations, safety, and confidence

- Web scraping is a **fallback** for public pages and yields a rendered snapshot; it cannot reliably recover underlying web-part properties, unrendered content, permissions, data bindings or authoring layout.
- Do not presume anything on a government public site is free of copyright, access-control or attribution requirements.
- Read-only first; honor site policies/robots, rate limits and terms; never bypass authentication.
- Sanitize HTML and reject scripts, event attributes and unsafe URLs before rendering or storing any executable content.
- Flag unsupported controls and dynamic behavior explicitly. Capture errors, missing assets, original URLs, ordering and content-fidelity metrics.
- For modern and classic formats, record whether each datum was confirmed by a source API, inferred from DOM, or inferred by heuristics.
- Fonts, layout and CSS recovered from a public page are **appearance evidence**, not automatically the authored SharePoint template.

## Sources (verified via public documentation)

S1. Microsoft SharePoint pages and the page model — https://learn.microsoft.com/en-us/sharepoint/dev/solution-guidance/sharepoint-pages-and-the-page-model

S2. Microsoft Graph Get sitePage v1.0 — https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0

S3. Customizing modern site pages / CanvasContent1 — https://learn.microsoft.com/en-us/sharepoint/dev/solution-guidance/modern-experience-customizations-customize-pages

S4. Microsoft Graph List webParts — https://learn.microsoft.com/en-us/graph/api/webpart-list?view=graph-rest-1.0

S5. Microsoft Graph standardWebPart — https://learn.microsoft.com/en-us/graph/api/resources/standardwebpart?view=graph-rest-1.0

S6. Microsoft Graph Create sitePage / supported web parts — https://learn.microsoft.com/en-us/graph/api/sitepage-create?view=graph-rest-1.0

S7. Microsoft 365 classic pages assessment — https://learn.microsoft.com/en-us/sharepoint/dev/transform/assessment-tool-classic-pages

S8. Classic web part mapping — https://learn.microsoft.com/en-us/sharepoint/dev/transform/modernize-userinterface-site-pages-webparts

S9. Classic publishing versus modern communication sites — https://learn.microsoft.com/en-us/sharepoint/publishing-sites-classic-to-modern-experience
