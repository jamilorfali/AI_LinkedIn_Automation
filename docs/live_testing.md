# Live Testing

## Current Stage

The system is ready for local live-source pilot testing when:

```bash
ai-linkedin v1-readiness
```

reports `ready_for_local_live_pilot` or better.

## Build The Pilot Package

```bash
ai-linkedin build-live-test-package --week current
ai-linkedin pilot-checklist
```

This creates:
- v1 readiness report.
- live test runbook.
- Apps Script deployment package.
- isolated approval QA report.
- intelligence report.
- Friday dry-run report.
- production pilot checklist.

No Google deployment, email send, paid API call, or LinkedIn publishing call is made by this command.

## Production Pilot Control Run

Use the production-pilot command before the first operating week:

```bash
ai-linkedin run-production-pilot --week current --dry-run
```

When you are ready to fetch live public RSS sources, run without `--dry-run`:

```bash
ai-linkedin run-production-pilot --week current
```

This writes a production pilot report, refreshes the pilot checklist, runs preflight, runs the daily scan, runs the Friday package workflow, audits sources, and refreshes readiness. It still does not deploy Apps Script, send email, call paid APIs, or publish to LinkedIn.

## Build The First-Post Test Package

After live-source candidates exist, build a complete first-post test package:

```bash
ai-linkedin build-production-test-package --week current
```

This creates:
- selected topic and candidate shortlist.
- saved draft in the active database.
- approval packet and token record.
- ReviewQueue CSV.
- local notification text/HTML files.
- review queue validation report.
- production test runbook.

If the selected topic needs stronger source verification, the package is still useful for approval-flow testing, but it is not a public-post green light.

## Live Pilot Steps

The lowest-maintenance path is now local approval from the business console:

1. Open `AI LinkedIn Console.app`.
2. Press `Run Full E2E Test` when you want a complete local health check.
3. Press `Start Weekly Flow`.
4. Press `Build Production Test Package`.
5. Review the generated production test runbook and candidate shortlist.
6. Press `Approve Locally & Build Package`.
7. Post manually only after final human source review.
8. Paste the final LinkedIn post URL into the console and archive it.

Optional phone approval still uses Google Apps Script:

1. Deploy the Apps Script package manually.
2. Add `GOOGLE_APPS_SCRIPT_WEBAPP_URL` to `.env`.
3. Paste/import the review queue CSV into the Sheet.
4. Open the magic link on iPhone and approve/reject.
5. Export the Sheet as CSV.
6. Validate and import the CSV.

Manual checklist updates are available for human-only gates:

```bash
ai-linkedin pilot-checklist --mark apps_script_deployed --status done --notes "Deployed latest web app."
ai-linkedin pilot-checklist --mark weekly_candidates_reviewed --status done --notes "Reviewed source quality."
ai-linkedin pilot-checklist --mark iphone_magic_link_tested --status done --notes "Approved on iPhone."
```

## Boundaries

- No action means no post.
- Approval does not publish.
- LinkedIn API publishing remains disabled.
- Media remains separate and disabled by default.
