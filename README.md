# AI LinkedIn Thought Leadership Automation

A zero-spend system for producing one thoughtful AI-related LinkedIn post per week with human approval.

## Quick Start

After setup, double-click `AI LinkedIn Console.app`. The fallback launcher is
`Launch AI LinkedIn Console.command`.

Inside the browser console, press **Prepare Everything**. That creates or repairs
the desktop app, prepares the approval deployment files, runs local approval QA,
builds schedule files, and refreshes the plain-English pilot checklist.

Press **Put App On Desktop** once to copy the app bundle to the macOS Desktop.
Press **Run System Check** when you want a business-readable functional
diagnostics report across the local launcher, data, guardrails, approval setup,
pilot package, and setup artifacts.

For developer setup:

1. Create virtual environment: `python3 -m venv .venv && source .venv/bin/activate`
2. Install: `python -m pip install -e ".[dev]"`
3. Initialize: `ai-linkedin init-db`
4. Run tests: `pytest`

## Core CLI

```bash
ai-linkedin init-db
ai-linkedin preflight
ai-linkedin load-sources
ai-linkedin ingest --dry-run
ai-linkedin ingest
ai-linkedin score --week current
ai-linkedin run-daily-scan
ai-linkedin build-weekly-package --week current
ai-linkedin run-friday-package --week current
ai-linkedin editorial-review --draft-id DRAFT_ID
ai-linkedin record-edit-learning --what-changed "..." --pattern "..."
ai-linkedin create-approval-packet --draft-id DRAFT_ID
ai-linkedin export-review-queue --week current
ai-linkedin validate-review-queue --csv exported_review_queue.csv
ai-linkedin import-review-queue --csv data/review_packets/YYYY-Www/review_queue.csv
ai-linkedin build-notification-package --draft-id DRAFT_ID
ai-linkedin build-reminder-package --draft-id DRAFT_ID --kind friday
ai-linkedin build-reminder-package --draft-id DRAFT_ID --kind monday
ai-linkedin integration-status
ai-linkedin audit-sources --week current
ai-linkedin cluster-topics --week current
ai-linkedin build-discovery-queue --week current
ai-linkedin build-citation-matrix --draft-id DRAFT_ID
ai-linkedin build-intelligence-report --week current --draft-id DRAFT_ID
ai-linkedin validate-approval-webapp
ai-linkedin build-approval-deployment-package --week current
ai-linkedin run-approval-qa --action approve_text_only
ai-linkedin v1-readiness
ai-linkedin build-live-test-package --week current
ai-linkedin pilot-checklist
ai-linkedin run-production-pilot --week current --dry-run
ai-linkedin build-production-test-package --week current
ai-linkedin prepare-business-console --week current
ai-linkedin build-local-schedule-package
ai-linkedin build-manual-posting-package --draft-id DRAFT_ID
ai-linkedin archive-post --draft-id DRAFT_ID --post-url LINKEDIN_POST_URL
ai-linkedin publish --draft-id DRAFT_ID
```

`publish` is intentionally blocked in v0 unless the disabled LinkedIn API adapter is explicitly enabled later. Approved drafts can be packaged for assisted manual posting.

## Features

- **Hard Zero Mode**: No paid APIs, no spending.
- **Safe ingestion**: RSS feeds, manual links, no scraping.
- **Deterministic scoring**: Topic evaluation without AI.
- **Human approval**: Magic link review on mobile.
- **Local notifications**: Outlook-copyable HTML/text files plus matching review queue CSV; no Graph sending.
- **Manual posting**: Assisted copy-paste to LinkedIn.
- **Integration status**: Local report showing which future adapters remain disabled.
- **Operational run reports**: Daily scan and Friday package workflows write local reports.
- **Content intelligence**: Source audit, topic clustering, discovery queue, and citation matrix outputs.
- **Approval QA**: Apps Script contract validation, deployment package, and isolated CSV round-trip QA.
- **Live pilot readiness**: v1.0 readiness report, live-test runbook, and dashboard endpoints.
- **Production pilot hardening**: Pilot checklist, pre-import Sheet validation, and production-pilot run reports.
- **Production test package**: Selected live topic, draft, approval packet, notification files, Sheet CSV, validation, and runbook.
- **Business console**: Browser-first workflow with next best action, setup, CSV paste/import, artifact viewer, manual package creation, and archive controls.
- **Touch-free desktop launcher**: Double-clickable macOS app plus browser setup flow for non-technical operators.
- **Functional diagnostics**: Browser and CLI report for launcher, database, guardrails, readiness, approval package, pilot package, and setup artifacts.
- **Schedule package**: Optional macOS launchd files are generated locally but never installed automatically.

## Architecture

- SQLite for data.
- YAML for config.
- argparse CLI.
- Markdown outputs.
- Google Apps Script for approval.

## Safety

- No publishing without approval.
- No paid API calls in default mode.
- No confidential data storage.
- No LinkedIn/X scraping.

## GitHub Backup

See `docs/github_migration.md` before pushing this project to GitHub. The
`.gitignore` is set up to keep local databases, generated packages, approval
artifacts, manual link CSVs, desktop app bundles, and secrets out of version
control.
