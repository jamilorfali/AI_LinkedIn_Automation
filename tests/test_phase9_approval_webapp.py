import csv
import json
from pathlib import Path

from ai_linkedin_automation.approval_webapp.deployment import (
    build_deployment_package,
    validate_approval_webapp_scaffold,
    write_sheet_template,
)
from ai_linkedin_automation.approval_webapp.qa import run_local_approval_qa
from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.review import REVIEW_QUEUE_HEADERS


def _config(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()
    config.storage.sqlite_path = db_path
    config.storage.review_packets_dir = str(tmp_path / "review_packets")
    config.storage.exports_dir = str(tmp_path / "exports")
    config.storage.logs_dir = str(tmp_path / "logs")
    return config


def test_validate_approval_webapp_contract_passes():
    report = validate_approval_webapp_scaffold()

    assert report.ok is True
    by_name = {check.name: check for check in report.checks}
    assert by_name["Function columnIndexes_"].status == "pass"
    assert by_name["Function syncReviewQueue_"].status == "pass"
    assert by_name["Sync queue API"].status == "pass"
    assert by_name["Export decisions API"].status == "pass"
    assert by_name["Script Properties"].status == "pass"
    assert by_name["Header review_id"].status == "pass"
    assert by_name["Action approve_text_only"].status == "pass"
    assert by_name["Manifest scope"].status == "pass"
    assert by_name["Manifest web app resource"].status == "pass"
    assert by_name["No API executable manifest"].status == "pass"
    assert by_name["No publish warning"].status == "pass"


def test_validate_approval_webapp_detects_missing_script_file(tmp_path):
    script_dir = tmp_path / "approval_webapp"
    script_dir.mkdir()
    (script_dir / "Index.html").write_text("<html></html>")
    (script_dir / "appsscript.json").write_text("{}")
    (script_dir / "README.md").write_text("")

    report = validate_approval_webapp_scaffold(script_dir=script_dir)

    assert report.ok is False
    assert any(check.name == "Code.gs exists" and check.status == "fail" for check in report.checks)


def test_write_sheet_template_matches_review_queue_headers(tmp_path):
    template_path = tmp_path / "review_queue_sheet_template.csv"

    write_sheet_template(template_path)

    with open(template_path, newline="") as f:
        rows = list(csv.reader(f))

    assert rows == [REVIEW_QUEUE_HEADERS]


def test_build_deployment_package_copies_script_and_templates(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    package = build_deployment_package(config, week="2026-W20")

    assert Path(package.output_dir).exists()
    packaged_code = Path(package.script_dir, "Code.gs").read_text()
    assert "syncReviewQueue_" in packaged_code
    assert "const SYNC_TOKEN_FALLBACK = 'aili_" in packaged_code
    assert "const SYNC_TOKEN_PLACEHOLDER_VALUE = '__AI_LINKEDIN_SYNC_TOKEN__'" in packaged_code
    assert Path(package.script_dir, "Index.html").exists()
    assert Path(package.sheet_template_csv).exists()
    assert Path(package.checklist_path).exists()
    manifest = json.loads(Path(package.manifest_path).read_text())
    checklist = Path(package.checklist_path).read_text()

    assert manifest["no_google_deploy_performed"] is True
    assert manifest["no_linkedin_publish"] is True
    assert manifest["validation_ok"] is True
    assert manifest["packaged_code_contains_sync_token"] is True
    assert "Nothing has been deployed" in checklist
    assert "GOOGLE_APPS_SCRIPT_WEBAPP_URL" in checklist
    assert "Sync to Phone Approval" in checklist
    assert "Import Phone Decision" in checklist
    assert "only see API Executable" in checklist


def test_local_approval_qa_round_trip_creates_manual_package(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    report = run_local_approval_qa(config, action="approve_text_only", week="2026-W20")

    assert report.status == "passed"
    assert Path(report.report_path).exists()
    assert Path(report.json_path).exists()
    assert Path(report.approval_packet_path).exists()
    assert Path(report.review_queue_csv).exists()
    assert Path(report.simulated_sheet_csv).exists()
    assert Path(report.manual_posting_package_path).exists()
    assert any(step.name == "live-publish-gate" and step.status == "passed" for step in report.steps)
    manual_package = Path(report.manual_posting_package_path).read_text()
    assert "Copy/paste post body" in manual_package
    assert "ai-linkedin archive-post --draft-id qa-draft" in manual_package
