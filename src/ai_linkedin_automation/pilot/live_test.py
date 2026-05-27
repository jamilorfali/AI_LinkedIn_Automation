import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List

from ai_linkedin_automation.approval_webapp.deployment import build_deployment_package
from ai_linkedin_automation.approval_webapp.qa import run_local_approval_qa
from ai_linkedin_automation.config import Config, resolve_project_path
from ai_linkedin_automation.intelligence.report import build_intelligence_report
from ai_linkedin_automation.operations.preflight import format_preflight_report, run_preflight
from ai_linkedin_automation.operations.workflows import run_friday_package
from ai_linkedin_automation.pilot.readiness import build_readiness_report
from ai_linkedin_automation.ingestion.sources import load_sources_from_config
from ai_linkedin_automation.storage.db import init_db


@dataclass
class PilotStep:
    name: str
    status: str
    details: str


@dataclass
class LiveTestPackage:
    status: str
    generated_at: str
    output_dir: str
    steps: List[PilotStep] = field(default_factory=list)
    readiness_report_path: str = ""
    runbook_path: str = ""
    manifest_path: str = ""
    friday_report_path: str = ""
    deployment_package_path: str = ""
    approval_qa_report_path: str = ""
    intelligence_report_path: str = ""


def _write_runbook(package: LiveTestPackage) -> str:
    runbook_path = Path(package.output_dir) / "LIVE_TEST_RUNBOOK.md"
    runbook_path.write_text(
        f"""# Live Testing Runbook

Generated: {package.generated_at}
Status: {package.status}

## What Live Testing Means Here

Live testing uses real public RSS/manual sources, a real Google Sheet/App Script approval page, and manual LinkedIn posting. It does not use paid AI APIs, Microsoft Graph, Google Sheets API write-back, or LinkedIn API publishing.

## Required Manual Steps

1. Review `{package.readiness_report_path}`.
2. Open the deployment package at `{package.deployment_package_path}`.
3. Create or update the Google Sheet `AI LinkedIn Review Queue`.
4. Deploy the Apps Script files from the deployment package.
5. Add `GOOGLE_APPS_SCRIPT_WEBAPP_URL=...` to `.env`.
6. Run `ai-linkedin preflight`.
7. Run `ai-linkedin run-daily-scan` when you are ready to fetch live public RSS sources.
8. Run `ai-linkedin run-friday-package --week current`.
9. Generate or save a draft, then run `ai-linkedin build-notification-package --draft-id DRAFT_ID`.
10. Paste/import the generated review queue CSV into the Sheet.
11. Open the magic link on iPhone and choose an approval action.
12. Export the Sheet as CSV and run `ai-linkedin import-review-queue --csv PATH`.
13. Run `ai-linkedin build-manual-posting-package --draft-id DRAFT_ID`.
14. Post manually on personal LinkedIn only after reading the package.
15. Archive with `ai-linkedin archive-post --draft-id DRAFT_ID --post-url LINKEDIN_POST_URL`.

## Guardrails

- No action means no post.
- No generated package posts to LinkedIn.
- Live publishing remains disabled in config.
- Media remains separate and disabled by default.
"""
    )
    package.runbook_path = str(runbook_path)
    return str(runbook_path)


def build_live_test_package(config: Config, week: str = "current", include_dry_run: bool = True) -> LiveTestPackage:
    """Build a consolidated local live-testing package without deploying or publishing."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = resolve_project_path(config.storage.exports_dir) / "pilot" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    package = LiveTestPackage(
        status="passed",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        output_dir=str(output_dir),
    )

    init_db(config.storage.sqlite_path)
    package.steps.append(PilotStep("init-db", "passed", "Database initialized or migrated"))

    load_sources_from_config(config)
    package.steps.append(PilotStep("load-sources", "passed", "Configured sources loaded for pilot readiness"))

    preflight = run_preflight(config)
    preflight_path = output_dir / "preflight.md"
    preflight_path.write_text(format_preflight_report(preflight))
    package.steps.append(
        PilotStep(
            "preflight",
            "passed" if preflight.ok else "failed",
            str(preflight_path),
        )
    )
    if not preflight.ok:
        package.status = "failed"

    deployment = build_deployment_package(config, week=week)
    package.deployment_package_path = deployment.output_dir
    package.steps.append(PilotStep("approval-deployment-package", "passed", deployment.checklist_path))

    qa = run_local_approval_qa(config, action="approve_text_only", week=week)
    package.approval_qa_report_path = qa.report_path
    package.steps.append(PilotStep("approval-qa", qa.status, qa.report_path))
    if qa.status != "passed":
        package.status = "failed"

    intelligence = build_intelligence_report(config, week=week)
    package.intelligence_report_path = intelligence.markdown_path
    package.steps.append(PilotStep("intelligence-report", "passed", intelligence.markdown_path))

    if include_dry_run:
        friday = run_friday_package(config, week=week, dry_run=True)
        package.friday_report_path = friday.report_path
        package.steps.append(PilotStep("friday-dry-run", friday.status, friday.report_path))
        if friday.status != "completed":
            package.status = "failed"

    readiness = build_readiness_report(config, write_files=True)
    package.readiness_report_path = readiness.markdown_path
    package.steps.append(
        PilotStep(
            "readiness-report",
            "passed" if readiness.ok_for_live_testing else "failed",
            readiness.markdown_path,
        )
    )
    if not readiness.ok_for_live_testing:
        package.status = "failed"

    _write_runbook(package)
    manifest_path = output_dir / "live_test_manifest.json"
    package.manifest_path = str(manifest_path)
    manifest_path.write_text(json.dumps(asdict(package), indent=2))
    return package
