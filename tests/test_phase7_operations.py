import plistlib
import sqlite3
from pathlib import Path

from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.operations.preflight import format_preflight_report, run_preflight
from ai_linkedin_automation.operations.schedule import build_local_schedule_package
from ai_linkedin_automation.operations.workflows import run_daily_scan, run_friday_package
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
    return config


def _insert_ranked_topic(config):
    conn = sqlite3.connect(config.storage.sqlite_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sources (id, name, type, trust_tier, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("source-phase7", "Phase 7 Source", "manual", "primary", "2026-05-14", "2026-05-14"),
    )
    cursor.execute(
        """
        INSERT INTO findings (
            id, source_id, url, title, summary, content_hash, raw_content, score, category, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "finding-phase7",
            "source-phase7",
            "https://example.com/phase7",
            "AI operations governance research",
            "A practical source about AI operations, governance, and decision quality.",
            "finding-hash-phase7",
            "raw",
            18,
            "high_impact",
            "2026-05-14",
        ),
    )
    cursor.execute(
        """
        INSERT INTO topics (
            id, week_id, title, summary, executive_relevance, hidden_gem_value,
            technical_signal, source_credibility, oracle_safe_fit, draft_readiness,
            weighted_score, political_risk, recommendation, status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "topic-phase7",
            "2026-W20",
            "AI operations governance habit",
            "A practical source about AI operations, governance, and decision quality.",
            5,
            4,
            4,
            5,
            5,
            5,
            4.8,
            "low",
            "draft_now",
            "candidate",
            "2026-05-14",
            "2026-05-14",
        ),
    )
    cursor.execute(
        "INSERT INTO topic_findings (topic_id, finding_id) VALUES (?, ?)",
        ("topic-phase7", "finding-phase7"),
    )
    conn.commit()
    conn.close()


def test_preflight_reports_safe_operational_posture(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    report = run_preflight(config)
    text = format_preflight_report(report)

    assert report.ok is True
    assert "[PASS] Python runtime" in text
    assert "[PASS] Cost Guard" in text
    assert "[PASS] Publishing safety" in text
    assert "[PASS] Optional integrations" in text


def test_daily_scan_workflow_writes_run_report(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    calls = []

    import ai_linkedin_automation.ingestion.ingest as ingest_module
    import ai_linkedin_automation.ingestion.sources as sources_module
    import ai_linkedin_automation.scoring.scoring as scoring_module

    def fake_load_sources(config):
        calls.append("load-sources")

    def fake_run_ingestion(config, dry_run=False):
        calls.append(f"ingest:{dry_run}")
        print("Saved 2 new findings")

    def fake_score_all_findings(config):
        calls.append("score")
        return 2

    monkeypatch.setattr(sources_module, "load_sources_from_config", fake_load_sources)
    monkeypatch.setattr(ingest_module, "run_ingestion", fake_run_ingestion)
    monkeypatch.setattr(scoring_module, "score_all_findings", fake_score_all_findings)

    report = run_daily_scan(config)

    assert report.status == "completed"
    assert calls == ["load-sources", "ingest:False", "score"]
    assert Path(report.report_path).exists()
    assert Path(report.json_path).exists()
    assert any(step.name == "ingest" and "Saved 2" in step.details for step in report.steps)


def test_friday_package_workflow_generates_outputs_and_report(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_ranked_topic(config)

    report = run_friday_package(config, week="2026-W20")

    assert report.status == "completed"
    assert "weekly_brief" in report.output_paths
    assert "prompt_packet" in report.output_paths
    assert Path(report.output_paths["weekly_brief"]).exists()
    assert Path(report.output_paths["prompt_packet"]).exists()
    assert Path(report.report_path).exists()
    brief = Path(report.output_paths["weekly_brief"]).read_text()
    assert "AI operations governance habit" in brief


def test_local_schedule_package_generates_but_does_not_install(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    package = build_local_schedule_package(config)

    daily = plistlib.loads(Path(package.daily_plist_path).read_bytes())
    friday = plistlib.loads(Path(package.friday_plist_path).read_bytes())
    runbook = Path(package.runbook_path).read_text()

    assert daily["Label"] == "com.ai-linkedin.daily-scan"
    assert "run-daily-scan" in daily["ProgramArguments"]
    assert friday["Label"] == "com.ai-linkedin.friday-package"
    assert "run-friday-package" in friday["ProgramArguments"]
    assert friday["StartCalendarInterval"]["Weekday"] == 5
    assert "They have not been installed or loaded" in runbook
    assert "No LinkedIn publishing is performed" in runbook
