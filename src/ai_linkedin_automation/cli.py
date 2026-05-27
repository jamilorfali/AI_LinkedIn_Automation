import argparse
import logging
from pathlib import Path
from typing import Optional

from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.storage.db import init_db


def _setup_logging(config):
    logging.basicConfig(
        level=getattr(logging, config.logging.level, logging.INFO),
        format=config.logging.format,
    )


def _print(message: str) -> None:
    print(message)


def status_command():
    config = load_config()
    _print(f"App: {config.app.name}")
    _print(f"Run Mode: {config.app.default_run_mode}")
    _print(f"Timezone: {config.app.timezone}")
    _print(f"Database: {config.storage.sqlite_path}")
    _print("Status: OK")


def preflight_command():
    from ai_linkedin_automation.operations.preflight import format_preflight_report, run_preflight
    config = load_config()
    report = run_preflight(config)
    _print(format_preflight_report(report))
    if not report.ok:
        raise RuntimeError("Preflight checks failed")


def init_db_command():
    config = load_config()
    init_db(config.storage.sqlite_path)
    _print("Database initialized successfully")


def load_sources_command():
    from ai_linkedin_automation.ingestion.sources import load_sources_from_config
    config = load_config()
    load_sources_from_config(config)
    _print("Sources loaded successfully")


def ingest_command(dry_run: bool):
    from ai_linkedin_automation.ingestion.ingest import run_ingestion
    config = load_config()
    run_ingestion(config, dry_run=dry_run)
    _print("Dry run completed" if dry_run else "Ingestion completed")


def score_command():
    from ai_linkedin_automation.scoring.scoring import score_all_findings
    config = load_config()
    scored_count = score_all_findings(config)
    _print(f"Scored {scored_count} findings")


def run_daily_scan_command(dry_run: bool):
    from ai_linkedin_automation.operations.workflows import run_daily_scan
    config = load_config()
    report = run_daily_scan(config, dry_run=dry_run)
    _print(f"Daily scan workflow: {report.status}")
    _print(f"Run report: {report.report_path}")
    _print(f"Run report JSON: {report.json_path}")


def build_weekly_package_command(week: str, dry_run: bool):
    from ai_linkedin_automation.weekly.weekly import generate_weekly_package
    config = load_config()
    result = generate_weekly_package(config, week=week, dry_run=dry_run)
    if result:
        weekly_file, prompt_file = result
        _print(f"Weekly package created: {weekly_file}")
        _print(f"Prompt packet created: {prompt_file}")


def run_friday_package_command(week: str, dry_run: bool):
    from ai_linkedin_automation.operations.workflows import run_friday_package
    config = load_config()
    report = run_friday_package(config, week=week, dry_run=dry_run)
    _print(f"Friday package workflow: {report.status}")
    for name, path in report.output_paths.items():
        _print(f"{name}: {path}")
    _print(f"Run report: {report.report_path}")
    _print(f"Run report JSON: {report.json_path}")


def editorial_review_command(draft_id: str, week: str):
    from ai_linkedin_automation.editorial.review import review_draft
    config = load_config()
    review = review_draft(config, draft_id, week=week)
    _print(f"Editorial review created: {review.review_path}")
    _print(f"Editorial status: {review.status}")
    _print(f"Claims: {len(review.claim_assessments)}")
    _print(f"Unsupported claims: {review.unsupported_claim_count}")
    _print(f"Voice/style issues: {review.voice_issue_count}")


def record_edit_learning_command(what_changed: str, pattern: str):
    from ai_linkedin_automation.editorial.learning import record_edit_learning
    path = record_edit_learning(what_changed, pattern)
    _print(f"Edit learning recorded: {path}")


def draft_command(weekly_package_path: str, topic_id: str):
    from ai_linkedin_automation.drafting import generate_draft_from_weekly_package, save_draft
    config = load_config()
    draft_content = generate_draft_from_weekly_package(weekly_package_path)
    draft_id = save_draft(config.storage.sqlite_path, topic_id, draft_content)
    _print(f"Draft generated and saved: {draft_id}")
    _print("Content preview:")
    _print(draft_content[:200] + "..." if len(draft_content) > 200 else draft_content)


def generate_approval_command(draft_id: str):
    from ai_linkedin_automation.approval import generate_approval_token, hash_token, store_approval_token
    config = load_config()
    token = generate_approval_token(draft_id)
    token_hash = hash_token(token)
    token_id = store_approval_token(
        config.storage.sqlite_path,
        draft_id,
        token_hash,
        expires_hours=config.review.token_expiration_hours,
    )
    _print(f"Approval token generated for draft {draft_id}")
    _print(f"Token: {token}")
    _print(f"Token ID: {token_id}")


def create_approval_packet_command(draft_id: str, week: str):
    from ai_linkedin_automation.review import create_approval_packet
    config = load_config()
    packet_path, raw_token = create_approval_packet(config, draft_id, week=week)
    _print(f"Approval packet created: {packet_path}")
    _print("Raw approval token, shown once:")
    _print(raw_token)


def export_review_queue_command(week: str):
    from ai_linkedin_automation.review import export_review_queue_csv
    config = load_config()
    output_file = export_review_queue_csv(config, week=week)
    _print(f"Review queue exported: {output_file}")


def import_review_queue_command(csv_path: str):
    from ai_linkedin_automation.review import import_review_queue_csv
    config = load_config()
    result = import_review_queue_csv(config, csv_path)
    _print(
        "Review queue import complete: "
        f"{result.imported} imported, {result.skipped} skipped, {len(result.errors)} errors"
    )
    for error in result.errors:
        _print(f"Error: {error}")
    if result.errors:
        raise RuntimeError("Review queue import completed with errors")


def validate_review_queue_command(csv_path: str):
    from ai_linkedin_automation.pilot.sheet_validation import (
        render_review_queue_validation,
        validate_review_queue_csv,
    )
    config = load_config()
    report = validate_review_queue_csv(config, csv_path)
    _print(render_review_queue_validation(report).rstrip())
    _print(f"Validation report: {report.markdown_path}")
    _print(f"Validation JSON: {report.json_path}")
    if not report.ok:
        raise RuntimeError("Review queue validation failed")


def approve_command(token: str, action: str, notes: Optional[str]):
    from ai_linkedin_automation.approval import approve_with_token
    config = load_config()
    draft_id, approval_id = approve_with_token(config.storage.sqlite_path, token, action, notes)
    _print(f"Approval recorded for draft {draft_id}: {approval_id}")


def build_manual_posting_package_command(draft_id: str):
    from ai_linkedin_automation.publishing.manual import build_manual_posting_package
    config = load_config()
    output_file = build_manual_posting_package(config, draft_id)
    _print(f"Manual posting package created: {output_file}")


def build_notification_package_command(draft_id: str, week: str):
    from ai_linkedin_automation.notifications.packages import build_notification_package
    config = load_config()
    package = build_notification_package(config, draft_id, week=week)
    _print(f"Notification text file created: {package.text_path}")
    _print(f"Notification HTML file created: {package.html_path}")
    _print(f"Notification metadata created: {package.metadata_path}")
    _print(f"Approval packet created: {package.approval_packet_path}")
    _print(f"Review queue CSV exported: {package.review_queue_path}")
    _print("No email was sent. Copy the text or HTML into Outlook manually.")


def build_reminder_package_command(draft_id: str, kind: str, week: str):
    from ai_linkedin_automation.notifications.packages import build_reminder_package
    config = load_config()
    package = build_reminder_package(config, draft_id, kind=kind, week=week)
    _print(f"Reminder text file created: {package.text_path}")
    _print(f"Reminder HTML file created: {package.html_path}")
    _print(f"Reminder metadata created: {package.metadata_path}")
    _print(f"Approval packet created: {package.approval_packet_path}")
    _print(f"Review queue CSV exported: {package.review_queue_path}")
    _print("No email was sent. Copy the text or HTML into Outlook manually.")


def integration_status_command():
    from ai_linkedin_automation.integrations.status import (
        collect_integration_status,
        format_integration_status,
    )
    config = load_config()
    _print(format_integration_status(collect_integration_status(config)))


def locus_status_command():
    from ai_linkedin_automation.locus_workflows import collect_locus_status, render_locus_status
    config = load_config()
    _print(render_locus_status(collect_locus_status(config)))


def locus_capability_check_command():
    from ai_linkedin_automation.locus_workflows import run_locus_capability_check

    config = load_config()
    report = run_locus_capability_check(config)
    _print(f"Locus capability check: {report.status}")
    for check in report.checks:
        _print(f"- [{check.status.upper()}] {check.name}: {check.details}")
    _print(f"Capability report: {report.markdown_path}")
    _print(f"Capability JSON: {report.json_path}")
    if report.status == "failed":
        raise RuntimeError("Locus capability check failed")


def build_locus_workbench_package_command():
    from ai_linkedin_automation.locus_workflows import build_locus_workbench_package

    config = load_config()
    package = build_locus_workbench_package(config)
    _print(f"Locus Workbench package: {package.status}")
    _print(f"Output directory: {package.output_dir}")
    _print(f"Manifest: {package.manifest_path}")
    _print(f"Readme: {package.readme_path}")
    for workflow, path in package.diagrams.items():
        _print(f"{workflow}: {path}")


def audit_sources_command(week: str):
    from ai_linkedin_automation.intelligence.source_audit import audit_sources
    config = load_config()
    init_db(config.storage.sqlite_path)
    report = audit_sources(config, week=week)
    _print(f"Source governance audit created: {report.markdown_path}")
    _print(f"Source governance audit JSON: {report.json_path}")
    _print(
        f"Issues: {len(report.issues)} "
        f"({report.fail_count} fail, {report.warn_count} warn, {report.info_count} info)"
    )


def cluster_topics_command(week: str):
    from ai_linkedin_automation.intelligence.clustering import cluster_topics
    config = load_config()
    init_db(config.storage.sqlite_path)
    report = cluster_topics(config, week=week)
    _print(f"Topic cluster report created: {report.markdown_path}")
    _print(f"Topic cluster JSON: {report.json_path}")
    _print(f"Clusters: {len(report.clusters)}")


def build_discovery_queue_command(week: str):
    from ai_linkedin_automation.intelligence.discovery import build_discovery_queue
    config = load_config()
    init_db(config.storage.sqlite_path)
    report = build_discovery_queue(config, week=week)
    _print(f"Discovery queue created: {report.markdown_path}")
    _print(f"Discovery queue JSON: {report.json_path}")
    _print(f"Discovery queue CSV: {report.csv_path}")
    _print(f"Items: {len(report.items)}")


def build_citation_matrix_command(draft_id: Optional[str], topic_id: Optional[str], week: str):
    from ai_linkedin_automation.intelligence.citations import build_citation_matrix
    if not draft_id and not topic_id:
        raise ValueError("Pass either --draft-id or --topic-id")
    config = load_config()
    init_db(config.storage.sqlite_path)
    report = build_citation_matrix(config, draft_id=draft_id, topic_id=topic_id, week=week)
    _print(f"Citation matrix created: {report.markdown_path}")
    _print(f"Citation matrix JSON: {report.json_path}")
    _print(f"Rows: {len(report.rows)}")
    _print(f"Publishable support rows: {report.publishable_support_count}")
    _print(f"Unsupported rows: {report.unsupported_count}")


def build_intelligence_report_command(week: str, draft_id: Optional[str], topic_id: Optional[str]):
    from ai_linkedin_automation.intelligence.report import build_intelligence_report
    config = load_config()
    init_db(config.storage.sqlite_path)
    report = build_intelligence_report(config, week=week, draft_id=draft_id, topic_id=topic_id)
    _print(f"Intelligence report created: {report.markdown_path}")
    _print(f"Intelligence report JSON: {report.json_path}")
    _print(f"Source audit: {report.source_audit_path}")
    _print(f"Topic clusters: {report.cluster_report_path}")
    _print(f"Discovery queue: {report.discovery_queue_path}")
    if report.citation_matrix_path:
        _print(f"Citation matrix: {report.citation_matrix_path}")


def validate_approval_webapp_command():
    from ai_linkedin_automation.approval_webapp.deployment import (
        render_validation_report,
        validate_approval_webapp_scaffold,
    )
    report = validate_approval_webapp_scaffold()
    _print(render_validation_report(report).rstrip())
    if not report.ok:
        raise RuntimeError("Approval web app validation failed")


def build_approval_deployment_package_command(week: str):
    from ai_linkedin_automation.approval_webapp.deployment import build_deployment_package
    config = load_config()
    package = build_deployment_package(config, week=week)
    _print(f"Approval deployment package created: {package.output_dir}")
    _print(f"Apps Script files: {package.script_dir}")
    _print(f"Sheet template CSV: {package.sheet_template_csv}")
    _print(f"Checklist: {package.checklist_path}")
    _print(f"Manifest: {package.manifest_path}")
    _print(f"Validation report: {package.validation_report_path}")
    _print("No Google deployment was performed.")


def run_approval_qa_command(action: str, week: str):
    from ai_linkedin_automation.approval_webapp.qa import run_local_approval_qa
    config = load_config()
    report = run_local_approval_qa(config, action=action, week=week)
    _print(f"Approval QA status: {report.status}")
    _print(f"QA directory: {report.qa_dir}")
    _print(f"Report: {report.report_path}")
    _print(f"Report JSON: {report.json_path}")
    _print(f"Manual posting package: {report.manual_posting_package_path}")
    if report.status != "passed":
        raise RuntimeError("Approval QA failed")


def build_local_schedule_package_command():
    from ai_linkedin_automation.operations.schedule import build_local_schedule_package
    config = load_config()
    package = build_local_schedule_package(config)
    _print(f"Local schedule package created: {package.output_dir}")
    _print(f"Daily scan plist: {package.daily_plist_path}")
    _print(f"Friday package plist: {package.friday_plist_path}")
    _print(f"Runbook: {package.runbook_path}")
    _print("No launchd jobs were installed or loaded.")


def readiness_report_command():
    from ai_linkedin_automation.pilot.readiness import build_readiness_report, render_readiness_report
    config = load_config()
    report = build_readiness_report(config, write_files=True)
    _print(render_readiness_report(report).rstrip())
    _print(f"Readiness report: {report.markdown_path}")
    _print(f"Readiness JSON: {report.json_path}")


def build_live_test_package_command(week: str, skip_dry_run: bool):
    from ai_linkedin_automation.pilot.live_test import build_live_test_package
    config = load_config()
    package = build_live_test_package(config, week=week, include_dry_run=not skip_dry_run)
    _print(f"Live test package status: {package.status}")
    _print(f"Output directory: {package.output_dir}")
    _print(f"Runbook: {package.runbook_path}")
    _print(f"Manifest: {package.manifest_path}")
    _print(f"Readiness report: {package.readiness_report_path}")
    _print(f"Approval QA report: {package.approval_qa_report_path}")
    if package.status != "passed":
        raise RuntimeError("Live test package has failed checks")


def pilot_checklist_command(mark: Optional[str], item_status: Optional[str], notes: str):
    from ai_linkedin_automation.pilot.checklist import (
        build_pilot_checklist,
        render_pilot_checklist,
        update_pilot_checklist_item,
    )
    config = load_config()
    if mark:
        checklist = update_pilot_checklist_item(config, mark, item_status or "done", notes=notes)
    else:
        checklist = build_pilot_checklist(config, write_files=True)
    _print(render_pilot_checklist(checklist).rstrip())
    _print(f"Pilot checklist: {checklist.markdown_path}")
    _print(f"Pilot checklist JSON: {checklist.json_path}")
    _print(f"Pilot checklist state: {checklist.state_path}")


def run_production_pilot_command(week: str, dry_run: bool, require_approval_url: bool):
    from ai_linkedin_automation.pilot.live_pilot import run_production_pilot
    config = load_config()
    report = run_production_pilot(
        config,
        week=week,
        dry_run=dry_run,
        require_approval_url=require_approval_url,
    )
    _print(f"Production pilot status: {report.status}")
    _print(f"Readiness stage: {report.readiness_stage}")
    _print(f"Checklist stage: {report.checklist_stage}")
    _print(f"Run report: {report.markdown_path}")
    _print(f"Run report JSON: {report.json_path}")
    for key, value in report.output_paths.items():
        if value:
            _print(f"{key}: {value}")
    if report.status == "failed":
        raise RuntimeError("Production pilot failed")


def build_production_test_package_command(week: str, topic_id: Optional[str]):
    from ai_linkedin_automation.pilot.production_test import build_production_test_package
    config = load_config()
    package = build_production_test_package(config, week=week, topic_id=topic_id)
    _print(f"Production test package status: {package.status}")
    _print(f"Selected topic: {package.selected_topic_title}")
    _print(f"Topic ID: {package.selected_topic_id}")
    _print(f"Draft ID: {package.draft_id}")
    _print(f"Output directory: {package.output_dir}")
    _print(f"Runbook: {package.runbook_path}")
    _print(f"Manifest: {package.manifest_path}")
    _print(f"Review queue CSV: {package.review_queue_path}")
    _print(f"Notification text: {package.notification_text_path}")
    _print(f"Approval URL configured: {package.approval_url_configured}")
    if not package.candidate_publish_ready:
        _print("Candidate publish readiness: needs human source review before public posting")


def prepare_business_console_command(week: str, skip_approval_qa: bool):
    from ai_linkedin_automation.business_console import run_touch_free_setup
    config = load_config()
    report = run_touch_free_setup(
        config,
        week=week,
        include_approval_qa=not skip_approval_qa,
    )
    _print(f"Business console setup status: {report.status}")
    _print(f"Summary: {report.summary}")
    _print(f"Report: {report.markdown_path}")
    _print(f"Report JSON: {report.json_path}")
    for key, value in report.output_paths.items():
        _print(f"{key}: {value}")
    if report.status == "needs_attention":
        raise RuntimeError("Business console setup needs attention")


def business_diagnostics_command():
    from ai_linkedin_automation.business_console import run_functional_diagnostics
    config = load_config()
    report = run_functional_diagnostics(config)
    _print(f"Functional diagnostics status: {report.status}")
    _print(f"Summary: {report.summary}")
    _print(f"Report: {report.markdown_path}")
    _print(f"Report JSON: {report.json_path}")
    if report.status == "failed":
        raise RuntimeError("Functional diagnostics failed")


def run_locus_e2e_test_command(week: str):
    from ai_linkedin_automation.business_console import run_locus_e2e_test

    config = load_config()
    report = run_locus_e2e_test(config, week=week)
    _print(f"Locus E2E status: {report.status}")
    _print(f"Summary: {report.summary}")
    _print(f"Report: {report.markdown_path}")
    _print(f"Report JSON: {report.json_path}")
    for key, value in report.output_paths.items():
        if value:
            _print(f"{key}: {value}")
    if report.status == "failed":
        raise RuntimeError("Locus E2E test failed")


def run_application_e2e_test_command(week: str, approval_action: str, archive_post_url: str):
    from ai_linkedin_automation.business_console import run_application_e2e_test

    config = load_config()
    report = run_application_e2e_test(
        config,
        week=week,
        approval_action=approval_action,
        archive_post_url=archive_post_url,
    )
    _print(f"Application E2E status: {report.status}")
    _print(f"Summary: {report.summary}")
    _print(f"Report: {report.markdown_path}")
    _print(f"Report JSON: {report.json_path}")
    for key, value in report.output_paths.items():
        if value:
            _print(f"{key}: {value}")
    if report.status == "failed":
        raise RuntimeError("Application E2E test failed")


def approval_setup_guide_command():
    from ai_linkedin_automation.business_console import build_approval_setup_guide
    config = load_config()
    guide = build_approval_setup_guide(config)
    _print(f"Approval setup status: {guide.status}")
    _print(f"Summary: {guide.summary}")
    _print(f"Guide: {guide.markdown_path}")
    _print(f"Guide JSON: {guide.json_path}")


def install_desktop_icon_command():
    from ai_linkedin_automation.business_console import install_desktop_icon
    package = install_desktop_icon()
    _print(f"Desktop icon status: {package.status}")
    _print(f"Desktop icon: {package.desktop_icon_path}")
    _print(package.instructions)


def archive_post_command(
    draft_id: str,
    post_url: Optional[str],
    final_text_file: Optional[str],
    engagement_snapshot: Optional[str],
):
    from ai_linkedin_automation.publishing.archive import archive_manual_post
    config = load_config()
    final_text = None
    if final_text_file:
        final_text = Path(final_text_file).read_text()
    result = archive_manual_post(
        config,
        draft_id,
        post_url=post_url,
        final_text=final_text,
        engagement_snapshot=engagement_snapshot,
    )
    _print(f"Archived manual LinkedIn post: {result.post_id}")


def publish_command(draft_id: str):
    from ai_linkedin_automation.publishing.manual import build_manual_posting_package
    from ai_linkedin_automation.publishing.safety_gate import evaluate_live_publish_gate
    config = load_config()
    decision = evaluate_live_publish_gate(config, draft_id)
    if decision.allowed:
        _print("Publishing would be allowed, but no live LinkedIn adapter is implemented in v0.")
        return

    _print("Publishing blocked.")
    _print(f"Reason: {decision.reason}")
    if "disabled" in decision.reason.lower():
        try:
            output_file = build_manual_posting_package(config, draft_id)
            _print(f"Assisted manual posting package available at {output_file}")
        except Exception as exc:
            _print(f"Manual posting package not created: {exc}")


def main():
    parser = argparse.ArgumentParser(description="AI LinkedIn Automation CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="Print system status")
    subparsers.add_parser("preflight", help="Run local operational readiness checks")
    subparsers.add_parser("init-db", help="Initialize the database")
    subparsers.add_parser("load-sources", help="Load sources from config into database")

    ingest_parser = subparsers.add_parser("ingest", help="Ingest findings from RSS and manual links")
    ingest_parser.add_argument("--dry-run", action="store_true", help="Show what would be ingested without saving")

    score_parser = subparsers.add_parser("score", help="Score all unscored findings")
    score_parser.add_argument("--week", default="current", help="Accepted for workflow compatibility")

    daily_parser = subparsers.add_parser("run-daily-scan", help="Run source loading, ingestion, and scoring")
    daily_parser.add_argument("--dry-run", action="store_true")

    weekly_parser = subparsers.add_parser("build-weekly-package", help="Generate weekly review packet")
    weekly_parser.add_argument("--week", default="current")
    weekly_parser.add_argument("--dry-run", action="store_true")

    friday_parser = subparsers.add_parser("run-friday-package", help="Run the local Friday package workflow")
    friday_parser.add_argument("--week", default="current")
    friday_parser.add_argument("--dry-run", action="store_true")

    editorial_parser = subparsers.add_parser("editorial-review", help="Run deterministic editorial review for a draft")
    editorial_parser.add_argument("--draft-id", required=True)
    editorial_parser.add_argument("--week", default="current")

    learning_parser = subparsers.add_parser("record-edit-learning", help="Append a note to the style edit learning log")
    learning_parser.add_argument("--what-changed", required=True)
    learning_parser.add_argument("--pattern", required=True)

    draft_parser = subparsers.add_parser("draft", help="Generate a draft from a weekly package")
    draft_parser.add_argument("weekly_package_path")
    draft_parser.add_argument("--topic-id", required=True, help="Topic ID to associate with the draft")

    approval_parser = subparsers.add_parser("generate-approval", help="Generate an approval token for a draft")
    approval_parser.add_argument("draft_id")

    packet_parser = subparsers.add_parser("create-approval-packet", help="Create a local approval packet")
    packet_parser.add_argument("--draft-id", required=True)
    packet_parser.add_argument("--week", default="current")

    queue_parser = subparsers.add_parser("export-review-queue", help="Export Google Sheets-compatible review queue CSV")
    queue_parser.add_argument("--week", default="current")

    import_queue_parser = subparsers.add_parser("import-review-queue", help="Import approval state from review queue CSV")
    import_queue_parser.add_argument("--csv", required=True, help="Path to review_queue.csv exported from Google Sheets")

    validate_queue_parser = subparsers.add_parser(
        "validate-review-queue",
        help="Validate a Google Sheet review queue CSV before import",
    )
    validate_queue_parser.add_argument("--csv", required=True, help="Path to CSV exported from Google Sheets")

    approve_parser = subparsers.add_parser("approve", help="Approve or reject a draft using an approval token")
    approve_parser.add_argument("token")
    approve_parser.add_argument(
        "action",
        choices=[
            "approve",
            "reject",
            "approve_text_only",
            "approve_text_plus_media",
            "approve_text_reject_media",
            "needs_edits",
            "pick_different_topic",
            "save_for_later",
        ],
    )
    approve_parser.add_argument("--notes", default=None)

    manual_parser = subparsers.add_parser("build-manual-posting-package", help="Create approved manual posting package")
    manual_parser.add_argument("--draft-id", required=True)

    notification_parser = subparsers.add_parser(
        "build-notification-package",
        help="Create local Outlook-copyable review notification files",
    )
    notification_parser.add_argument("--draft-id", required=True)
    notification_parser.add_argument("--week", default="current")

    reminder_parser = subparsers.add_parser(
        "build-reminder-package",
        help="Create local non-response reminder email files",
    )
    reminder_parser.add_argument("--draft-id", required=True)
    reminder_parser.add_argument("--kind", required=True, choices=["friday", "monday"])
    reminder_parser.add_argument("--week", default="current")

    subparsers.add_parser("integration-status", help="Report optional integration guardrail status")
    subparsers.add_parser("locus-status", help="Report Oracle Locus workflow engine setup status")
    subparsers.add_parser("locus-capability-check", help="Run local Oracle Locus SDK capability checks")
    subparsers.add_parser("build-locus-workbench-package", help="Export local Locus workflow manifest and diagrams")

    audit_parser = subparsers.add_parser("audit-sources", help="Run local source governance audit")
    audit_parser.add_argument("--week", default="current")

    cluster_parser = subparsers.add_parser("cluster-topics", help="Cluster local findings and topic candidates")
    cluster_parser.add_argument("--week", default="current")

    discovery_parser = subparsers.add_parser("build-discovery-queue", help="Build local verification/discovery queue")
    discovery_parser.add_argument("--week", default="current")

    citation_parser = subparsers.add_parser("build-citation-matrix", help="Build claim/source citation matrix")
    citation_parser.add_argument("--draft-id", default=None)
    citation_parser.add_argument("--topic-id", default=None)
    citation_parser.add_argument("--week", default="current")

    intelligence_parser = subparsers.add_parser(
        "build-intelligence-report",
        help="Build source audit, clusters, discovery queue, and optional citation matrix",
    )
    intelligence_parser.add_argument("--week", default="current")
    intelligence_parser.add_argument("--draft-id", default=None)
    intelligence_parser.add_argument("--topic-id", default=None)

    subparsers.add_parser("validate-approval-webapp", help="Validate Apps Script approval scaffold")

    deployment_parser = subparsers.add_parser(
        "build-approval-deployment-package",
        help="Create local Apps Script deployment package and Sheet template",
    )
    deployment_parser.add_argument("--week", default="current")

    approval_qa_parser = subparsers.add_parser(
        "run-approval-qa",
        help="Run isolated local approval CSV round-trip QA",
    )
    approval_qa_parser.add_argument("--action", default="approve_text_only")
    approval_qa_parser.add_argument("--week", default="current")

    subparsers.add_parser("v1-readiness", help="Build v1.0 live testing readiness report")

    live_test_parser = subparsers.add_parser(
        "build-live-test-package",
        help="Build consolidated local live testing runbook and artifacts",
    )
    live_test_parser.add_argument("--week", default="current")
    live_test_parser.add_argument("--skip-dry-run", action="store_true")

    checklist_parser = subparsers.add_parser(
        "pilot-checklist",
        help="Show or update the production pilot checklist",
    )
    checklist_parser.add_argument("--mark", default=None, help="Checklist item key to update")
    checklist_parser.add_argument(
        "--status",
        default=None,
        choices=["pending", "done", "blocked", "attention"],
        help="Status to write when --mark is used",
    )
    checklist_parser.add_argument("--notes", default="", help="Optional note for a manual checklist mark")

    production_parser = subparsers.add_parser(
        "run-production-pilot",
        help="Run the production-pilot control loop and report",
    )
    production_parser.add_argument("--week", default="current")
    production_parser.add_argument("--dry-run", action="store_true")
    production_parser.add_argument("--require-approval-url", action="store_true")

    production_test_parser = subparsers.add_parser(
        "build-production-test-package",
        help="Build first-post production testing artifacts from a live topic candidate",
    )
    production_test_parser.add_argument("--week", default="current")
    production_test_parser.add_argument("--topic-id", default=None)

    business_console_parser = subparsers.add_parser(
        "prepare-business-console",
        help="Create desktop launcher and safe business-user setup artifacts",
    )
    business_console_parser.add_argument("--week", default="current")
    business_console_parser.add_argument("--skip-approval-qa", action="store_true")

    subparsers.add_parser(
        "business-diagnostics",
        help="Run safe functional diagnostics across the local business console",
    )
    locus_e2e_parser = subparsers.add_parser(
        "run-locus-e2e-test",
        help="Run the local Locus workflow engine end-to-end test",
    )
    locus_e2e_parser.add_argument("--week", default="current")

    app_e2e_parser = subparsers.add_parser(
        "run-application-e2e-test",
        help="Run the touch-free local application path through local approval",
    )
    app_e2e_parser.add_argument("--week", default="current")
    app_e2e_parser.add_argument("--approval-action", default="approve_text_only")
    app_e2e_parser.add_argument("--archive-post-url", default="")

    subparsers.add_parser(
        "approval-setup-guide",
        help="Build the phone approval setup guide for the manual Google Apps Script gate",
    )
    subparsers.add_parser(
        "install-desktop-icon",
        help="Copy the AI LinkedIn Console app bundle to the Desktop",
    )

    subparsers.add_parser("build-local-schedule-package", help="Generate optional launchd schedule files")

    archive_parser = subparsers.add_parser("archive-post", help="Archive a manually posted LinkedIn post")
    archive_parser.add_argument("--draft-id", required=True)
    archive_parser.add_argument("--post-url", default=None)
    archive_parser.add_argument("--final-text-file", default=None)
    archive_parser.add_argument("--engagement-snapshot", default=None)

    publish_parser = subparsers.add_parser("publish", help="Attempt publishing through the disabled v0 adapter")
    publish_parser.add_argument("--draft-id", required=True)

    args = parser.parse_args()
    config = load_config()
    _setup_logging(config)

    try:
        if args.command == "status":
            status_command()
        elif args.command == "preflight":
            preflight_command()
        elif args.command == "init-db":
            init_db_command()
        elif args.command == "load-sources":
            load_sources_command()
        elif args.command == "ingest":
            ingest_command(args.dry_run)
        elif args.command == "score":
            score_command()
        elif args.command == "run-daily-scan":
            run_daily_scan_command(args.dry_run)
        elif args.command == "build-weekly-package":
            build_weekly_package_command(args.week, args.dry_run)
        elif args.command == "run-friday-package":
            run_friday_package_command(args.week, args.dry_run)
        elif args.command == "editorial-review":
            editorial_review_command(args.draft_id, args.week)
        elif args.command == "record-edit-learning":
            record_edit_learning_command(args.what_changed, args.pattern)
        elif args.command == "draft":
            draft_command(args.weekly_package_path, args.topic_id)
        elif args.command == "generate-approval":
            generate_approval_command(args.draft_id)
        elif args.command == "create-approval-packet":
            create_approval_packet_command(args.draft_id, args.week)
        elif args.command == "export-review-queue":
            export_review_queue_command(args.week)
        elif args.command == "import-review-queue":
            import_review_queue_command(args.csv)
        elif args.command == "validate-review-queue":
            validate_review_queue_command(args.csv)
        elif args.command == "approve":
            approve_command(args.token, args.action, args.notes)
        elif args.command == "build-manual-posting-package":
            build_manual_posting_package_command(args.draft_id)
        elif args.command == "build-notification-package":
            build_notification_package_command(args.draft_id, args.week)
        elif args.command == "build-reminder-package":
            build_reminder_package_command(args.draft_id, args.kind, args.week)
        elif args.command == "integration-status":
            integration_status_command()
        elif args.command == "locus-status":
            locus_status_command()
        elif args.command == "locus-capability-check":
            locus_capability_check_command()
        elif args.command == "build-locus-workbench-package":
            build_locus_workbench_package_command()
        elif args.command == "audit-sources":
            audit_sources_command(args.week)
        elif args.command == "cluster-topics":
            cluster_topics_command(args.week)
        elif args.command == "build-discovery-queue":
            build_discovery_queue_command(args.week)
        elif args.command == "build-citation-matrix":
            build_citation_matrix_command(args.draft_id, args.topic_id, args.week)
        elif args.command == "build-intelligence-report":
            build_intelligence_report_command(args.week, args.draft_id, args.topic_id)
        elif args.command == "validate-approval-webapp":
            validate_approval_webapp_command()
        elif args.command == "build-approval-deployment-package":
            build_approval_deployment_package_command(args.week)
        elif args.command == "run-approval-qa":
            run_approval_qa_command(args.action, args.week)
        elif args.command == "v1-readiness":
            readiness_report_command()
        elif args.command == "build-live-test-package":
            build_live_test_package_command(args.week, args.skip_dry_run)
        elif args.command == "pilot-checklist":
            pilot_checklist_command(args.mark, args.status, args.notes)
        elif args.command == "run-production-pilot":
            run_production_pilot_command(args.week, args.dry_run, args.require_approval_url)
        elif args.command == "build-production-test-package":
            build_production_test_package_command(args.week, args.topic_id)
        elif args.command == "prepare-business-console":
            prepare_business_console_command(args.week, args.skip_approval_qa)
        elif args.command == "business-diagnostics":
            business_diagnostics_command()
        elif args.command == "run-locus-e2e-test":
            run_locus_e2e_test_command(args.week)
        elif args.command == "run-application-e2e-test":
            run_application_e2e_test_command(
                args.week,
                args.approval_action,
                args.archive_post_url,
            )
        elif args.command == "approval-setup-guide":
            approval_setup_guide_command()
        elif args.command == "install-desktop-icon":
            install_desktop_icon_command()
        elif args.command == "build-local-schedule-package":
            build_local_schedule_package_command()
        elif args.command == "archive-post":
            archive_post_command(
                args.draft_id,
                args.post_url,
                args.final_text_file,
                args.engagement_snapshot,
            )
        elif args.command == "publish":
            publish_command(args.draft_id)
        else:
            parser.print_help()
    except Exception as exc:
        _print(f"Error: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
