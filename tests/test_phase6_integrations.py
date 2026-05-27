import json
import sqlite3
from pathlib import Path

import pytest

from ai_linkedin_automation.approval import (
    generate_approval_token,
    hash_token,
    record_approval,
    store_approval_token,
)
from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.integrations.status import (
    collect_integration_status,
    format_integration_status,
)
from ai_linkedin_automation.notifications.packages import (
    build_notification_package,
    build_reminder_package,
)
from ai_linkedin_automation.providers.claude_provider import ClaudeProvider
from ai_linkedin_automation.providers.gemini_provider import GeminiProvider
from ai_linkedin_automation.providers.openai_provider import OpenAIProvider
from ai_linkedin_automation.publishing.linkedin_adapter import publish_to_linkedin
from ai_linkedin_automation.storage.db import init_db


def _config(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()
    config.storage.sqlite_path = db_path
    config.storage.review_packets_dir = str(tmp_path / "review_packets")
    config.storage.exports_dir = str(tmp_path / "exports")
    init_db(config.storage.sqlite_path)
    return config


def _insert_reviewable_draft(config, draft_id="draft-phase6", topic_id="topic-phase6"):
    conn = sqlite3.connect(config.storage.sqlite_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sources (id, name, type, trust_tier, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("source-phase6", "Phase 6 Source", "manual", "primary", "2026-05-14", "2026-05-14"),
    )
    cursor.execute(
        """
        INSERT INTO findings (
            id, source_id, url, title, summary, content_hash, raw_content, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "finding-phase6",
            "source-phase6",
            "https://example.com/phase6",
            "Practical AI workflow source",
            "summary",
            "finding-hash-phase6",
            "raw",
            "2026-05-14",
        ),
    )
    cursor.execute(
        """
        INSERT INTO topics (id, title, summary, recommendation, political_risk, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            topic_id,
            "AI notification operating habit",
            "A useful topic",
            "draft_now",
            "low",
            "2026-05-14",
            "2026-05-14",
        ),
    )
    cursor.execute(
        "INSERT INTO topic_findings (topic_id, finding_id) VALUES (?, ?)",
        (topic_id, "finding-phase6"),
    )
    cursor.execute(
        """
        INSERT INTO drafts (id, topic_id, version, content, content_hash, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft_id,
            topic_id,
            1,
            "A practical note about AI workflows and review habits.",
            f"{draft_id}-hash",
            "pending_approval",
            "2026-05-14",
        ),
    )
    conn.commit()
    conn.close()


def _approve_draft(config, draft_id="draft-phase6"):
    token = generate_approval_token(draft_id)
    token_id = store_approval_token(config.storage.sqlite_path, draft_id, hash_token(token), expires_hours=1)
    record_approval(config.storage.sqlite_path, token_id, "approve_text_only", "approved")


def test_notification_package_creates_local_outlook_files(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "https://script.example/review")
    config = _config(tmp_path, monkeypatch)
    _insert_reviewable_draft(config)

    package = build_notification_package(config, "draft-phase6", week="2026-W20")

    text = Path(package.text_path).read_text()
    html = Path(package.html_path).read_text()
    metadata = json.loads(Path(package.metadata_path).read_text())

    assert "Subject: Friday AI LinkedIn brief ready for review" in text
    assert "AI notification operating habit" in text
    assert "https://script.example/review" in text
    assert "No action means no post." in text
    assert "No automatic LinkedIn publishing will happen" in text
    assert "Friday AI LinkedIn brief ready for review" in html
    assert metadata["email_sent"] is False
    assert metadata["outlook_graph_email_enabled"] is False
    assert metadata["google_sheets_api_writeback_enabled"] is False
    assert metadata["linkedin_api_publish_enabled"] is False
    assert Path(package.approval_packet_path).exists()
    assert Path(package.review_queue_path).exists()
    assert metadata["review_queue_path"] == package.review_queue_path
    assert "Review queue CSV used by the phone approval sync" in text


def test_reminder_package_creates_non_response_follow_up(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_reviewable_draft(config)

    package = build_reminder_package(config, "draft-phase6", kind="monday", week="2026-W20")

    text = Path(package.text_path).read_text()
    metadata = json.loads(Path(package.metadata_path).read_text())

    assert "Subject: Monday follow-up: AI LinkedIn draft needs a decision" in text
    assert "No action means no post." in text
    assert metadata["package_type"] == "monday_follow_up"
    assert metadata["reminder_kind"] == "monday"
    assert metadata["email_sent"] is False


def test_notification_package_blocks_after_decision(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_reviewable_draft(config)
    _approve_draft(config)

    with pytest.raises(RuntimeError, match="already has an approval decision"):
        build_notification_package(config, "draft-phase6", week="2026-W20")


def test_integration_status_reports_disabled_future_adapters(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    report = collect_integration_status(config)
    status_text = format_integration_status(report)
    by_name = {item.name: item for item in report.items}

    assert by_name["Local notification package"].status == "available"
    assert by_name["Google Sheets API write-back"].enabled is False
    assert by_name["Google Sheets API write-back"].cost_allowed is False
    assert by_name["Microsoft Graph email sending"].enabled is False
    assert by_name["LinkedIn live API publishing"].enabled is False
    assert by_name["LinkedIn live API publishing"].cost_allowed is False
    assert by_name["OpenAI provider adapter"].enabled is False
    assert by_name["OpenAI provider adapter"].cost_allowed is False
    assert by_name["No-API prompt packet provider"].enabled is True
    assert by_name["No-API prompt packet provider"].cost_allowed is True
    assert "Run mode: hard_zero" in status_text


def test_paid_capable_model_providers_are_cost_guard_blocked():
    for provider in [OpenAIProvider(), ClaudeProvider(), GeminiProvider()]:
        with pytest.raises(RuntimeError, match="Cost Guard blocked"):
            provider.draft_post("Draft a post")


def test_linkedin_adapter_still_blocks_after_text_approval(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_reviewable_draft(config)
    _approve_draft(config)

    result = publish_to_linkedin("draft-phase6")

    assert result.allowed is False
    assert result.status == "blocked"
    assert "LinkedIn API publishing is disabled" in result.reason
