# MVP milestone 06 — authorized Graph transport + verified publication boundary

**Scope:** Modern SharePoint file dependencies only. This extends the offline `graph-plan` and binary-staging adapter; it does not enable automatic tenant discovery, OAuth grants, deployment to a website, or a hosted SaaS. Public/demo test fixtures require no tenant credentials.

## Source API contract and trust zones

- Source metadata is reconciled to a stable `(driveId, itemId)` identity first. This identity determines `GET https://graph.microsoft.com/v1.0/drives/{driveId}/items/{itemId}/content`. The token is supplied from a server-side provider, never from the page fixture, destination profile, browser UI, CLI arguments or migration report.
- Microsoft Graph may answer with a **302** to a temporary preauthenticated download URL. Treat the `Location` header as a bearer-like capability: it is **not** a permanent asset URL, must never be logged or included in CIR, and must be fetched **without** a Graph Authorization header. Allow the host explicitly (exact DNS name), HTTPS only, no URL userinfo, no custom ports, no subsequent redirects.
- The provided default transport resolves all host addresses and rejects non-public IPs. It pins the approved address into a TLS connection with certificate validation for the DNS hostname, avoiding a separate DNS lookup during connection. It does not use ambient proxy settings.
- Bound transfers by the existing file-size policy, number of retries, server-supplied Retry-After (capped), network timeout and existing staging size/MIME/signature checks. All failures use redacted diagnostic codes. The implementation does not bypass malware or sensitivity restrictions.
- For least privilege, prefer a security-reviewed delegated `Files.Read` integration or grant the minimal app permission scope (such as site-scoped `Sites.Selected` when supported and configured). Admin consent and per-site access grants belong in a future authentication/onboarding adapter. This MVP does **not** obtain tokens or consent.

## Operational states and evidence

1. `graph-identity-resolved`: stable metadata matched but no bytes have been transferred.
2. `staged-verified`: an approved transport fetched file bytes and staging SHA-256, size, MIME and signature checks passed.
3. `published-verified`: the destination store wrote bytes **and independently read back** the same SHA-256 and length.
4. `hostedDestinationVerified: false`: a local output directory is **not proof** that an external CDN, bucket, production URL, browser or routing config works. No production website publication is claimed.

The publication interface is `store.put_if_absent(key, bytes)` plus `store.read(key)`. The reference `LocalDirectoryStore` creates a safe local export package; future S3/Azure Blob/client CMS adapters must implement the same independent read-back and record real provider version/etag/URL-resolution evidence. Existing file contents are never overwritten when bytes differ. The report distinguishes incomplete source dependencies from successfully stored files.

## Offline walkthrough (Windows PowerShell, no tenant access)

```powershell
python -m poc build --input poc/samples/modern-cdph-routes-demo.json --out demo-graph
python -m poc graph-plan --ir demo-graph/page.ir.json --drive-items tests/fixtures/graph-drive-items-offline-demo.json --profile poc/profiles/cdph-root-routing-example.json --out demo-graph/graph-acquisition-plan.json
python -m unittest discover -s tests -v
```

The synthetic metadata fixture resolves **3 of 4** referenced files, without downloading any. For a separately authorized **real** Graph proof, a security reviewer must supply an independently obtained, limited-scope Graph token through a server-side environment variable and the exact download-redirect DNS host(s):

```powershell
# An authorized operator provisions MIGRATION_GRAPH_ACCESS_TOKEN outside Git and shell history.
python -m poc graph-stage --plan demo-graph/graph-acquisition-plan.json --out demo-graph/staged --allow-download-host your-approved-download-host.example --token-env MIGRATION_GRAPH_ACCESS_TOKEN
python -m poc graph-verify --report demo-graph/staged/graph-staging-report.json --staged-root demo-graph/staged
python -m poc graph-publish-local --report demo-graph/staged/graph-staging-report.json --staged-root demo-graph/staged --destination demo-graph/destination-package --out demo-graph/local-publication-report.json
```

No live Graph calls were performed in this milestone. A real run requires **actual accessible drive IDs**, an authorized token and the actual explicitly approved Graph redirect hostname. The illustrative CDPH fixture isn't real Graph evidence.

## Gaps to production-grade

- Admin-approved OAuth/OIDC flow with token lifecycle, credential vault and audit logs.
- Robust remote storage connectors with idempotency, remote object versions, evidence of CDN routing and content validation.
- Graph token-scoping reviews, tenant-specific redirect domain policies, enterprise private-network egress review, malware/mime threat analysis, Microsoft Graph 429 concurrency budgeting and large-file streaming/upload sessions.
- Multi-GB file streaming; current MVP buffers files up to its bounded PoC limit and is **not** ready for large tenant migration.
- End-to-end integration tests against explicitly authorized test tenants and destination accounts, plus independent security audit and reliable CI.

## Microsoft primary references

- [Graph driveItem content, v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0) — 302/temporary download URL and permissions.
- [Graph throttling guidance](https://learn.microsoft.com/en-us/graph/throttling) — 429, Retry-After, backoff.
- [Graph permissions reference — Sites.Selected](https://learn.microsoft.com/en-us/graph/permissions-reference) — app permission scope.
- [Upload sessions](https://learn.microsoft.com/en-us/graph/api/driveitem-createuploadsession?view=graph-rest-1.0) — future large-file/destination adapter design.
