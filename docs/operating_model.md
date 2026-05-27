# Operating Model

## Business Console

Use the browser console for normal operation:

```text
Launch AI LinkedIn Console.command
```

The console shows the next best action, runs the weekly flow, builds production test packages, previews artifacts, records local approval decisions, builds manual posting packages, and archives final post URLs. Google Apps Script phone approval is optional rather than the default operating path.

## Daily Scan

Run source loading and ingestion manually until scheduling is stable:

```bash
ai-linkedin preflight
ai-linkedin run-daily-scan
```

This writes a local run report under `data/exports/operations/`.

## Friday Package

Every Friday between 12:00 PM and 2:00 PM Central:

```bash
ai-linkedin run-friday-package --week current
```

Outputs live under `data/review_packets/YYYY-Www/`.
The workflow also writes a run report under `data/exports/operations/` and intelligence outputs under `data/review_packets/YYYY-Www/intelligence/`.

## Intelligence Review

The Friday workflow now generates local quality reports:

```bash
ai-linkedin audit-sources --week current
ai-linkedin cluster-topics --week current
ai-linkedin build-discovery-queue --week current
ai-linkedin build-intelligence-report --week current
```

For a specific draft, build a claim/source matrix:

```bash
ai-linkedin build-citation-matrix --draft-id DRAFT_ID --week current
```

Use these reports before approval when a topic depends on weak, social, or unfamiliar sources.

## Editorial Review

Before approval, run:

```bash
ai-linkedin editorial-review --draft-id DRAFT_ID
```

This creates an editorial review packet with:
- Extracted draft claims.
- Claim support status.
- Voice and style checklist.
- Political and vendor-sensitivity notes.

Approval packet creation also runs this review and includes the claim and voice notes in the local JSON packet.
It also generates a citation matrix and includes citation summary counts in the approval packet.

## Notification Package

Create a local Outlook-copyable notification after the approval packet is ready:

```bash
ai-linkedin build-notification-package --draft-id DRAFT_ID --week current
```

This creates HTML, plain text, metadata, an approval packet, and a matching review queue CSV under the local data folders. No email is sent automatically.

## Non-Response Behavior

- No response means no post.
- Send one Friday reminder.
- Roll the draft forward.
- Send a Monday follow-up if still unanswered.

Generate reminder packages locally:

```bash
ai-linkedin build-reminder-package --draft-id DRAFT_ID --kind friday --week current
ai-linkedin build-reminder-package --draft-id DRAFT_ID --kind monday --week current
```

## Manual Posting

After approval in the business console, press `Approve Locally & Build Package` to create the final manual package without Google Sheets or CSV import.

The Google Sheet path remains available for phone approval testing:

```bash
ai-linkedin validate-review-queue --csv data/review_packets/YYYY-Www/review_queue.csv
ai-linkedin import-review-queue --csv data/review_packets/YYYY-Www/review_queue.csv
ai-linkedin build-manual-posting-package --draft-id DRAFT_ID
```

The user copies and posts manually on a personal LinkedIn profile.

`validate-review-queue` checks the exported Sheet headers, review IDs, draft versions, content hashes, duplicate decisions, and allowed approval actions before anything is imported.

## Approval Web App QA

Before depending on the mobile approval page:

```bash
ai-linkedin validate-approval-webapp
ai-linkedin build-approval-deployment-package --week current
ai-linkedin run-approval-qa --action approve_text_only --week current
```

The QA command tests the local CSV write-back/import/manual-package path in an isolated workspace.

After posting, archive the final URL:

```bash
ai-linkedin archive-post --draft-id DRAFT_ID --post-url LINKEDIN_POST_URL
```

## Integration Status

Check optional integration guardrails at any time:

```bash
ai-linkedin integration-status
```

In Hard Zero Mode, the active paths are local notification files, local prompt packets, CSV review queue export/import, and the manually deployed Apps Script approval page. Google Sheets API write-back, Microsoft Graph email sending, paid model providers, media generation, and LinkedIn API publishing remain disabled unless explicitly approved later.

## Local Scheduling

Generate optional macOS `launchd` files only after manual runs are stable:

```bash
ai-linkedin build-local-schedule-package
```

This writes plists and a runbook under `data/exports/schedule/`. It does not install or load any scheduled job. Approval, notification sending, and LinkedIn posting remain human actions.

## Live Pilot

Build the full live-testing package:

```bash
ai-linkedin v1-readiness
ai-linkedin build-live-test-package --week current
ai-linkedin pilot-checklist
```

You can start local live-source testing when `v1-readiness` reports `ready_for_local_live_pilot`. Deploy Apps Script and set `GOOGLE_APPS_SCRIPT_WEBAPP_URL` before iPhone magic-link testing.

Run the production pilot control loop before the first operating week:

```bash
ai-linkedin run-production-pilot --week current --dry-run
```

Remove `--dry-run` when you are ready for live public RSS ingestion. The command writes a production pilot report, refreshes the checklist, audits sources, and keeps all publishing and email actions manual.

Build the first-post production test package after candidates exist:

```bash
ai-linkedin build-production-test-package --week current
```

This creates a selected topic shortlist, saved draft, approval packet, local notification files, ReviewQueue CSV, validation report, and runbook. If the chosen topic is not publish-ready, use the package to test the approval flow only and attach stronger sources before posting publicly.
