# Research 05 — Separate handling by SharePoint family and deployment

> **Scope update:** This matrix preserves broader API research, but the MVP will use **three grouped readers only**: Modern; Classic Content (Wiki/WebPart strategies); Publishing/Website. On-prem, Blog, arbitrary ASPX and custom apps are deferred. [MVP scope decision](09-mvp-scope-three-page-families.md).

Date: 2026-10-28. Scope: research, not an implemented connector. No authenticated tenant data has been collected.

## Core decision

Select a source adapter **per page**, not per domain. One tenant/site can include multiple page families. SharePoint deployment (Online vs on-prem and version) controls the transport; page family (Modern, Wiki, Web Part, Publishing, other) controls how to decode content. All feed one shared Canonical Intermediate Representation (CIR).

| Source | Strong identification | Capture strategy | Essential preserved information |
|---|---|---|---|
| Modern SharePoint Online | Typed Graph sitePage with canvasLayout; authenticated modern metadata | Microsoft Graph v1.0 sitePage GET expanded canvasLayout; supplement PnP/SharePoint API for data missing in Graph | titleArea, horizontal and vertical sections, widths/order, textWebPart HTML, standardWebPart GUID and data, metadata and linked assets |
| Classic Wiki | Assessment PageType WikiPage + confirmed wiki content | CSOM/REST list-item fields and embedded webpart manager | wiki rich text, text layout, embedded webparts and their positions |
| Classic Web Part | Assessment PageType WebPartPage + confirmed zone data | CSOM File.GetLimitedWebPartManager(Shared), webpart definitions/properties; page template | zones, order, part type/ID, properties, dynamic data sources, hidden/closed state |
| Classic Publishing | Assessment PageType PublishingPage + publishing layout link | Publishing fields, associated content type, page-layout/master-page gallery references, webpart zones and CSS/assets | field-to-template placement, layout identity, shared site chrome, publishing metadata, webparts |
| Custom/Blog/other ASPX | Assessment or authenticated type evidence | inventory-first, specialized adapter/review | source bytes/evidence, unsupported control diagnostics |
| On-premises SharePoint Server | authenticated server edition/version | version-compatible CSOM/REST or approved export + page-family reader | same semantic elements, server-specific metadata and assets |
| Public HTML-only | accessible rendered HTML; no authorized API | observed DOM, linked stylesheet and media inventory, optional screenshots/computed style | visible content and observed layout ONLY; webpart identity and authoring schema generally unknown |

## Relevant confirmed API surfaces

**Modern:** GET /sites/{site-id}/pages/{page-id}/microsoft.graph.sitePage?$expand=canvasLayout; pages list endpoint supports pagination. Webparts can be read from page or columns/verticalSection. A standardWebPart has a webPartType GUID and data; a textWebPart has innerHtml. Its titleArea may be separate from canvas. Graph create/write supports a constrained list of webparts; do not mistake that for the read taxonomy.

References:
- https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/sitepage-list?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/webpart-list?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/resources/standardwebpart?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/sitepage-create-webpart?view=graph-rest-1.0

**Classic:** Microsoft CSOM documents File.GetLimitedWebPartManager(PersonalizationScope) and associated webpart definitions. Historical Web Part Pages SOAP protocol also documents GetWebPartProperties2; use only as approved compatibility fallback, not first choice.

References:
- https://learn.microsoft.com/en-us/dotnet/api/microsoft.sharepoint.client.file.getlimitedwebpartmanager?view=sharepoint-csom
- https://learn.microsoft.com/en-us/dotnet/api/microsoft.sharepoint.client.webparts.limitedwebpartmanager?view=sharepoint-csom
- https://learn.microsoft.com/en-us/openspecs/sharepoint_protocols/ms-wpps/1e4a2a07-988c-4981-a6a1-3b76a4c4eb64

**Publishing:** master page provides shared chrome; page layout combines field controls and webpart zones, and page values supply authored content. Associated content type/layout can vary by page. Deduplicate shared template and preserve page-field provenance.

References:
- https://learn.microsoft.com/en-us/sharepoint/administration/stage-7-upload-page-layouts-and-create-new-pages-in-a-publishing-site
- https://learn.microsoft.com/en-us/openspecs/sharepoint_protocols/ms-pubws/6293da78-9f29-4025-8c71-05fd29a8be2f

**Inventory:** Microsoft 365 Assessment Tool supports SharePoint Online (not SharePoint Server). It distinguishes WikiPage, WebPartPage, PublishingPage, BlogPage and ASPXPage. Option --exportwebpartproperties includes serialized webpart properties and can contain sensitive configuration. Verify scan coverage before using report counts.

References:
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/assessment-tool-classic-pages
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/assessment-tool-classic-pages-run
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/assessment-tool-classic-pages-requirements
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/assessment-tool-classic-pages-csv

**Special case:** PnP Get-PnPPage and Get-PnPPageComponent warn the unmodified modern Home.aspx may show empty CanvasContent1 until edited/published. This is not proof the user-visible homepage is blank.

References:
- https://pnp.github.io/powershell/cmdlets/Get-PnPPage.html
- https://pnp.github.io/powershell/cmdlets/Get-PnPPageComponent.html

## Key caveats

1. Do not infer a specific SharePoint page family from an .aspx filename, URL folder, CSS class or a SharePoint service endpoint.
2. A page can include custom SPFx, custom classic parts, dynamic list queries, scripts and user-specific content. Capture dependencies; never run source scripts in the new runtime.
3. The PnP modernization engine produces **modern SharePoint pages**, while this project must produce **target-neutral CIR**. Its mappings are research prior art, not our output requirements.
4. Prefer read-only auth, preserve source data in restricted storage, sanitize before publication, and flag unsupported parts rather than silently dropping them.

Prior art:
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/modernize-userinterface-site-pages-webparts
- https://learn.microsoft.com/en-us/sharepoint/dev/transform/modernize-userinterface-site-pages-layout

## Proposed source modules (not yet implemented)

discovery/site-profile; discovery/page-classifier; capture/graph-modern; capture/classic-wiki; capture/classic-webpart; capture/classic-publishing; capture/versioned-onprem-transport; capture/public-dom; normalize/semantic; normalize/layout; normalize/style; normalize/dependencies; diagnostics/coverage.

A shared source-site profile stores nav/master/template catalog and theme observations, while each page is routed separately.

## Research acceptance

For each source page prove page family from recorded evidence; inventory every field/webpart; report order/position and dependencies; map every part to a CIR component or explicit unknown with provenance; keep site shell out of repeated body content.
