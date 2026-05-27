from pathlib import Path

from ai_linkedin_automation.business_console import (
    approve_latest_draft_locally,
    business_home,
    run_application_e2e_test,
    run_locus_e2e_test,
)
from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.pilot.production_test import build_production_test_package
from ai_linkedin_automation.storage.db import connect_db, init_db, transaction


def _config(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.delenv("GOOGLE_APPS_SCRIPT_WEBAPP_URL", raising=False)
    config = load_config()
    config.storage.sqlite_path = db_path
    config.storage.review_packets_dir = str(tmp_path / "review_packets")
    config.storage.exports_dir = str(tmp_path / "exports")
    config.storage.logs_dir = str(tmp_path / "logs")
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


def test_local_approval_removes_google_csv_glue_and_builds_manual_package(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)
    package = build_production_test_package(config, week="2026-W20")

    result = approve_latest_draft_locally(config, draft_id=package.draft_id)

    assert result.status == "approved"
    assert result.action == "approve_text_only"
    assert Path(result.manual_package_path).exists()
    with connect_db(config.storage.sqlite_path) as conn:
        row = conn.execute(
            "SELECT approval_channel FROM approvals WHERE id = ?",
            (result.approval_id,),
        ).fetchone()
    assert row["approval_channel"] == "local_console"


def test_application_e2e_runs_through_local_approval_path(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)

    report = run_application_e2e_test(config, week="2026-W20")

    assert report.status == "passed_with_warnings"
    assert Path(report.markdown_path).exists()
    assert Path(report.output_paths["manual_posting_package"]).exists()
    by_key = {step.key: step for step in report.steps}
    assert by_key["production_test_package"].status == "pass"
    assert by_key["local_approval"].status == "pass"
    assert by_key["archive_post"].status == "warn"


def test_locus_e2e_runs_graphs_capabilities_and_workbench(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)

    report = run_locus_e2e_test(config, week="2026-W20")

    assert report.status == "passed"
    assert Path(report.markdown_path).exists()
    assert Path(report.output_paths["locus_workbench_manifest"]).exists()
    by_key = {step.key: step for step in report.steps}
    assert by_key["capability_check"].status == "pass"
    assert by_key["daily_scan_graph"].status == "pass"
    assert by_key["friday_package_graph"].status == "pass"
    assert by_key["production_pilot_graph"].status == "pass"


def test_business_home_defaults_to_local_approval_path_not_google_gate(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    home = business_home(config)

    assert home.next_action.key == "build_test_package"
    assert "Google" not in home.next_action.description
