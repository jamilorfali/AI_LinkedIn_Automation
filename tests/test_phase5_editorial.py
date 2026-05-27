import json
import sqlite3
from pathlib import Path

from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.editorial.learning import record_edit_learning
from ai_linkedin_automation.editorial.review import review_draft
from ai_linkedin_automation.review import create_approval_packet
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


def _insert_draft_with_source(config, trust_tier="primary", content=None, draft_id="draft-phase5"):
    content = content or (
        "A research paper evaluates agent workflows for governance and decision quality. "
        "The practical question for leaders is how teams should test these systems before using them in real work."
    )
    conn = sqlite3.connect(config.storage.sqlite_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sources (id, name, type, trust_tier, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("source-phase5", "Phase 5 Source", "manual", trust_tier, "2026-05-14", "2026-05-14"),
    )
    cursor.execute(
        """
        INSERT INTO findings (
            id, source_id, url, title, summary, content_hash, raw_content, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "finding-phase5",
            "source-phase5",
            "https://example.com/source",
            "Agent governance paper",
            "summary",
            "finding-hash-phase5",
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
            "topic-phase5",
            "AI governance operating habit",
            "A useful topic",
            "draft_now",
            "low",
            "2026-05-14",
            "2026-05-14",
        ),
    )
    cursor.execute(
        "INSERT INTO topic_findings (topic_id, finding_id) VALUES (?, ?)",
        ("topic-phase5", "finding-phase5"),
    )
    cursor.execute(
        """
        INSERT INTO drafts (id, topic_id, version, content, content_hash, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft_id,
            "topic-phase5",
            1,
            content,
            f"{draft_id}-hash",
            "pending_approval",
            "2026-05-14",
        ),
    )
    conn.commit()
    conn.close()
    return draft_id


def test_editorial_review_creates_claim_packet_and_rows(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    draft_id = _insert_draft_with_source(config)

    review = review_draft(config, draft_id)

    assert review.status == "ready_for_approval"
    assert review.unsupported_claim_count == 0
    assert Path(review.review_path).exists()
    packet = Path(review.review_path).read_text()
    assert "## Claim Review" in packet
    assert "## Voice And Style Checklist" in packet

    conn = sqlite3.connect(config.storage.sqlite_path)
    claim_count = conn.execute(
        "SELECT COUNT(*) FROM claims WHERE topic_id = ? AND claim_type = 'draft_claim'",
        ("topic-phase5",),
    ).fetchone()[0]
    review_row = conn.execute(
        "SELECT review_status, unsupported_claim_count, voice_issue_count FROM editorial_reviews WHERE draft_id = ?",
        (draft_id,),
    ).fetchone()
    conn.close()

    assert claim_count >= 1
    assert review_row == ("ready_for_approval", 0, 0)


def test_editorial_review_flags_unsupported_overstrong_claim(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    draft_id = _insert_draft_with_source(
        config,
        trust_tier="useful_but_verify",
        content="This revolutionary benchmark proves every company will replace old workflows.",
    )

    review = review_draft(config, draft_id)

    assert review.status == "needs_edits"
    assert review.unsupported_claim_count >= 1
    assert any(claim.support_status == "remove" for claim in review.claim_assessments)
    assert any(not check.passed for check in review.voice_checks)


def test_approval_packet_includes_editorial_claims_and_voice_checks(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    draft_id = _insert_draft_with_source(config)

    packet_path, raw_token = create_approval_packet(config, draft_id)
    packet = json.loads(Path(packet_path).read_text())

    assert raw_token
    assert packet["editorial_status"] == "ready_for_approval"
    assert packet["editorial_review_path"]
    assert packet["claim_notes"]
    assert packet["voice_checklist"]


def test_record_edit_learning_appends_log_entry(tmp_path):
    log_path = tmp_path / "edit_learning_log.md"

    result_path = record_edit_learning(
        "Shortened the opening and removed hype.",
        "Start with the practical observation before the technical detail.",
        log_path=str(log_path),
    )

    content = Path(result_path).read_text()
    assert "Shortened the opening" in content
    assert "Start with the practical observation" in content
