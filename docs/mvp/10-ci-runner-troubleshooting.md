# GitHub Actions blocker: hosted runner fails before step 1

**Status:** BLOCKED — no evidence that application tests are failing. Owner-side GitHub Actions dispatch/billing/policy investigation required. Do not mark PR #3 CI-green.

## Reproduced on 2026-10-31

- Repo: `AncilBenny/SP_Migration_PoC`; branch: `mvp/01-migration-studio`.
- MVP workflow: [run 41129449535](https://github.com/AncilBenny/SP_Migration_PoC/actions/runs/41129449535), job 124316337924 — `failure`, **no job steps**, `logs_url: null`.
- PoC workflow: [run 41129449545](https://github.com/AncilBenny/SP_Migration_PoC/actions/runs/41129449545), job 124316337650 — identical symptom.
- **Minimal diagnostic**: [run 41129449527](https://github.com/AncilBenny/SP_Migration_PoC/actions/runs/41129449527), job 124316337514 — same `failure` / no steps / no logs. Its job has one plain `echo` step, no checkout, dependencies, secrets, packages, network calls or generated build artifacts.
- A re-run of previous MVP [run 41128928148](https://github.com/AncilBenny/SP_Migration_PoC/actions/runs/41128928148) (latest job 124316089163) again failed before recording a step.
- Fetching the job log returns `404 BlobNotFound` from the backing log store.

**Interpretation:** the runner has not visibly executed any configured step. The root cause is not proven by the API evidence alone, but this is **not an observed Python test failure**. Changes to `unittest`, `pip`, `actions/checkout`, `setup-python` or application code will not fix an upstream dispatch failure. Exact cause might be quota/billing/payment, runner provisioning/availability, repository/owner policy, or a GitHub service incident.

## Owner-side checklist (no automatic billing changes)

1. Sign in as the account that owns the repository. Open the failed **minimal diagnostic run** above. Look for a yellow/red **run annotation/banner**, such as a billing/spending-limit message, runner not allocated, permissions or required approval. Capture only the non-sensitive text.
2. Open [GitHub Billing](https://github.com/settings/billing), then **Budgets and alerts / Usage** for the repo-owning account. Check GitHub Actions included usage, exhausted hard limits, blocking budgets, current payment method/account hold, and any GitHub notification. Do not enable additional spending without explicit owner approval.
3. Open [repository Actions settings](https://github.com/AncilBenny/SP_Migration_PoC/settings/actions). Confirm Actions are enabled and GitHub-hosted runners are allowed for this private repository. The minimal diagnostic needs no third-party action.
4. Check [GitHub status](https://www.githubstatus.com/) for Actions or runner incidents affecting this time window.
5. After correcting a *confirmed* account/repo issue, use **Re-run jobs** on the diagnostic run. A successful run must contain its **Confirm a runner actually started** step and log line `Runner started`.
6. Only then rerun [MVP workflow](https://github.com/AncilBenny/SP_Migration_PoC/actions/runs/41129449535) and [PoC workflow](https://github.com/AncilBenny/SP_Migration_PoC/actions/runs/41129449545). Treat CI as passing **only after all expected steps complete successfully**.
7. If billing, permissions and status all look healthy, use [GitHub Support](https://support.github.com/) with the repo/run/job IDs above. Ask them to investigate pre-step hosted-runner dispatch/provisioning and missing logs; avoid sharing tokens, keys or private content.

## Repro workflow

`.github/workflows/runner-diagnostic.yml` contains a single Ubuntu-hosted `echo` step. It is intentionally independent of the Python app. Keep it as an opt-in/manual check or remove it once hosting is repaired.

## References

- [GitHub: Troubleshooting workflows](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)
- [GitHub: Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [GitHub: Budgets and hard-blocked usage](https://docs.github.com/en/billing/how-tos/set-up-budgets)
- [GitHub: Getting help for Actions](https://docs.github.com/en/actions/how-tos/get-support)

**Exit gate:** A new `mvp/01-migration-studio` commit has both workflows green, including full regression steps, and no runner failure. Local tests are not a replacement for this evidence.
