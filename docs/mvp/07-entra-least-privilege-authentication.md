# MVP milestone 07 — Microsoft Entra delegated Graph authentication

## Research-backed design

This optional **operator-side** adapter enables an authorized, local Graph binary staging workflow. It is **not** a multiuser hosted identity system, SharePoint tenant connection, or automatic consent/grant manager. No tenant or credential was accessed in the offline tests.

Verified primary sources:

- [MSAL Python token acquisition](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens): use MSAL rather than implementing OAuth. For an installed public desktop client, MSAL's browser flow implements PKCE; silent acquisition and refresh use its token cache.
- [Graph driveItem /content API](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0): delegated Files.Read is the least-privileged **listed** permission; effective file access also depends on the signed-in user's permissions.
- [Selected permissions](https://learn.microsoft.com/en-us/graph/permissions-selected-overview): Sites.Selected and file/list selected scopes need consent **and** a resource grant. Merely requesting Sites.Selected grants no site access.
- [Entra app registration security](https://learn.microsoft.com/en-us/entra/identity-platform/security-best-practices-for-app-registration): least privilege, delegated access when appropriate, managed identity for Azure services, and certificates rather than password secrets where applicable.
- [MSAL conditional access](https://learn.microsoft.com/en-us/entra/msal/python/advanced/conditional-access): MFA and other tenant policies may require interactive reauthentication.

## Trust zones and implemented boundaries

1. An authorized administrator separately registers a **single-tenant public desktop application** with Mobile/Desktop redirect URI http://localhost and approved Graph delegated read permissions. The installed client must **not** have a client secret. Consent, site grants and admin policies are outside this MVP CLI.
2. The operator sets MIGRATION_ENTRA_TENANT_ID and MIGRATION_ENTRA_CLIENT_ID **in their local environment**, never in the source fixture, migration profile, output report or CLI flags. Both must be UUIDs. A login hint may optionally be selected through a named environment variable.
3. \`python -m poc graph-auth-check\` only validates the local configuration and returns permissionApproved:false, graphAuthorization:not-verified, and selectedResourceGrant:not-verified. It does not contact Entra/Graph or disclose tenant/account information.
4. \`graph-stage --auth-mode entra-delegated\` lazily loads the optional MSAL Python library, uses an in-memory cache and system-browser PKCE login, and calls acquire_token_silent_with_error for subsequent requests. Multiple cached accounts are **rejected** until one is explicitly selected. --silent-only denies interactive login.
5. Only Files.Read, Sites.Selected, and Files.SelectedOperations.Selected can be requested. No read-all, write, full-control, or .default scopes are allowed by this adapter. Selected scopes require separate resource grants; these checks are not a substitute for service-side authorization.
6. The existing GraphBinaryFetcher sends bearer credentials **only** to graph.microsoft.com. Temporary Graph download URLs are fetched **without** the token, on an explicitly allowlisted HTTPS hostname. No bearer, signed URL or raw MSAL errors go into reports. Graph errors have stable redacted diagnostics.
7. Binary staging, integrity verification and independently verified local publication remain separate operations; local stored bytes are not proof that a production URL is reachable.

## Windows operator workflow

\`\`\`powershell
python -m pip install -r requirements-auth.txt

# Obtain the tenant/client UUIDs from your organization's authorized Entra application registration.
$env:MIGRATION_ENTRA_TENANT_ID = "<approved tenant GUID>"
$env:MIGRATION_ENTRA_CLIENT_ID = "<registered public client GUID>"
python -m poc graph-auth-check --scope Files.Read

# An actual authorized Graph drive-item plan is required. Public synthetic fixtures
# do not contain real drive identities and cannot be used for live downloads.
python -m poc graph-stage --plan path/to/authorized-plan.json --out private-staged \`
  --allow-download-host approved-tenant-download-host.example --auth-mode entra-delegated --scope Files.Read
python -m poc graph-verify --report private-staged/graph-staging-report.json --staged-root private-staged
\`\`\`

Do not paste access tokens into prompts, shell commands, logs, the web UI or source files. Protect downloaded source documents and reports with appropriate local access controls.

## Not implemented / release blockers

- Live tenant onboarding, login/consent integration testing, grant verification and Microsoft Entra admin review.
- Server-side OIDC sessions, browser/UI account management, persistent OS-backed token cache, MFA edge-case integration and Conditional Access claim challenge handling.
- App-only unattended background jobs. For Azure-hosted background work, evaluate managed identity; elsewhere evaluate secure workload identity federation or certificate-backed authentication and least-privilege resource grants.
- Live destination CDN/bucket publishing, production URL readback, tenant-wide scanning, enterprise malware/sensitivity controls, verified CI green status, and visual fidelity assessment.

Offline tests inject MSAL test clients; they never open a browser or contact SharePoint. Production release needs authorized test-tenant integration, security review and reliable CI.
