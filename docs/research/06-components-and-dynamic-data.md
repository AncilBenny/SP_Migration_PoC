# Research 06 — Semantic control catalog and dynamic dependencies

Date: 2026-10-28. Mapping candidates, **not confirmed results from CDPH or a tenant export**.

## Source-to-CIR normalization matrix

| Source pattern | Candidate CIR component | Capture requirements | Key caveat |
|---|---|---|---|
| Text webpart, Wiki HTML, Publishing rich content field | richText, heading, paragraph, list, table | text/HTML, semantic tags, links, ordering | inline controls/tables may prevent safe splitting |
| Image / image gallery | image, or provisional image gallery extension | asset ID/url, alt, crop/focal point, caption, order | responsive rendering and license |
| Title banner / Hero | hero or page titleArea | title/banner configuration and asset | title area may be outside canvas; don't duplicate |
| Quick Links / Summary Links | linkList or cardCollection | labels, URLs, thumbnails, grouping, order | composition depends on actual semantics |
| Button / Call To Action | link or callout variant | label, destination, visual prominence | must remain keyboard accessible |
| Document embed | file/embed + asset | document URL/ID, type, preview behavior | permissions may restrict access |
| List, Library, Highlighted Content | dynamicCollection | view/query/filter/sort, data source, item fields | static snapshot loses live updates |
| People / News / Events / Search | dynamicCollection, search, unknown | query, audience, API dependencies | user personalization and refresh behavior |
| Custom SPFx | known semantic mapping or unknown | type GUID, properties, dynamic data bindings | arbitrary source JavaScript is not reusable |
| Script Editor / legacy custom | sanitized content or unknown | source markup, script dependencies, behavior | NEVER execute imported script |
| Classic Web Part zone | section / columns / container | zone ID and placement, page layout | may need CSS for visual relationships |
| Publishing field-control | content node | content type, field name, template position | underlying field may be transformed |
| Shared master-page menu/footer | siteShell/navigation | master/layout site settings | should not be repeated as body on every page |

Microsoft notes no universal classic-to-modern webpart equivalence:
https://support.microsoft.com/en-us/sharepoint/sites-pages/classic-and-modern-web-part-experiences

PnP mapping is a useful reference but targets **modern SharePoint**, not arbitrary frontend frameworks:
https://learn.microsoft.com/en-us/sharepoint/dev/transform/modernize-userinterface-site-pages-webparts

## Custom SPFx and dynamic bindings

Modern standardWebPart webPartType is a GUID with an associated data payload. SPFx property metadata can mark plain text, safe HTML, image sources and links; it is not a universal schema for every tenant custom part. SPFx DynamicData may bind a property to runtime data sources. Both should be recorded for reimplementation rather than flattened.

References:
https://learn.microsoft.com/en-us/graph/api/resources/standardwebpart?view=graph-rest-1.0
https://learn.microsoft.com/en-us/sharepoint/dev/spfx/web-parts/guidance/integrate-web-part-properties-with-sharepoint
https://learn.microsoft.com/en-us/sharepoint/dev/spfx/dynamic-data

## Proposed dependency manifest

Each nonstatic component records:
- dependencyKind: list, library, search, taxonomy, people, externalAPI, workflow, script or unknown
- sourceRef: secure identifier to original binding/query
- requiredFields, filter/sort, refresh mode and audience
- outputStrategy: reimplement, snapshotWithWarning, manuallyRebuild or approvedExclude
- fallback snapshot timestamp if any, plus fidelity diagnostics

A dynamic list shown in the public HTML can be used as a snapshot evidence source but is not proof of current query/config; the source API must confirm it.

## Mapping registry (proposal)

Identify a source component by its source family + stable type signature/field ID, not by visible title or a CSS class. Registry entry carries matching conditions, required data fields, normalization handler, chosen CIR component, fidelity, diagnostic requirements and links to real fixtures.

**Unknown by default** for any unsupported custom part. An unknown part must retain source ID/type, source location, reason, and a review task; it must not disappear from the tree.

## Initial real-world validation order

1. Rich text, headings, lists, links.
2. Sections, columns, classic zones and publishing layouts.
3. Images/media and asset rewriting.
4. Link lists, navigation, callouts and composite cards.
5. Tables and file references.
6. Dynamic list/library/search data.
7. Custom SPFx, custom classic parts and complex interactions.
