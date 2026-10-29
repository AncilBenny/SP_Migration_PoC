# Modern SharePoint — Graph driveItem asset identity & binary staging (MVP milestone 05)

**Status:** Offline Graph metadata resolver and injectable binary staging; **not** a connected Graph client or production uploader. This work uses Microsoft Graph v1.0 contracts and a **self-authored** synthetic driveItem fixture. No tenants, credentials, private exports, or protected assets were used.

## Why a separate Graph adapter

A SharePoint page's asset link is not proof that the corresponding binary has migrated. A `driveItem` includes its opaque `id`, `parentReference.driveId`, the `file` facet, `webUrl`, and optional SharePoint identifiers. The drive/item pair is the stable acquisition *locator* for a particular indexed item. `webUrl` is only a URL-matching hint, not an authoritative unique ID. This adapter never guesses a match when metadata contains two conflicting items with the same URL.

References: [Microsoft Graph driveItem resource, v1.0](https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0), [itemReference resource, v1.0](https://learn.microsoft.com/en-us/graph/api/resources/itemreference?view=graph-rest-1.0), [download driveItem content, v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0), [SharePointIds, v1.0](https://learn.microsoft.com/en-us/graph/api/resources/sharepointids?view=graph-rest-1.0).

**Never persist a preauthenticated URL:** Graph `@microsoft.graph.downloadUrl` is a short-lived capability URL, not a durable source identifier. Graph `/drives/{driveId}/items/{itemId}/content` may redirect to one of these URLs. A future authorized transport must implement safe, immediate redirect handling and **never forward its Authorization header to the redirected destination**. This PoC intentionally has no live transport and cannot download private SharePoint content.

## Local Windows demo

```powershell
python -m poc build --input poc/samples/modern-cdph-routes-demo.json --out demo-graph
python -m poc graph-plan --ir demo-graph/page.ir.json --drive-items tests/fixtures/graph-drive-items-offline-demo.json --profile poc/profiles/cdph-root-routing-example.json --out demo-graph/graph-acquisition-plan.json
python -m unittest tests.test_graph_assets -v
```

The synthetic input has four document/image references. The synthetic driveItem catalog identifies three. The unresolved `.docx` reference remains **unresolved-graph-metadata**. This is an intentional incomplete catalog demonstrating review behavior, not a real CDPH inventory.

The output plan records `nodeId`, original and destination URLs, `driveId`, `itemId`, `graphContentPath`, optional SharePoint IDs, and a non-success status. The canonical CIR remains unchanged. The sample contains a deliberately fake `@microsoft.graph.downloadUrl`; it is excluded from the output report.

## Binary staging adapter

`poc.graph_assets.stage_graph_files(plan, out, fetcher=provider)` requires a **caller-provided** `provider(driveId, itemId) -> (bytes, mimeType)` abstraction. A production implementation must first authenticate with least-privilege Graph permissions, enforce host and redirect restrictions, implement bounded streaming/retries/throttling, and track authorization. The staging code has file-count and byte caps, MIME and limited binary-signature checks, stable hash-addressed output filenames, path/symlink checks, SHA-256 evidence, deduplication by drive ID plus item ID, and independent `verify_graph_staging` rechecking. It does **not** determine whether the user has rights to migrate the file, perform antivirus or DLP scanning, or publish it to a client's target storage.

## Release-gate semantics

| Status | Meaning | Production approval |
| --- | --- | --- |
| `graph-identity-resolved` | Unique Graph driveItem metadata matched an authored source reference | **No** — no bytes downloaded |
| `unresolved-graph-metadata` | No matching supplied Graph file metadata | **No** — manual research / catalog expansion |
| `ambiguous-graph-match` | Multiple distinct Graph items claim the same URL | **No** — manual disambiguation |
| `requires-source-review` | Cannot safely match sensitive or unsupported reference | **No** |
| `staged-verified` | Exact binary bytes written and SHA-256 verified locally | **No** — not published |
| `uploadedToDestination: false` | No verified destination upload | **No** |

### Follow-on engineering before any real tenant use

- Microsoft Entra app registration, explicit tenant authorization, least-privilege permissions and audit logging; no tokens in user-accessible reports.
- Graph metadata pagination, change tracking and version/ETag concurrency checks; evidence of HTTP status and retries / throttling (`429`, `503`, Retry-After).
- Robust streamed authenticated Graph `/content` adapter, safe redirect isolation, size/MIME/malware enforcement and tenant/drive access controls.
- Real client destination storage upload adapters and **read-back or signed receipt verification** before setting `uploadedToDestination = true`.
- Broader references: `srcset`, `picture`, CSS `url()`, page attachment files, document/web-part APIs, and cases where `webUrl` differs from the authored link.
- Benchmarks, public-format fixtures, independent extraction validation and CI green. This is not yet an industry-grade engine.
