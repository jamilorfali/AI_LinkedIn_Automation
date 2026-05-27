# Troubleshooting

## Business Console Does Not Open

Double-click `Launch AI LinkedIn Console.command` from the project folder. If macOS blocks the file because it was downloaded or edited, right-click it and choose Open once.

If port 8000 is already in use, close the older console window and try again.

## Codex Approval Policy Error

Use `approval_policy = "untrusted"` in `.codex/config.toml`. Do not switch to `on-request` unless the managed environment allows it.

## Database Initialization

Run:

```bash
ai-linkedin init-db
```

The initializer applies lightweight migrations for older local databases.

## RSS Feed Failures

Run `ai-linkedin ingest --dry-run` first. Public-web sources may be registered before web extraction is implemented.

## Preflight Warning

Run:

```bash
ai-linkedin preflight
```

Warnings are informational when they describe optional setup, such as a missing `GOOGLE_APPS_SCRIPT_WEBAPP_URL`. Failures mean the local workflow is not ready.

## Schedule Package

`ai-linkedin build-local-schedule-package` only writes files under `data/exports/schedule/`. If jobs are not running, confirm you manually copied and loaded the plist files from that runbook.

## Intelligence Reports

If `build-citation-matrix` fails, pass either `--draft-id` or `--topic-id`. If the matrix has unsupported rows, attach a primary or high-trust source before using the claim in public copy.

## Approval Token Mismatch

Tokens are hashed before storage. Raw tokens appear only once. If a token is expired or used, generate a new approval packet.

## Apps Script Header Error

Run:

```bash
ai-linkedin validate-approval-webapp
ai-linkedin build-approval-deployment-package
```

Then replace the Sheet header row with the generated `review_queue_sheet_template.csv` header row. The Apps Script now checks required columns before validating tokens.

## Review Queue Import Blocked

Run:

```bash
ai-linkedin validate-review-queue --csv PATH_TO_EXPORTED_SHEET.csv
```

Failures usually mean the exported Sheet row no longer matches the local draft version or content hash. Regenerate the approval packet and review queue for the current draft before importing.

## Pilot Checklist Is Not Advancing

Run:

```bash
ai-linkedin pilot-checklist
```

Some gates are intentionally manual, including Apps Script deployment, weekly candidate review, and iPhone magic-link testing. Mark them only after the human action is complete.

## Production Test Package Is Not Publish Ready

`build-production-test-package` can produce an approval-flow test package even when the selected topic still needs stronger sources. If the status says source review is needed, use the package to test Apps Script, Sheet export/import, and manual package generation only. Do not post publicly until the candidate shortlist and citation matrix support the claims.

## Live Readiness Warning

`v1-readiness` may report `ready_for_local_live_pilot` with a warning when `GOOGLE_APPS_SCRIPT_WEBAPP_URL` is missing. This is acceptable for public-source ingestion and local package testing. Set the URL before iPhone magic-link testing.

## Publishing Blocked

This is expected in v0. Build a manual posting package after approval.
