import sqlite3

from ai_linkedin_automation.approval import (
    generate_approval_token,
    hash_token,
    record_approval,
    store_approval_token,
)
from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.publishing.safety_gate import (
    evaluate_live_publish_gate,
    evaluate_manual_posting_gate,
)
from ai_linkedin_automation.storage.db import init_db


def _insert_draft(db_path, draft_id="draft-1", content_hash="hash-1"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO topics (id, title, summary, recommendation, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("topic-1", "AI agent governance", "A useful topic", "draft_now", "2026-05-14", "2026-05-14"),
    )
    cursor.execute(
        """
        INSERT INTO drafts (id, topic_id, version, content, content_hash, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (draft_id, "topic-1", 1, "Draft content", content_hash, "pending_approval", "2026-05-14"),
    )
    conn.commit()
    conn.close()


def _approved_draft(db_path, action="approve_text_only"):
    token = generate_approval_token("draft-1")
    token_id = store_approval_token(db_path, "draft-1", hash_token(token), expires_hours=1)
    record_approval(db_path, token_id, action, "test approval")


def test_publish_blocks_without_approval(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    _insert_draft(db_path)
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()

    decision = evaluate_manual_posting_gate(config, "draft-1")

    assert decision.allowed is False
    assert "No approval" in decision.reason


def test_manual_package_gate_allows_approved_text(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    _insert_draft(db_path)
    _approved_draft(db_path)
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()

    decision = evaluate_manual_posting_gate(config, "draft-1")

    assert decision.allowed is True


def test_publish_blocks_hash_mismatch(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    _insert_draft(db_path)
    _approved_draft(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE drafts SET content_hash = ? WHERE id = ?", ("changed", "draft-1"))
    conn.commit()
    conn.close()
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()

    decision = evaluate_manual_posting_gate(config, "draft-1")

    assert decision.allowed is False
    assert "hash" in decision.reason


def test_live_publish_blocks_when_adapter_disabled(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    _insert_draft(db_path)
    _approved_draft(db_path)
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()

    decision = evaluate_live_publish_gate(config, "draft-1")

    assert decision.allowed is False
    assert "disabled" in decision.reason


def test_media_requires_separate_approval(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    _insert_draft(db_path)
    _approved_draft(db_path, action="approve_text_only")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO media_assets (id, draft_id, type, approval_status, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("media-1", "draft-1", "image", "not_requested", "2026-05-14"),
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()

    decision = evaluate_manual_posting_gate(config, "draft-1")

    assert decision.allowed is False
    assert "Media" in decision.reason
