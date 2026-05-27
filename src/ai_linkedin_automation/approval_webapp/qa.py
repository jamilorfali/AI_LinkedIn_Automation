import csv
import json
import shutil
import sqlite3
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List

from ai_linkedin_automation.config import Config, resolve_project_path
from ai_linkedin_automation.notifications.packages import build_notification_package
from ai_linkedin_automation.publishing.manual import build_manual_posting_package
from ai_linkedin_automation.publishing.safety_gate import evaluate_live_publish_gate
from ai_linkedin_automation.review import export_review_queue_csv, import_review_queue_csv
from ai_linkedin_automation.storage.db import init_db


@dataclass
class ApprovalQAStep:
    name: str
    status: str
    details: str


@dataclass
class ApprovalQAReport:
    status: str
    generated_at: str
    qa_dir: str
    steps: List[ApprovalQAStep] = field(default_factory=list)
    approval_packet_path: str = ""
    notification_text_path: str = ""
    review_queue_csv: str = ""
    simulated_sheet_csv: str = ""
    manual_posting_package_path: str = ""
    report_path: str = ""
    json_path: str = ""


def _qa_config(config: Config, qa_dir: Path) -> Config:
    qa_config = deepcopy(config)
    qa_config.storage.sqlite_path = str(qa_dir / "qa.db")
    qa_config.storage.review_packets_dir = str(qa_dir / "review_packets")
    qa_config.storage.exports_dir = str(qa_dir / "exports")
    qa_config.storage.logs_dir = str(qa_dir / "logs")
    return qa_config


def _insert_fixture(config: Config) -> str:
    conn = sqlite3.connect(config.storage.sqlite_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sources (id, name, type, trust_tier, url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "qa-source",
            "QA Primary Source",
            "manual",
            "primary",
            "https://example.com/qa-source",
            "2026-05-14",
            "2026-05-14",
        ),
    )
    cursor.execute(
        """
        INSERT INTO findings (
            id, source_id, url, title, summary, content_hash, raw_content, score, category, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "qa-finding",
            "qa-source",
            "https://example.com/qa-source",
            "QA approval workflow source",
            "A primary source for local approval workflow QA.",
            "qa-finding-hash",
            "raw",
            18,
            "high_impact",
            "2026-05-14",
        ),
    )
    cursor.execute(
        """
        INSERT INTO topics (
            id, week_id, title, summary, draft_readiness, political_risk,
            recommendation, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "qa-topic",
            "2026-W20",
            "QA approval workflow",
            "A practical approval workflow QA topic.",
            5,
            "low",
            "draft_now",
            "2026-05-14",
            "2026-05-14",
        ),
    )
    cursor.execute("INSERT INTO topic_findings (topic_id, finding_id) VALUES (?, ?)", ("qa-topic", "qa-finding"))
    cursor.execute(
        """
        INSERT INTO drafts (id, topic_id, version, content, content_hash, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "qa-draft",
            "qa-topic",
            1,
            "A short practical QA draft about keeping approval human-led.",
            "qa-draft-hash",
            "pending_approval",
            "2026-05-14",
        ),
    )
    conn.commit()
    conn.close()
    return "qa-draft"


def _simulate_sheet_action(input_csv: str, output_csv: Path, action: str, notes: str) -> str:
    with open(input_csv, newline="") as f:
        rows = list(csv.DictReader(f))
        fieldnames = rows[0].keys()
    if not rows:
        raise RuntimeError("Review queue CSV has no rows to simulate")
    now = datetime.now().isoformat(timespec="seconds")
    rows[0]["approval_status"] = "completed"
    rows[0]["approval_action"] = action
    rows[0]["approval_notes"] = notes
    rows[0]["approved_at"] = now
    rows[0]["token_used_at"] = now
    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return str(output_csv)


def _write_report(report: ApprovalQAReport) -> ApprovalQAReport:
    report_path = Path(report.qa_dir) / "approval_qa_report.md"
    json_path = Path(report.qa_dir) / "approval_qa_report.json"
    lines = [
        "# Approval Web App Local QA Report",
        "",
        f"Generated: {report.generated_at}",
        f"Status: {report.status}",
        "",
        "## Steps",
        "",
    ]
    for step in report.steps:
        lines.append(f"- {step.name}: {step.status} - {step.details}")
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- Approval packet: {report.approval_packet_path}",
            f"- Notification text: {report.notification_text_path}",
            f"- Review queue CSV: {report.review_queue_csv}",
            f"- Simulated sheet CSV: {report.simulated_sheet_csv}",
            f"- Manual posting package: {report.manual_posting_package_path}",
            "",
            "No Google API call, email send, or LinkedIn publishing call was made.",
        ]
    )
    report.report_path = str(report_path)
    report.json_path = str(json_path)
    report_path.write_text("\n".join(lines) + "\n")
    json_path.write_text(json.dumps(asdict(report), indent=2))
    return report


def run_local_approval_qa(
    config: Config,
    action: str = "approve_text_only",
    week: str = "current",
) -> ApprovalQAReport:
    """Run an isolated local approval CSV round-trip with no Google or LinkedIn calls."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    qa_dir = resolve_project_path(config.storage.exports_dir) / "approval_qa" / timestamp
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_config = _qa_config(config, qa_dir)
    init_db(qa_config.storage.sqlite_path)

    report = ApprovalQAReport(
        status="passed",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        qa_dir=str(qa_dir),
    )
    report.steps.append(ApprovalQAStep("init-db", "passed", "Created isolated QA database"))

    draft_id = _insert_fixture(qa_config)
    report.steps.append(ApprovalQAStep("fixture", "passed", f"Created draft {draft_id}"))

    notification = build_notification_package(qa_config, draft_id, week=week)
    report.approval_packet_path = notification.approval_packet_path
    report.notification_text_path = notification.text_path
    report.review_queue_csv = notification.review_queue_path
    report.steps.append(ApprovalQAStep("notification-package", "passed", "Created local notification and review row"))

    exported_queue = export_review_queue_csv(qa_config, week=week)
    simulated_csv = qa_dir / "simulated_sheet_export.csv"
    report.simulated_sheet_csv = _simulate_sheet_action(
        exported_queue,
        simulated_csv,
        action,
        "Local QA approval round trip.",
    )
    report.steps.append(ApprovalQAStep("simulate-sheet", "passed", f"Simulated Apps Script action {action}"))

    import_result = import_review_queue_csv(qa_config, report.simulated_sheet_csv)
    if not import_result.ok or import_result.imported != 1:
        report.status = "failed"
        report.steps.append(
            ApprovalQAStep(
                "import-review-queue",
                "failed",
                f"{import_result.imported} imported, errors: {import_result.errors}",
            )
        )
        return _write_report(report)
    report.steps.append(ApprovalQAStep("import-review-queue", "passed", "Imported one approval action"))

    manual_package = build_manual_posting_package(qa_config, draft_id)
    report.manual_posting_package_path = manual_package
    report.steps.append(ApprovalQAStep("manual-package", "passed", "Manual posting package created"))

    live_decision = evaluate_live_publish_gate(qa_config, draft_id)
    if live_decision.allowed:
        report.status = "failed"
        report.steps.append(ApprovalQAStep("live-publish-gate", "failed", "Live publishing unexpectedly allowed"))
    else:
        report.steps.append(ApprovalQAStep("live-publish-gate", "passed", live_decision.reason))

    shutil.copy2(report.simulated_sheet_csv, qa_dir / "copy_of_sheet_export_for_import.csv")
    return _write_report(report)
