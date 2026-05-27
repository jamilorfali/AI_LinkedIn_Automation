# AI LinkedIn Thought Leadership Automation - Progress Report & Continuation Guide

**Date:** May 18, 2026  
**Current Status:** Phase 19 Feedback Iteration Complete (Diverse Source Refresh, Undo, Consumer Google Deployment Guidance, Content-Aware Image Planning, and Draft Controls)  
**Next Milestone:** User product test the refreshed guided web UI from Start -> pick topic -> Draft -> Source Looks OK -> edit buttons -> Approve Draft -> Make Package -> Copy Post Text -> Generate Safe Image -> manual LinkedIn post -> Save Final URL

---

## Phase 19 Feedback Iteration - May 18, 2026

This pass addressed the latest hands-on testing feedback around overly technical arXiv-heavy suggestions, confusing full-refresh behavior, Google Apps Script deployment friction, generic image output, and missing draft-length controls.

**Implemented:**
- Broadened active source coverage beyond arXiv with MIT Technology Review, Microsoft Research, Google Research, Google Cloud AI/ML, NVIDIA AI, VentureBeat AI, The Verge AI, MIT News, NIST, and curated high-trust business sources.
- Added Start-page `Full Refresh Topics` and `Undo Refresh` controls.
- Full refresh now hides the current board/build, seeds 12 business-friendly replacement topics from diverse verifiable sources, avoids repeated titles, clears the stale package state, and keeps Undo available.
- Full refresh and new topic selection now reset the human source-review gate so an old `Source Looks OK` click cannot accidentally approve a new topic.
- The Start next-action button now says `Show Topic Board` after a refresh instead of trying to build a stale posting package.
- Updated the Google Apps Script manifest and deployment checklist so consumer Google accounts see the `Web app` deployment type; instructions now explain saving/reloading if only `API Executable` appears.
- Added click-only draft edit presets for longer, more detail, more concise, less detail, business-friendly, and sharper tone options.
- Reworked safe image generation into a local Locus-style scene planner that creates original content-aware PNG visuals instead of abstract blobs.
- Added UI guardrails so `Source Looks OK` and `Approve Draft` provide visible error feedback when clicked too early.

**Verification:**
- Focused tests: `14 passed`.
- Full suite: `104 passed, 6 skipped`.
- Ruff lint: passed.
- Running API smoke confirmed the refreshed board has 12 non-arXiv suggestions from NIST, Brookings, Google Cloud, Microsoft WorkLab, MIT Sloan, BCG, MIT News, McKinsey, Stanford HAI, WEF, Pew, and HBR.
- Non-mutating browser smoke confirmed Start-page topic controls, visual click feedback, and precondition errors for source review and approval.

---

## Codex Deep Dive Update - May 14, 2026

A structural review found that the previous implementation was useful as an early prototype, but it overstated completion in several safety-critical areas. The largest issue was architectural: scoring only decorated `findings`, approvals were not tied to exact draft versions and content hashes, publishing safety did not exist, Cost Guard was config-only, and the weekly package did not follow the review-packet workflow described in the build guide.

**Changes made in this review pass:**
- Added a central SQLite gateway with path resolution, foreign key enforcement, transactions, and lightweight migrations.
- Added stable finding IDs and safer manual CSV parsing.
- Reworked scoring so each finding becomes a traceable topic candidate with scorecard fields, risk gating, and recommendations.
- Moved weekly output into `data/review_packets/YYYY-Www/weekly_brief.md` plus a no-API prompt packet.
- Replaced the hype-prone draft template with a plain, practical starter draft.
- Added approval records that store draft ID, draft version, and content hash.
- Added local approval packet JSON export and Google Sheets-compatible review queue CSV export.
- Added Cost Guard enforcement module.
- Added publishing safety gate and manual posting package builder; live LinkedIn publishing remains blocked by default.
- Added Google Apps Script scaffold files under `apps_script/approval_webapp/`.
- Added tests for Cost Guard, review packets, and publishing safety gate.

**Verification note:** Source compilation and a focused end-to-end smoke workflow passed. Full `pytest` could not be run in the current local environment because available Python executables are 3.9.6, the project declares Python 3.11+, and `pytest` is not installed.

---

## Detailed Build Guide Reconciliation - May 14, 2026

The downloaded guide `AI_LINKEDIN_AUTOMATION_CODEX_BUILD_GUIDE_v0_2_DETAILED.md` was reviewed against the repo. It is more complete than the in-repo guide and expects additional config files, docs, prompts, style assets, provider adapters, and source governance scaffolding.

**Reconciliation changes made:**
- Added missing config files: `weekly_schedule.yaml`, `blocked_topics.yaml`, `trusted_domains.yaml`, `provider_registry.yaml`, and `publishing.yaml`.
- Expanded `sources.yaml` with the fuller source registry from the guide while keeping RSS/arXiv ingestion safe and public-web sources registered for later extraction.
- Added documentation files for architecture, operating model, local setup, Apps Script setup, approval flow, source governance, future LinkedIn API work, and troubleshooting.
- Added all prompt assets `00` through `10` for guardrails, scoring, hidden-gem detection, claims, citations, executive translation, drafting, voice review, political risk, vendor sensitivity, and media recommendations.
- Added style assets for personal voice, banned AI giveaways, approved samples, and edit learning.
- Added provider adapter scaffolds for `no_api`, OpenAI, Claude, and Gemini; external provider adapters remain disabled and call Cost Guard before doing anything.
- Added a future LinkedIn adapter scaffold that always routes through the publishing safety gate.
- Added compatibility modules for ingestion, scoring, storage, paths, logging, models, and utilities to match the guide’s intended adapter seams.
- Expanded the SQLite schema and migrations with guide-compatible fields for runs, sources, findings, topics, claims, drafts, media assets, approvals, posts, and cost audit records.
- Added missing safety tests for expired tokens, social-signal source gating, high political risk, vendor scorekeeping, and media requiring separate approval.

**Verification note:** Compilation, database migration, source loading, ingestion dry-run, weekly package dry-run, CLI help, and the focused end-to-end smoke workflow passed. Full `pytest` remains blocked until Python 3.11+ and test dependencies are installed.

---

## Phase 4 Implementation - May 14, 2026

Phase 4 assisted manual posting is now implemented end to end.

**Implemented:**
- `ai-linkedin import-review-queue --csv ...` imports approval actions from a Google Sheets-compatible review queue CSV.
- Review queue import validates review ID, draft ID, draft version, and content hash before creating approval records.
- Imported approvals update token usage and draft status.
- Manual posting packages now include source links when topic findings are available and include the follow-up archive command.
- Manual posting packages use draft-specific filenames to avoid overwriting multiple packages in the same week.
- `ai-linkedin archive-post --draft-id ... --post-url ...` records the final manually posted LinkedIn URL in the `posts` table.
- Added Phase 4 tests covering CSV import, content hash mismatch rejection, manual package contents, and post archive records.

**Verification:**
- Full test suite: 32 passed, 2 skipped in the Codex sandbox. The two skipped tests are local UI socket tests that pass in the user's Terminal.

---

## Phase 5 Implementation - May 14, 2026

Phase 5 editorial intelligence is now implemented as a deterministic local review layer.

**Implemented:**
- `ai-linkedin editorial-review --draft-id ...` creates a markdown and JSON editorial review packet.
- Draft claims are extracted and classified as supported, weak support, unsupported, or remove.
- Extracted draft claims are persisted in the `claims` table for the draft's topic.
- Editorial review summaries are persisted in the new `editorial_reviews` table.
- Voice/style checks apply banned phrase, vendor scorekeeping, political risk, length, punctuation, and hashtag rules.
- Approval packet creation now runs editorial review and includes claim notes, voice checklist, editorial status, and review path.
- `ai-linkedin record-edit-learning --what-changed ... --pattern ...` appends lessons to `style/edit_learning_log.md`.
- Final post archiving records an edit-learning note when the archived final text differs from the approved draft.
- Weekly recommendation notes now include more explicit score rationale.

**Verification:**
- Phase 5 tests: 4 passed.
- Full test suite in Codex sandbox: 36 passed, 2 skipped. The skipped tests are local UI socket tests that pass in the user's Terminal.

---

## Phase 6 Implementation - May 14, 2026

Phase 6 is implemented as a safe local integration layer, not live API automation.

**Implemented:**
- `ai-linkedin build-notification-package --draft-id ...` creates local Outlook-copyable HTML, text, and metadata files.
- Notification packages create a matching approval packet, export the review queue CSV, and include the review target while making clear that no action means no post.
- `ai-linkedin build-reminder-package --draft-id ... --kind friday|monday` creates local non-response reminder packages.
- Notification/reminder packages are blocked once a draft already has an approval decision.
- `ai-linkedin integration-status` reports local paths, disabled future adapters, and Cost Guard decisions.
- Added `config/integrations.yaml` to explicitly keep Google Sheets API write-back, Microsoft Graph email sending, LinkedIn OAuth/API, and media generation disabled.
- Expanded Cost Guard blocked providers to include Google Sheets API, Microsoft Graph/Outlook Graph, and media generation.
- Added Phase 6 tests for notification files, reminder files, integration status, paid provider blocking, and LinkedIn adapter blocking.

**Verification:**
- Phase 6 tests: 6 passed.
- Full test suite in Codex sandbox: 42 passed, 2 skipped. The skipped tests are local UI socket tests that pass in the user's Terminal.

---

## Phase 7 Implementation - May 14, 2026

Phase 7 makes the local operating loop repeatable without enabling background jobs automatically.

**Implemented:**
- `ai-linkedin preflight` runs local readiness checks for Python, storage, SQLite, sources, Cost Guard, publishing safety, optional integrations, and approval URL setup.
- `ai-linkedin run-daily-scan` orchestrates database init/migration, source loading, ingestion, scoring, and writes a markdown/JSON run report.
- `ai-linkedin run-friday-package --week current` scores pending findings, builds the weekly brief and prompt packet, and writes a markdown/JSON run report.
- `ai-linkedin build-local-schedule-package` generates macOS `launchd` plist files and a runbook under `data/exports/schedule/`.
- The schedule package does not install, load, email, publish, or enable paid providers.
- Added Phase 7 tests for preflight status, daily workflow reports, Friday package outputs, and schedule package generation.

**Verification:**
- Phase 7 tests: 4 passed.
- Full test suite in Codex sandbox: 46 passed, 2 skipped. The skipped tests are local UI socket tests that pass in the user's Terminal.
- Full-project Ruff lint: passed.

---

## Phase 8 Implementation - May 14, 2026

Phase 8 adds a heavier local content-intelligence layer for better recommendations and more trustworthy citation review.

**Implemented:**
- Added persistent tables for content clusters, cluster membership, source audit findings, discovery queue items, and citation matrix rows.
- `ai-linkedin audit-sources --week ...` audits active sources against trusted domain policy, trust tiers, social-source rules, and public-web extraction limitations.
- `ai-linkedin cluster-topics --week ...` clusters local findings/topic candidates using deterministic token overlap and ranks draft candidates vs. verification/watch queues.
- `ai-linkedin build-discovery-queue --week ...` generates markdown, JSON, and CSV for findings that need verification, stronger sources, or human review.
- `ai-linkedin build-citation-matrix --draft-id ...` creates a claim/source matrix with publishable support counts, unsupported counts, and source-role notes.
- `ai-linkedin build-intelligence-report --week ...` runs source audit, clustering, discovery queue, and optional citation matrix generation together.
- Approval packet creation now builds a citation matrix and includes `citation_matrix_path` plus citation summary counts.
- Friday workflow now builds intelligence outputs alongside the weekly brief and no-API prompt packet.
- Added Phase 8 tests for source audit persistence, clustering, discovery queue generation, citation matrix persistence, approval packet citation metadata, and aggregate intelligence report output.

**Verification:**
- Phase 8 tests: 6 passed.
- Full test suite in Codex sandbox: 52 passed, 2 skipped. The skipped tests are local UI socket tests that pass in the user's Terminal.
- Full-project Ruff lint: passed.
- Intelligence CLI smoke checks passed for source audit, clustering, discovery queue, aggregate intelligence report, Friday dry-run, preflight, and health status.

---

## Phase 9 Implementation - May 14, 2026

Phase 9 hardens the Apps Script approval path and adds a local QA harness for the approval/write-back/import/manual-package loop.

**Implemented:**
- Apps Script `Code.gs` now has explicit `REQUIRED_HEADERS`, centralized column validation, and shared allowed action definitions.
- Apps Script mobile page now displays recommendation, political risk, draft readiness, and a clear no-publishing warning.
- `ai-linkedin validate-approval-webapp` validates required files, functions, headers, allowed actions, mobile viewport, no-publish warning, and manifest scope.
- `ai-linkedin build-approval-deployment-package --week ...` creates local copy/paste Apps Script files, Sheet header template CSV, deployment checklist, manifest, and validation report.
- `ai-linkedin run-approval-qa --action approve_text_only` creates an isolated QA database, approval packet, notification package, review queue CSV, simulated Sheet export, imported approval record, manual posting package, and live-publish block check.
- Added Phase 9 tests for contract validation, missing-script detection, Sheet template headers, deployment package generation, and full local approval QA round trip.

**Verification:**
- Phase 9 tests: 5 passed.
- Full test suite in Codex sandbox: 57 passed, 2 skipped. The skipped tests are local UI socket tests that pass in the user's Terminal.
- Focused Ruff lint: passed.

---

## Phase 10 Implementation - May 14, 2026

Phase 10 accelerates the project into live-pilot readiness and operational visibility.

**Implemented:**
- `ai-linkedin v1-readiness` builds a live-testing readiness report with preflight, Apps Script contract, approval URL status, integration guardrails, DB counts, and latest artifact paths.
- `ai-linkedin build-live-test-package --week ...` creates a consolidated pilot package with readiness report, live test runbook, approval deployment package, isolated approval QA, intelligence report, and Friday dry-run report.
- Added dashboard API endpoints for overview counts, preflight, live readiness, integration status, artifacts, daily scan, Friday package, and live-test package generation.
- Rebuilt the local dashboard UI around live testing readiness, guardrails, artifacts, workflows, drafting, and config editing.
- Added `docs/live_testing.md` with the real pilot sequence.
- Added Phase 10 tests for readiness, live-test package generation, latest artifact discovery, dashboard endpoint contracts, and dashboard controls.

**Verification:**
- Phase 10 tests: 4 passed, 1 skipped in Codex sandbox. The skipped test is a local socket endpoint test that passes in the user's Terminal environment.
- Full test suite in Codex sandbox: 61 passed, 3 skipped. The skipped tests are local UI socket tests.
- Full-project Ruff lint: passed.
- Local dashboard server was started with approval; `/api/overview`, `/api/live-readiness`, and dashboard HTML controls were verified over HTTP.
- `v1-readiness` and `build-live-test-package --week current` CLI smoke checks passed.

---

## Phase 11 Implementation - May 14, 2026

Phase 11 hardens the system for the first production-style pilot week.

**Implemented:**
- `ai-linkedin pilot-checklist` creates a persistent production pilot checklist with auto-detected gates and manual confirmation gates.
- `ai-linkedin pilot-checklist --mark ... --status ... --notes ...` records human-only setup steps such as Apps Script deployment, weekly candidate review, and iPhone magic-link testing.
- `ai-linkedin validate-review-queue --csv ...` validates exported Google Sheet CSV headers, review IDs, draft IDs, draft versions, content hashes, duplicate decisions, and approval actions before import.
- `ai-linkedin run-production-pilot --week current [--dry-run]` runs the production-pilot control loop: preflight, source loading, daily scan, Friday package, source audit, readiness, checklist refresh, and a consolidated run report.
- Added dashboard API endpoints and controls for the pilot checklist, production pilot run, checklist updates, and Sheet CSV validation.
- Source audit output now separates informational source-governance findings from warnings/failures.
- Readiness artifact discovery now includes production pilot reports, pilot checklist, and review queue validation reports.
- Added `docs/live_testing.md`, `docs/operating_model.md`, `docs/troubleshooting.md`, and README updates for the production pilot path.
- Added Phase 11 tests for checklist persistence, review queue validation, hash mismatch detection, production pilot reporting, and dashboard controls.

**Verification:**
- Phase 11 tests: 5 passed.
- Full test suite in Codex sandbox: 66 passed, 3 skipped. The skipped tests are local UI socket tests.
- Full-project Ruff lint: passed.
- CLI smoke checks passed for `pilot-checklist`, `run-production-pilot --dry-run`, `validate-review-queue`, and source audit info/warn/fail output.

---

## Phase 12 Implementation - May 14, 2026

Phase 12 turns the live-candidate database into a first-post production testing package.

**Implemented:**
- `ai-linkedin build-production-test-package --week current` selects a live topic candidate, creates a candidate shortlist, generates a topic-specific draft, saves it, builds the approval packet, creates local notification files, exports ReviewQueue CSV, validates the CSV, refreshes the pilot checklist, and writes a production test runbook/manifest.
- Added topic-specific draft generation so explicit topic IDs no longer rely on the first weekly-brief option.
- Added candidate publish-readiness labeling so source-verification candidates can be used for approval-flow testing without implying public-post readiness.
- Fixed a production rebuild bug where regenerated draft claims could be blocked by older citation-matrix foreign keys.
- Tightened pilot checklist logic so empty or pending-only CSV validation no longer marks the import gate complete.
- Added dashboard support for building a production test package from the local UI.
- Updated readiness artifact discovery to include production test runbooks.
- Updated README, live testing docs, operating model, troubleshooting, and architecture docs.
- Added Phase 12 tests for production package creation, explicit topic selection, checklist validation gating, and dashboard controls.

**Verification:**
- Phase 12 tests: 5 passed.
- Full test suite in Codex sandbox: 71 passed, 3 skipped. The skipped tests are local UI socket tests.
- Full-project Ruff lint: passed.
- CLI smoke check built a real production test package from the active live-candidate database.

---

## Phase 13 Implementation - May 14, 2026

Phase 13 turns the project from a developer-operated CLI into a business-user console.

**Implemented:**
- Rebuilt `ui/index.html` into a browser-first business console with next best action, production flow controls, current package summary, approval Sheet return, manual posting, checklist, artifact viewer, and activity log.
- Added `business_console.py` as the UI operations layer for next-action logic, `.env` approval URL saving, latest production package discovery, artifact preview, pasted CSV validation/import, manual package creation, and post archive.
- Added UI/API endpoints for `/api/business/home`, approval deployment bundle viewing, approval URL saving, pasted ReviewQueue CSV validation/import, manual package creation, post archive, schedule package generation, and artifact preview.
- Added `Launch AI LinkedIn Console.command`, a double-click Mac launcher that starts the local server and opens the browser console.
- Added browser-visible approval deployment bundle output so `Code.gs`, `Index.html`, `appsscript.json`, Sheet header, and checklist can be copied without opening VS Code.
- Added `docs/business_console.md` plus README, operating model, and troubleshooting updates.
- Added Phase 13 tests for `.env` updates, business-home next action, pasted CSV import path, artifact path safety, console UI presence, launcher executability, and API contract.

**Verification:**
- Phase 13 tests: 6 passed, 1 skipped in Codex sandbox. The skipped test is a local socket test.
- Full-project Ruff lint: passed.
- Local HTTP smoke checks passed for `/api/business/home`, `/api/business/approval-deployment`, and the console HTML.

---

## Phase 14 Implementation - May 18, 2026

Phase 14 completes the touch-free local operation layer for non-terminal use.

**Implemented:**
- Desktop launcher package generation creates `AI LinkedIn Console.app` plus fallback command launcher files.
- Desktop icon installation copies a runnable app bundle to the macOS Desktop.
- Touch-free setup builds the console, approval deployment files, local approval QA artifacts, schedule package, and pilot checklist from one flow.
- Approval setup guide tracks the human Google Apps Script deployment gate, local QA readiness, and approval URL configuration.
- Functional diagnostics report the launcher, desktop icon, SQLite database, readiness, guardrails, approval package, production package, checklist, and touch-free setup artifacts.
- The UI exposes plain-English workflow navigation, setup, weekly pilot, approval, posting, progress, artifacts, and activity controls.

**Verification:**
- Phase 14 focused tests passed on May 18, 2026 as part of the Phase 14-16 run: 18 passed, 1 skipped.
- `ai-linkedin business-diagnostics` passed on May 18, 2026.

---

## Phase 15 Implementation - May 18, 2026

Phase 15 adds a local Locus-compatible workflow engine layer while preserving Hard Zero Mode.

**Implemented:**
- `ai-linkedin locus-status` reports local workflow engine state, provider mode, SDK capability, and install guidance.
- `ai-linkedin locus-capability-check` exercises available Locus SDK primitives when installed.
- Daily scan, Friday package, and production pilot workflows write Locus trace and orchestration metadata.
- Integration status includes Oracle Locus as a non-paid, local workflow engine option.
- `ai-linkedin build-locus-workbench-package` exports workflow manifests and Mermaid diagrams for daily scan, Friday package, production pilot, and production test package flows.
- The console includes workflow engine controls for status, capability testing, and workbench export.

**Verification:**
- `ai-linkedin run-locus-e2e-test` passed on May 18, 2026.
- Locus E2E report: `data/exports/business_console/LOCUS_E2E_REPORT.md`.

---

## Phase 16 Implementation - May 18, 2026

Phase 16 validates the whole local application loop without requiring Google Sheet CSV glue for the happy path.

**Implemented:**
- Local approval flow can approve the latest draft and immediately build the manual posting package.
- Application E2E test prepares the business console, runs the production pilot, builds a production test package, approves locally, creates the manual posting package, and runs functional diagnostics.
- Locus E2E test validates workflow engine capabilities, daily scan graph, Friday package graph, production pilot graph, and workflow map export.
- Business console defaults to the local approval path for least-maintenance operation while keeping the Google Apps Script mobile approval path available.

**Verification:**
- `ai-linkedin run-application-e2e-test` passed with warnings on May 18, 2026. Warnings are the intended human gates: source review before posting and final LinkedIn URL archive after manual posting.
- `ai-linkedin run-locus-e2e-test` passed on May 18, 2026.
- Focused Phase 14-16 tests: 18 passed, 1 skipped on May 18, 2026.
- Current diagnostics: `data/exports/business_console/FUNCTIONAL_DIAGNOSTICS.md`.

---

## Phase 17 Implementation - May 18, 2026

Phase 17 converts the console from a developer-style dashboard into a business-user guided product flow.

**Implemented:**
- Reworked the first screen into a "Start Here" wizard with seven plain-language steps: prepare, build draft, check source, tune draft, approve, make package, and save final URL.
- Added backend `journey_steps` and `draft_workspace` to `/api/business/home` so the UI can explain what to do without exposing file-path thinking first.
- Added click-only draft revision presets: shorter, warmer, executive, safer, simpler, stronger first line, and start over safely.
- Draft revisions create a brand-new draft version, refresh approval artifacts, update the latest package pointer, and require a fresh approval for the new content hash.
- Added source-review and topic-change controls so a non-technical user can reject a weak topic without touching the terminal.
- Simplified approval into a human gate: approve the exact on-screen draft, ask for edits, or pick a different topic.
- Simplified posting into final-copy preview, copy post text, open LinkedIn, and save the final URL.
- Kept advanced setup, phone approval, Locus diagnostics, artifacts, and maintenance tools available but no longer as the primary path.

**Verification:**
- Added Phase 17 tests for wizard state, click-only draft revision, and UI contract language.
- Focused Phase 13/14/16/17 tests: 20 passed, 2 skipped.
- Full test suite: 98 passed, 6 skipped.
- Ruff lint: passed.
- Local console restarted at `http://127.0.0.1:8000/` and `/api/business/home` smoke check confirmed the new `journey_steps` and `draft_workspace` response.

---

## Phase 18 Feedback Iteration - May 18, 2026

Phase 18 addresses the first hands-on business-user testing feedback against the guided web UI.

**Implemented:**
- Added visible button feedback across the core workflow: running state, success/error outlines, and toast messages.
- Fixed `Source Looks OK` so it updates the source-review status text and shows a success toast after the click.
- Fixed `Approve Draft & Make Package` so it moves to `Post`, not `Files`.
- Fixed `Make Package` so it stays on `Post`, not `Files`.
- Changed `Copy Post Text` to copy only the LinkedIn-ready final post body, not the markdown package, internal notes, source metadata, or truncated summaries.
- Added `Copy Abstract`, `Copy Source Link`, `Generate Safe Image`, and `Copy Image Path` to the posting flow.
- Added safe local original PNG image generation with a guardrail manifest, keeping Hard Zero Mode intact.
- Added a grouped Start-page topic board with 10+ topic options, topic-category grouping, and an up-to-50-word custom topic builder.
- Added starter topic suggestions for low-data states so the Start page still has business-friendly choices.
- Added an approval preview that shows the exact post text that will be copied after approval.
- Removed duplicate button IDs and added a regression test for unique UI IDs.
- Updated manual posting packages to keep the copy/paste body free of source footers and operator-only notes.
- Kept Oracle Locus workflow usage active through the local StateGraph-backed production-test package path when the SDK is installed.

**Verification:**
- Full test suite: 102 passed, 6 skipped.
- Ruff lint: passed.
- Local HTTP smoke checks passed for `/api/business/home`, `/api/business/topic-board`, and the served UI HTML.
- Headless Chrome UI smoke passed against `http://127.0.0.1:8000/`: custom topic build, source review feedback, final-polish edit, approval routing to `Post`, manual package staying on `Post`, clean post-text clipboard copy, and safe image preview.

---

## Executive Summary

This is a zero-spend, human-approved automation system for producing one thoughtful AI-related LinkedIn post per week. The system ingests public AI news from RSS feeds and manual links, scores content deterministically, generates draft posts, and requires explicit human approval before any publishing attempt.

**Current Working Features:**
- ✅ Database initialization and schema
- ✅ YAML configuration loading
- ✅ RSS feed ingestion (arXiv AI)
- ✅ Manual link ingestion from CSV
- ✅ Deterministic content scoring
- ✅ Weekly review package and no-API prompt packet generation
- ✅ Approval packet, token generation, review queue export/import, and validation
- ✅ Deterministic editorial review with claim and voice checks
- ✅ Assisted manual posting package and post archive
- ✅ Local notification and reminder package generation
- ✅ Integration status reporting for optional future adapters
- ✅ Preflight checks, workflow reports, and optional local schedule package generation
- ✅ Content intelligence reports, source governance audit, topic clustering, discovery queue, and citation matrix
- ✅ Apps Script validation/deployment package and isolated approval QA round trip
- ✅ v1 readiness report, live-test package, dashboard visibility, and live-pilot runbook
- ✅ Production pilot checklist, Sheet CSV validation, and pilot run reporting
- ✅ First-post production test package with selected topic, draft, approval packet, notification files, ReviewQueue CSV, validation, and runbook
- ✅ Browser-first business console and double-click launcher for no-terminal local operation
- ✅ Touch-free setup, functional diagnostics, and local approval happy path
- ✅ Locus-compatible local workflow orchestration, traces, and workbench export
- ✅ Application and Locus E2E validation reports
- ✅ Showtime Wizard UI with start-to-finish guided steps and click-only draft tuning
- ✅ Product-test feedback fixes for visible click feedback, clean copy, topic selection, approval routing, and safe image generation
- ✅ CLI interface with core commands
- ✅ Web UI server for status viewing
- ✅ Comprehensive test suite

**Safety Implemented:**
- Hard Zero Mode (no paid APIs by default)
- Cost Guard blocks paid-capable providers and live API adapters
- Publishing blocked without approval
- Token hashing (raw tokens not stored)
- Source trust tiers prevent weak claims
- Notification packages send nothing automatically
- No LinkedIn/X scraping

---

## Project Architecture

### Core Components

```
ai-linkedin-automation/
├── AGENTS.md                          # Project rules and guidelines
├── pyproject.toml                     # Python package config
├── db/schema.sql                      # SQLite database schema
├── config/                            # YAML configuration files
│   ├── app.yaml                       # Main app settings
│   ├── sources.yaml                   # Source definitions
│   ├── scoring.yaml                   # Scoring rules and weights
│   ├── integrations.yaml              # Disabled future integration switches
│   └── cost_guard.yaml                # API cost controls
├── src/ai_linkedin_automation/
│   ├── cli.py                         # Command-line interface
│   ├── config.py                      # Configuration loading
│   ├── storage/db.py                  # Database operations
│   ├── ingestion/                     # Data collection
│   │   ├── sources.py                 # Source management
│   │   └── ingest.py                  # RSS/manual ingestion
│   ├── scoring/scoring.py             # Content scoring
│   ├── weekly/weekly.py               # Weekly package generation
│   ├── drafting.py                    # Draft post generation
│   ├── approval.py                    # Approval token system
│   ├── editorial/                     # Claim and voice review
│   ├── notifications/                 # Local Outlook-copyable packages
│   ├── integrations/                  # Optional adapter status reporting
│   ├── publishing/                    # Manual posting and disabled live adapter
│   └── ui_server.py                  # Web interface
├── tests/                             # Test suite
├── data/                              # Runtime data
│   ├── manual_links/inbox.csv         # Manual content input
│   ├── sqlite/                        # Database files
│   ├── exports/                       # Generated posting/notification outputs
│   └── review_packets/                # Weekly briefs and approval packets
└── apps_script/approval_webapp/       # Google Apps Script scaffold
```

### Data Flow

1. **Ingestion**: RSS feeds + manual links → Findings table
2. **Scoring**: Findings → Scores + categories
3. **Weekly Package**: Top findings → Markdown briefing
4. **Drafting**: Weekly package → LinkedIn post draft
5. **Editorial Review**: Draft → claim and voice checks
6. **Notification**: Draft + approval packet → local Outlook-copyable files
7. **Approval**: Draft + magic token → Approval record
8. **Publishing**: Approved draft → manual posting package and archive

---

## Current Implementation Status

### ✅ Completed (Phase 0-17)

#### Phase 0: Repo Skeleton & Safety Baseline
- Directory structure created
- SQLite schema implemented (matches guide)
- Basic CLI commands: `status`, `init-db`
- Configuration loading from YAML
- Virtual environment setup
- AGENTS.md with project rules

#### Phase 1: Ingestion MVP
- Source loading from `config/sources.yaml`
- RSS ingestion using feedparser
- Manual link ingestion from CSV
- Finding deduplication by content hash
- Run logging in database

**Commands Working:**
```bash
ai-linkedin load-sources
ai-linkedin ingest --dry-run
ai-linkedin ingest
```

#### Phase 2: Scoring & Weekly Package
- Deterministic scoring based on keywords
- Category assignment (high_impact, academic, industry, etc.)
- Weekly package generation from top findings
- Markdown output with findings list

**Commands Working:**
```bash
ai-linkedin score
ai-linkedin build-weekly-package --week current
```

#### Phase 3: Approval Packet & Google Review Scaffold
- ✅ Approval token generation (random strings)
- ✅ Token hashing with SHA-256
- ✅ Token validation and expiration
- ✅ Approval recording
- ✅ Google Apps Script files (manual deployment scaffold exists)
- ✅ Review queue CSV export/import
- ✅ Magic-link approval page scaffold

**Current CLI Commands:**
```bash
ai-linkedin generate-approval <draft_id>
ai-linkedin approve <token> <action> [--notes]
ai-linkedin create-approval-packet --draft-id DRAFT_ID
ai-linkedin export-review-queue --week current
ai-linkedin import-review-queue --csv data/review_packets/YYYY-Www/review_queue.csv
```

#### Phase 4: Assisted Manual Posting
- Publishing safety gate
- Manual posting package generation
- Post archiving

#### Phase 5: Editorial Intelligence
- Claim extraction
- Voice review
- Citation checking
- Edit learning log

#### Phase 6: Safe Local Integrations
- Outlook-copyable local notification and reminder packages
- Integration status reporting
- Explicitly disabled Google Sheets API, Microsoft Graph, LinkedIn API, paid model providers, and media generation

#### Phase 7: Operational Readiness
- Preflight/doctor checks
- Daily scan workflow report
- Friday package workflow report
- Generated macOS launchd schedule package, not installed automatically

#### Phase 8: Content Intelligence & Citation Trust
- Source governance audit
- Topic/finding clustering
- Discovery queue
- Citation validation matrix
- Approval-packet citation summary integration

#### Phase 9: Approval Web App Deployment & QA
- Apps Script contract validator
- Deployment package and Sheet template generator
- Isolated local approval round-trip QA
- Manual package creation after simulated Sheet import
- Live publishing remains blocked

#### Phase 10: Live Pilot Readiness & Dashboard
- v1 readiness report
- Consolidated live-test package and runbook
- Dashboard overview/readiness/artifacts/guardrails endpoints
- Redesigned local dashboard UI
- Live public-source pilot can begin after review of readiness report

#### Phase 11: Production Pilot Hardening
- Persistent production pilot checklist
- Review queue CSV validation before import
- Production pilot control run and consolidated report
- Dashboard controls for pilot checklist, CSV validation, and pilot run
- Source-audit info/warn/fail clarity

#### Phase 12: First-Post Production Testing Package
- Production test package builder
- Topic-specific draft generation
- Candidate publish-readiness labeling
- Approval packet, notification package, ReviewQueue CSV, validation, and runbook in one flow
- Checklist gate correction for empty/pending CSV validation
- Citation/claim rebuild safety fix

#### Phase 13: Business Console & Touch-Free Local Operation
- Browser-first business console
- Next best action engine
- Pasted Sheet CSV validation/import
- In-browser artifact and deployment file viewer
- Approval URL `.env` save from UI
- Manual posting package and archive controls
- Double-click Mac launcher

---

## Configuration Files Status

### ✅ Working Configurations

**config/app.yaml:**
```yaml
app:
  name: ai-linkedin-automation
  timezone: America/Chicago
  default_run_mode: hard_zero

storage:
  sqlite_path: data/sqlite/ai_linkedin_automation.db

review:
  approval_method: magic_link
  token_expiration_hours: 120

publishing:
  target: personal_linkedin_profile
  default_mode: assisted_manual
  require_approval_record: true
```

**config/sources.yaml:**
```yaml
recurring_sources:
  - id: arxiv_ai
    name: arXiv AI
    type: rss
    trust_tier: high_trust
    rss_url: http://export.arxiv.org/rss/cs.AI
    is_active: true
```

**config/scoring.yaml:**
```yaml
scoring_rules:
  - name: "AI Breakthrough"
    keywords: ["breakthrough", "revolutionary"]
    score: 10
    category: "high_impact"
  # ... more rules

weekly_package:
  max_findings: 10
  min_score: 5
  categories: [high_impact, academic, industry]
```

### 🚧 Needs Enhancement

**config/cost_guard.yaml:** Basic structure exists, needs full implementation
**config/style_rules.yaml:** Exists but not fully integrated
**apps_script/approval_webapp/:** Scaffold exists, needs implementation

---

## Test Suite Status

### ✅ Passing Tests
- `test_config.py` - Configuration loading
- `test_db.py` - Database initialization
- `test_ingestion.py` - RSS and manual link ingestion
- `test_scoring_weekly.py` - Scoring logic
- `test_approval.py` - Token generation and validation
- `test_drafting.py` - Basic draft generation
- `test_ui_server.py` - Web interface

### Test Coverage Areas
- Database schema creation
- Config file parsing
- RSS feed parsing
- Finding deduplication
- Scoring rule application
- Token hashing and validation
- Approval workflow

---

## CLI Commands Status

### ✅ Implemented
```bash
ai-linkedin status              # System status
ai-linkedin init-db            # Database setup
ai-linkedin load-sources       # Load sources from config
ai-linkedin ingest [--dry-run] # Run ingestion
ai-linkedin score              # Score findings
ai-linkedin generate-approval  # Create approval token
ai-linkedin approve            # Record approval
```

### ❌ Missing (Need Implementation)
```bash
ai-linkedin build-weekly-package    # Generate weekly briefing
ai-linkedin create-approval-packet  # Export review packet
ai-linkedin export-review-queue     # CSV for Google Sheets
ai-linkedin build-manual-posting-package  # Manual posting prep
ai-linkedin publish                 # Publishing (blocked by default)
```

---

## Key Code Files Analysis

### Core Modules

**config.py:**
- Loads YAML files from config/
- Merges with environment variables
- Validates run modes
- Provides typed Config object

**storage/db.py:**
- SQLite connection management
- Schema application
- Transaction helpers

**ingestion/ingest.py:**
- RSS feed fetching with feedparser
- Manual CSV processing
- Content hashing for deduplication
- Finding storage

**scoring/scoring.py:**
- Keyword-based scoring
- Category assignment
- Database updates

**approval.py:**
- Cryptographically secure token generation
- SHA-256 hashing
- Expiration checking
- Approval recording

### Database Schema
- Full schema implemented matching guide
- Foreign key constraints enabled
- All required tables: runs, sources, findings, topics, drafts, approvals, etc.

---

## Safety & Security Implementation

### ✅ Implemented Safeguards
1. **Hard Zero Mode**: No paid APIs by default
2. **Approval Required**: Publishing blocked without approval record
3. **Token Security**: Raw tokens never stored, only hashes
4. **Source Trust**: Only high_trust sources can support publishable claims
5. **No Scraping**: Only RSS and manual public links
6. **Cost Guard**: Framework exists (needs full implementation)

### Risk Mitigation
- All publishing attempts logged and blocked by default
- Content hash verification for approvals
- Token expiration prevents stale approvals
- Manual review required for all outputs

---

## Demo Script Status

**demo.sh** provides end-to-end workflow:
1. Environment setup
2. Database initialization
3. Source loading
4. Ingestion (dry-run + real)
5. Scoring
6. Draft generation with approval workflow

**Status:** Working for implemented features

---

## Web UI Status

**ui_server.py:** Basic Flask server showing:
- System status
- Recent runs
- Findings count
- Approval status

**Status:** Functional for monitoring

---

## Next Steps for Continuation

### Immediate Priorities (Complete Phase 3)

1. **Implement Weekly Package CLI Command**
   - Add `build-weekly-package` to cli.py
   - Integrate with weekly/weekly.py
   - Test end-to-end package generation

2. **Complete Approval Packet Export**
   - Implement `create-approval-packet` command
   - Generate JSON review packets
   - Add CSV export for Google Sheets

3. **Google Apps Script Implementation**
   - Create HTML approval page
   - Implement magic link handling
   - Add mobile-friendly interface

### Medium-term Goals (Phase 4)

4. **Assisted Manual Posting**
   - Implement publishing safety gate
   - Create manual posting packages
   - Add post archiving

5. **Enhanced Weekly Package**
   - Add topic clustering
   - Improve recommendation logic
   - Include prompt packets for AI drafting

### Long-term Vision (Phase 5-6)

6. **Editorial Intelligence**
   - Claim extraction and validation
   - Voice consistency checking
   - Citation verification

7. **API Integrations** (Optional)
   - Google Sheets sync
   - Outlook notifications
   - LinkedIn API (future)

---

## Development Environment

### Prerequisites
- Python 3.11+
- SQLite 3
- Virtual environment

### Setup Commands
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ai-linkedin init-db
ai-linkedin load-sources
```

### Testing
```bash
python -m pytest
```

### Demo
```bash
bash demo.sh
PYTHONPATH=src python3 -m ai_linkedin_automation.ui_server
# Visit http://127.0.0.1:8000/
```

---

## Key Decisions & Constraints

### Non-negotiable Rules
1. No publishing without explicit approval
2. No paid APIs in default Hard Zero Mode
3. No LinkedIn/X scraping
4. No storage of confidential data
5. Portable across AI providers

### Architecture Principles
- SQLite as single source of truth
- YAML for configuration
- CLI-first interface
- Web UI for monitoring
- Adapters for external services

### Voice Guidelines
- Plain-spoken, practical, warm
- Non-technical when possible
- Good for executives and technical audiences
- Short posts (150-250 words) preferred

---

## Continuation Instructions for Codex

### If Starting Fresh
1. Read `AI_LINKEDIN_AUTOMATION_CODEX_BUILD_GUIDE.md` completely
2. Follow Phase 0-3 prompts from the guide
3. Focus on small, testable increments
4. Run tests after each change

### Current Continuation Points
1. **Complete CLI Commands**: Add missing commands for weekly packages and approval packets
2. **Google Apps Script**: Implement the approval webapp
3. **Weekly Package Enhancement**: Add topic recommendations and prompt packets
4. **Safety Gates**: Ensure all publishing paths are blocked without approval

### Testing Focus
- All safety-critical paths must have tests
- Cost guard must block paid APIs
- Publishing must require approval
- Token security must be maintained

### Code Quality Standards
- Type hints where helpful
- Docstrings for public functions
- Tests for all new features
- Follow existing patterns

---

## File Inventory

### Source Code Files
- `src/ai_linkedin_automation/__init__.py`
- `src/ai_linkedin_automation/cli.py` ✅
- `src/ai_linkedin_automation/config.py` ✅
- `src/ai_linkedin_automation/storage/db.py` ✅
- `src/ai_linkedin_automation/ingestion/__init__.py`
- `src/ai_linkedin_automation/ingestion/ingest.py` ✅
- `src/ai_linkedin_automation/ingestion/sources.py` ✅
- `src/ai_linkedin_automation/scoring/__init__.py`
- `src/ai_linkedin_automation/scoring/scoring.py` ✅
- `src/ai_linkedin_automation/weekly/__init__.py`
- `src/ai_linkedin_automation/weekly/weekly.py` ✅
- `src/ai_linkedin_automation/drafting.py` ✅
- `src/ai_linkedin_automation/approval.py` ✅
- `src/ai_linkedin_automation/ui_server.py` ✅

### Configuration Files
- `config/app.yaml` ✅
- `config/cost_guard.yaml` 🚧
- `config/publishing.yaml` (missing - needs creation)
- `config/sources.yaml` ✅
- `config/scoring.yaml` ✅
- `config/scoring_weights.yaml` ✅
- `config/style_rules.yaml` ✅

### Test Files
- `tests/test_approval.py` ✅
- `tests/test_config.py` ✅
- `tests/test_config_load.py` ✅
- `tests/test_db.py` ✅
- `tests/test_drafting.py` ✅
- `tests/test_ingestion.py` ✅
- `tests/test_scoring_weekly.py` ✅
- `tests/test_ui_server.py` ✅

### Documentation
- `README.md` ✅
- `AGENTS.md` ✅
- `AI_LINKEDIN_AUTOMATION_CODEX_BUILD_GUIDE.md` ✅
- `demo.sh` ✅

---

## Final Notes

This project is designed to be safe, portable, and incrementally buildable. The current implementation provides a solid foundation with working ingestion, scoring, and basic approval. The next steps focus on completing the human approval workflow and adding the missing CLI commands.

Remember: **No publishing without approval. No paid APIs by default. Keep it simple and safe.**

For any questions about the current state or next steps, refer to the detailed implementation guide and existing code patterns.
