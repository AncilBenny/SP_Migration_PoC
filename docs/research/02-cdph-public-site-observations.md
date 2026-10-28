# Research 02 — California Department of Public Health public case study

Research date: 2026-10-28.

**Target**: https://www.cdph.ca.gov/

## Evidence and verification boundaries

Search-indexed public CDPH content is accessible, but attempted direct fetches of the home page and representative pages returned HTTP 502 through the available research browser; a separate runtime attempt failed DNS resolution. Therefore **no live DOM, HTTP headers, network waterfall, linked CSS source, master-page markup, computed style, page source, or authenticated SharePoint page definition was actually inspected**.

There is useful evidence of a SharePoint surface: a publicly indexed SiteData SOAP web-service description appears under a CDPH path at https://www.cdph.ca.gov/Programs/PSB/_vti_bin/SiteData.asmx?op=GetWeb and advertises a Microsoft SharePoint SOAP namespace. This suggests a SharePoint-based path or legacy surface, but does not establish the CMS/version used by every CDPH page.

Other clues: publicly indexed *.aspx pages and site-style directory structures. **ASPX is not by itself proof of SharePoint.**

We must not infer whether these pages are classic Publishing, classic Wiki, modern Site Pages, or custom applications until source evidence is available. Public observation is a case study; authorized source-system export will ultimately be necessary.

## Candidate public page archetypes

1. **Program landing page** — https://www.cdph.ca.gov/Programs/EPO/Pages/Program-Landing1.aspx
   Search-indexed content: Center for Preparedness and Response; program branding image; About Us heading; descriptive paragraphs. Candidate IR blocks to investigate: heading, image/brand area, rich text, navigation, callouts.
2. **Health information article** — https://www.cdph.ca.gov/Programs/CCDPHP/DEODC/CLPPB/pages/prov.aspx
   Search-indexed content: Health Care Provider Information; title/heading, public-health explanation, regulations section, links. Candidate IR blocks: heading, paragraphs, link, section, possibly image.
3. **Organizational informational page** — https://www.cdph.ca.gov/Programs/ODS/Pages/Office-of-Data-Strategy-Homepage.aspx
   Search-indexed content: Office of Data Strategy introduction and an About Us area. Candidate IR blocks: heading, richText, container, navigation.

These are **content observations only**, not confirmation of exact HTML, CSS, component semantics or web-part types.

## Planned collection protocol (once accessible)

For each page, capture a compliant, reproducible evidence bundle:
- Source URL, timestamp, final URL, status, content type, response headers, SharePoint-specific markers if observed, and access mode.
- Raw HTML snapshot (if permitted), sanitized DOM, rendered screenshot at desktop and mobile viewports, and extracted accessibility tree where available.
- Linked stylesheet URLs and order, media queries, CSS custom properties, font declarations, computed values at key regions, loaded images/fonts, asset licensing/permissions.
- Semantic DOM landmarks, heading order, link list, tables, layout boundaries, section backgrounds, widths, margins, spacing and breakpoints.
- Repeating chrome (site header/nav/breadcrumbs/footer) versus unique page body; identify reusable templates using multiple pages.
- Any SharePoint metadata and web-part information available via authorized APIs; do not infer hidden source parts from CSS classes.
- Evidence confidence: observed/source API, observed/rendered DOM, or heuristic.

## Specific style / layout questions to answer

- Which visual elements are site shell vs page-level? Is there a common top bar, breadcrumb, left nav, footer or side rail?
- Is main content fixed-width or fluid? How are sidebars and responsive layout treated?
- Which heading, list, table, alert and link styles are repeated? Are they based on global tokens?
- Are page banners semantic images, background images, page fields or web parts?
- Are accordions/tabs/interactions present? Are they accessible and what data powers them?
- What is source metadata vs content actually authored by an editor?

## Known unknowns and immediate next step

**Unverified:** exact CSS filenames, fonts, pixel measurements, DOM selectors, master-page/layout names, SharePoint version, source web-part types and identities. Avoid claiming any of these as facts.

The next study should combine *one authorized representative SharePoint source export* with public page screenshots/HTML when access works. We can then compare (a) source fields/parts, (b) rendered page and (c) target CIR.

## Public evidence links

- SharePoint SOAP service index: https://www.cdph.ca.gov/Programs/PSB/_vti_bin/SiteData.asmx?op=GetWeb
- Program page: https://www.cdph.ca.gov/Programs/EPO/Pages/Program-Landing1.aspx
- Health care page: https://www.cdph.ca.gov/Programs/CCDPHP/DEODC/CLPPB/pages/prov.aspx
- Office of Data Strategy page: https://www.cdph.ca.gov/Programs/ODS/Pages/Office-of-Data-Strategy-Homepage.aspx
