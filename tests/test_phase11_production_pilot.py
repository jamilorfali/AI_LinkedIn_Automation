import csv
import json
from pathlib import Path

from ai_linkedin_automation.approval_webapp.qa import run_local_approval_qa
from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.ingestion.sources import load_sources_from_config
from ai_linkedin_automation.pilot.checklist import (
    build_pilot_checklist,
    update_pilot_checklist_item,
)
from ai_linkedin_automation.pilot.live_pilot import run_production_pilot
from ai_linkedin_automation.pilot.sheet_validation import validate_review_queue_csv
from ai_linkedin_automation.storage.db import init_db


def _config(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()
    config.storage.sqlite_path = db_path
    config.storage.review_packets_dir = str(tmp_path / "review_packets")
    config.storage.exports_dir = str(tmp_path / "exports")
    config.storage.logs_dir = str(tmp_path / "logs")
    init_db(config.storage.sqlite_path)
    load_sources_from_config(config)
    return config


def _qa_config(base_config, qa_dir: str):
    config = load_config()
    config.storage.sqlite_path = str(Path(qa_dir) / "qa.db")
    config.storage.review_packets_dir = str(Path(qa_dir) / "review_packets")
    config.storage.exports_dir = base_config.storage.exports_dir
    config.storage.logs_dir = base_config.storage.logs_dir
    return config


def test_pilot_checklist_tracks_auto_and_manual_gates(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    checklist = build_pilot_checklist(config)
    assert Path(checklist.markdown_path).exists()
    assert checklist.stage in {"setup_in_progress", "ready_for_live_source_pilot"}

    updated = update_pilot_checklist_item(
        config,
        "apps_script_deployed",
        "done",
        notes="Deployed test web app.",
    )
    by_key = {item.key: item for item in updated.items}

    assert by_key["apps_script_deployed"].status == "done"
    assert by_key["apps_script_deployed"].manual_override is True
    assert "Deployed test web app" in by_key["apps_script_deployed"].notes
    assert Path(updated.state_path).exists()


def test_validate_review_queue_csv_accepts_qa_sheet_export(tmp_path, monkeypatch):
    base_config = _config(tmp_path, monkeypatch)
    qa = run_local_approval_qa(base_config, action="approve_text_only", week="2026-W20")
    config = _qa_config(base_config, qa.qa_dir)

    report = validate_review_queue_csv(config, qa.simulated_sheet_csv)

    assert report.ok is True
    assert report.decision_rows == 1
    assert Path(report.markdown_path).exists()
    assert Path(report.json_path).exists()


def test_validate_review_queue_csv_rejects_hash_mismatch(tmp_path, monkeypatch):
    base_config = _config(tmp_path, monkeypatch)
    qa = run_local_approval_qa(base_config, action="approve_text_only", week="2026-W20")
    config = _qa_config(base_config, qa.qa_dir)
    broken_csv = tmp_path / "broken_sheet_export.csv"

    with open(qa.simulated_sheet_csv, newline="") as f:
        rows = list(csv.DictReader(f))
        fieldnames = rows[0].keys()
    rows[0]["content_hash"] = "stale-hash"
    with open(broken_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    report = validate_review_queue_csv(config, str(broken_csv))

    assert report.ok is False
    assert any(issue.field == "content_hash" and issue.severity == "fail" for issue in report.issues)


def test_run_production_pilot_dry_run_writes_report_and_checklist(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    report = run_production_pilot(config, week="2026-W20", dry_run=True)

    assert report.status in {"passed", "passed_with_warnings"}
    assert Path(report.markdown_path).exists()
    assert Path(report.json_path).exists()
    assert Path(report.output_paths["daily_scan_report"]).exists()
    assert Path(report.output_paths["friday_package_report"]).exists()
    assert Path(report.output_paths["pilot_checklist"]).exists()
    assert "findings" in report.deltas
    manifest = json.loads(Path(report.json_path).read_text())
    assert manifest["dry_run"] is True
    assert any(step["name"] == "pilot-checklist" for step in manifest["steps"])


def test_ui_html_contains_phase11_pilot_controls():
    html = Path("ui/index.html").read_text()

    assert "Production Pilot" in html
    assert "/api/pilot-checklist" in html
    assert "/api/run-production-pilot" in html
    assert "/api/validate-review-queue" in html
