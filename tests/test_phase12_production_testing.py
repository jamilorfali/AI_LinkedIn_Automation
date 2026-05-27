import csv
import json
from pathlib import Path

from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.locus_workflows import locus_sdk_installed
from ai_linkedin_automation.pilot.checklist import build_pilot_checklist
from ai_linkedin_automation.pilot.production_test import build_production_test_package
from ai_linkedin_automation.pilot.sheet_validation import validate_review_queue_csv
from ai_linkedin_automation.storage.db import init_db, transaction
from ai_linkedin_automation.review import REVIEW_QUEUE_HEADERS


def _config(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()
    config.storage.sqlite_path = db_path
    config.storage.review_packets_dir = str(tmp_path / "review_packets")
    config.storage.exports_dir = str(tmp_path / "exports")
    config.storage.logs_dir = str(tmp_path / "logs")
    monkeypatch.delenv("GOOGLE_APPS_SCRIPT_WEBAPP_URL", raising=False)
    init_db(config.storage.sqlite_path)
    return config


def _insert_publish_ready_finding(config):
    with transaction(config.storage.sqlite_path) as conn:
        conn.execute(
            """
            INSERT INTO sources (id, name, type, trust_tier, url, is_active, recurring_enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "primary-ai-lab",
                "Primary AI Lab",
                "manual",
                "primary",
                "https://example.com/primary-ai-lab",
                1,
                1,
                "2026-05-14",
                "2026-05-14",
            ),
        )
        conn.execute(
            """
            INSERT INTO findings (
                id, source_id, url, title, summary, published_at, content_hash, raw_content, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "finding-primary-ready",
                "primary-ai-lab",
                "https://example.com/primary-ai-lab/research",
                "AI governance strategy benchmark architecture for enterprise operations",
                "A primary research standard gives leaders a practical decision model for AI governance, operations, data, and risk management.",
                "2026-05-14",
                "finding-primary-ready-hash",
                "raw",
                "new",
                "2026-05-14",
            ),
        )


def test_build_production_test_package_creates_first_post_artifacts(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)

    package = build_production_test_package(config, week="2026-W20")

    assert package.status == "ready_for_apps_script_deployment"
    assert package.candidate_publish_ready is True
    assert package.approval_url_configured is False
    assert package.selected_topic_id.startswith("topic_")
    assert package.draft_id.startswith("draft_")
    assert Path(package.runbook_path).exists()
    assert Path(package.manifest_path).exists()
    assert Path(package.candidate_shortlist_path).exists()
    assert Path(package.draft_path).exists()
    assert Path(package.review_queue_path).exists()
    assert Path(package.notification_text_path).exists()
    assert Path(package.approval_packet_path).exists()
    manifest = json.loads(Path(package.manifest_path).read_text())
    runbook = Path(package.runbook_path).read_text()

    assert manifest["draft_id"] == package.draft_id
    assert "No LinkedIn API publishing was attempted" in runbook
    assert "Use local approval in the console" in runbook
    assert "Optional: deploy the Apps Script package" in runbook
    if locus_sdk_installed():
        assert package.orchestration["sdk_graph_used"] is True
        assert package.orchestration["sdk_graph_success"] is True
        assert package.orchestration["sdk_execution_order"] == [
            "candidate",
            "weekly_package",
            "intelligence",
            "deployment",
            "drafting",
            "approval_packet",
            "checklist",
            "shortlist",
        ]


def test_build_production_test_package_honors_explicit_topic_id(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)
    first = build_production_test_package(config, week="2026-W20")

    second = build_production_test_package(config, week="2026-W20", topic_id=first.selected_topic_id)

    assert second.selected_topic_id == first.selected_topic_id
    assert second.draft_id != first.draft_id


def test_checklist_does_not_mark_empty_csv_validation_done(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    empty_csv = tmp_path / "empty_review_queue.csv"
    with open(empty_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(REVIEW_QUEUE_HEADERS)

    validation = validate_review_queue_csv(config, str(empty_csv))
    checklist = build_pilot_checklist(config)
    by_key = {item.key: item for item in checklist.items}

    assert validation.ok is True
    assert validation.decision_rows == 0
    assert by_key["review_queue_validated"].status == "pending"


def test_checklist_marks_pending_review_queue_validation_as_attention(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)
    build_production_test_package(config, week="2026-W20")

    checklist = build_pilot_checklist(config)
    by_key = {item.key: item for item in checklist.items}

    assert by_key["real_draft_created"].status == "done"
    assert by_key["review_queue_validated"].status == "attention"


def test_ui_html_contains_phase12_production_test_controls():
    html = Path("ui/index.html").read_text()

    assert "Build Production Test Package" in html
    assert "/api/build-production-test-package" in html
