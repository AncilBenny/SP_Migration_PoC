# Modern SharePoint: destination roots, dependencies and public acquisition (MVP 0.1)

**Status:** implemented prototype with regression tests, **not** a SharePoint tenant downloader, not a production asset migration solution. All implemented examples are public/test data. This module must remain source-independent; it reads CIR and mapping profiles without accessing a SharePoint service.

## Product behavior

Customers can declare a **source website root** and independent **page, image, and document destination roots**. The path after the source prefix survives unchanged. Page routing optionally removes the final `.aspx` suffix, case-insensitively; query strings and fragments survive. Roots are matched by parsed origin and path boundary, avoiding substring host collisions. More-specific typed rules override generic, legacy URL mappings. Page/document/image rules can use different hostnames or root-relative destinations.

For instance, a sample policy (not verified to be an actual client deployment):

```json
{
  "rootMappings": [
    {"kind":"page", "sourcePrefix":"https://www.cdph.ca.gov/", "targetPrefix":"https://internet.staging/", "stripAspx":true},
    {"kind":"image", "sourcePrefix":"https://www.cdph.ca.gov/", "targetPrefix":"https://images.internet.staging/"},
    {"kind":"document", "sourcePrefix":"https://www.cdph.ca.gov/", "targetPrefix":"https://documents.internet.staging/"}
  ]
}
```

This maps `https://www.cdph.ca.gov/anything.aspx` to `https://internet.staging/anything`, `https://www.cdph.ca.gov/directory/report.pdf` to `https://documents.internet.staging/directory/report.pdf`, and `https://www.cdph.ca.gov/images/example.png` to `https://images.internet.staging/images/example.png`. These are illustrative routes, not claims that the destination hosts are live. Root mappings operate at the **destination adapter**, leaving CIR source references intact. For old profiles, `urlMappings` continues to work unchanged. Unsupported URL formats fail profile validation.

Important: URL classification is based on element role (`<img>`) and recognized file extension (e.g. `.pdf`, `.docx`, `.png`). Extensionless download URLs, `/_layouts/15/download.aspx?SourceUrl=...`, SharePoint sharing links and Graph IDs require a future source-resolved file classifier instead of guessing their type.

## Source dependency manifest and pull

`dependency-manifest.json` audits the *rendered* HTML and exact bundled file bytes, recording local SHA-256 hashes and unresolved remote/root-relative URLs. `acquisition-plan.json` inventories image/document candidates using original CIR URLs, grouped by source node and classified as `already-bundled`, `pending-public-fetch`, or `requires-source-resolution`. An asset with a rewritten destination URL has **not** necessarily been retrieved, scanned, uploaded, or verified at that URL.

You can opt into fetching **publicly accessible** documents and images separately from rendering:

```powershell
python -m poc pull --ir demo/page.ir.json --profile poc/profiles/cdph-root-routing-example.json --out pulled-assets --plan-only
python -m poc pull --ir demo/page.ir.json --profile poc/profiles/cdph-root-routing-example.json --out pulled-assets --allow-host www.cdph.ca.gov
```

The second command is an explicit network operation and will only succeed for public accessible file URLs; it does not authenticate to SharePoint. It checks exact allowed hostname, HTTPS/TLS certificate, DNS public IPs, disallows redirects and signed URLs, and limits files and bytes. Active-file formats such as SVG/HTML are not downloaded by this prototype. Downloaded files are saved into `downloads/images/` or `downloads/documents/` with hashes, byte lengths, and an `acquisition-result.json` report. **Nothing is uploaded automatically**. Actual SharePoint private library retrieval requires a dedicated Graph/driveItem adapter, secure credential handling, permitted download, rights/malware scanning, destination storage credentials and successful upload verification.

### Production security gate

The opt-in local downloader is **not a general URL fetching service**. Do not expose it as an internet-accessible endpoint. Even with pinned public DNS addresses and disallowed redirects, public DNS domains may be hostile and fetched content untrusted. Production requires separate restricted egress infrastructure, quotas, authorization, malware and file-type scanning, storage isolation, retry/backoff, deduplication, operational logging without secrets, and explicit approval of source and target tenants.

### Public evidence

- Microsoft Graph driveItem API: https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0
- Microsoft Graph download content: https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0
- Graph `@microsoft.graph.downloadUrl` is **temporary** and **preauthenticated**. It is not a permanent source link, canonical asset key, or target URL. The later Graph adapter must use stable drive/item identities to retrieve bytes without leaking token-bearing URLs into manifests.
