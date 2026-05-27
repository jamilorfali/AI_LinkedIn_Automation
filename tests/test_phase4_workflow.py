import csv
import sqlite3
from pathlib import Path

from ai_linkedin_automation.approval import generate_approval_token, hash_token, record_approval, store_approval_token
from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.publishing.archive import archive_manual_post
from ai_linkedin_automation.publishing.manual import build_manual_posting_package
from ai_linkedin_automation.review import (
    create_approval_packet,
    export_review_queue_csv,
    import_review_queue_csv,
)
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


def _insert_reviewable_draft(config, draft_id="draft-phase4", topic_id="topic-phase4"):
    conn = sqlite3.connect(config.storage.sqlite_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sources (id, name, type, trust_tier, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("source-phase4", "Phase 4 Source", "manual", "primary", "2026-05-14", "2026-05-14"),
    )
    cursor.execute(
        """
        INSERT INTO findings (
            id, source_id, url, title, summary, content_hash, raw_content, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "finding-phase4",
            "source-phase4",
            "https://example.com/source",
            "Useful AI governance source",
            "summary",
            "finding-hash",
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
        (topic_id, "finding-phase4"),
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
            "Final draft content",
            "draft-hash-phase4",
            "pending_approval",
            "2026-05-14",
        ),
    )
    conn.commit()
    conn.close()


def _approve_draft(config, draft_id="draft-phase4"):
    token = generate_approval_token(draft_id)
    token_id = store_approval_token(config.storage.sqlite_path, draft_id, hash_token(token), expires_hours=1)
    record_approval(config.storage.sqlite_path, token_id, "approve_text_only", "approved")


def _rewrite_csv_row(csv_path, updates):
    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
        fieldnames = f.seek(0) or rows[0].keys()
    row = rows[0]
    row.update(updates)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_import_review_queue_csv_records_approval(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_reviewable_draft(config)
    create_approval_packet(config, "draft-phase4")
    csv_path = export_review_queue_csv(config)
    _rewrite_csv_row(
        csv_path,
        {
            "approval_status": "completed",
            "approval_action": "approve_text_only",
            "approval_notes": "approved from sheet",
            "approved_at": "2026-05-14T12:30:00",
            "token_used_at": "2026-05-14T12:30:00",
        },
    )

    result = import_review_queue_csv(config, csv_path)

    assert result.imported == 1
    assert result.skipped == 0
    assert result.errors == []

    conn = sqlite3.connect(config.storage.sqlite_path)
    approval = conn.execute(
        "SELECT action, approval_channel, notes FROM approvals WHERE draft_id = ?",
        ("draft-phase4",),
    ).fetchone()
    token_used_at = conn.execute("SELECT used_at FROM approval_tokens").fetchone()[0]
    draft_status = conn.execute("SELECT status FROM drafts WHERE id = ?", ("draft-phase4",)).fetchone()[0]
    conn.close()

    assert approval == ("approve_text_only", "google_sheets_csv", "approved from sheet")
    assert token_used_at == "2026-05-14T12:30:00"
    assert draft_status == "approved_text_only"


def test_import_review_queue_csv_rejects_hash_mismatch(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_reviewable_draft(config)
    create_approval_packet(config, "draft-phase4")
    csv_path = export_review_queue_csv(config)
    _rewrite_csv_row(
        csv_path,
        {
            "content_hash": "wrong-hash",
            "approval_action": "approve_text_only",
            "approved_at": "2026-05-14T12:30:00",
        },
    )

    result = import_review_queue_csv(config, csv_path)

    assert result.imported == 0
    assert result.skipped == 1
    assert "content_hash mismatch" in result.errors[0]


def test_import_review_queue_csv_rejects_expired_review_token(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_reviewable_draft(config)
    token = generate_approval_token("draft-phase4")
    token_id = store_approval_token(
        config.storage.sqlite_path,
        "draft-phase4",
        hash_token(token),
        expires_hours=-1,
    )
    csv_path = export_review_queue_csv(config)
    _rewrite_csv_row(
        csv_path,
        {
            "review_id": token_id,
            "approval_action": "approve_text_only",
            "approved_at": "2026-05-14T12:30:00",
        },
    )

    result = import_review_queue_csv(config, csv_path)

    assert result.imported == 0
    assert result.skipped == 1
    assert "review_id expired" in result.errors[0]


def test_import_review_queue_csv_rejects_used_review_token(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_reviewable_draft(config)
    token = generate_approval_token("draft-phase4")
    token_id = store_approval_token(
        config.storage.sqlite_path,
        "draft-phase4",
        hash_token(token),
        expires_hours=1,
    )
    conn = sqlite3.connect(config.storage.sqlite_path)
    conn.execute(
        "UPDATE approval_tokens SET used_at = ? WHERE id = ?",
        ("2026-05-14T12:00:00", token_id),
    )
    conn.commit()
    conn.close()
    csv_path = export_review_queue_csv(config)
    _rewrite_csv_row(
        csv_path,
        {
            "review_id": token_id,
            "approval_action": "approve_text_only",
            "approved_at": "2026-05-14T12:30:00",
        },
    )

    result = import_review_queue_csv(config, csv_path)

    assert result.imported == 0
    assert result.skipped == 1
    assert "review_id already used" in result.errors[0]


def test_manual_posting_package_includes_sources_and_archive_command(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_reviewable_draft(config)
    _approve_draft(config)

    package_path = build_manual_posting_package(config, "draft-phase4")
    package = Path(package_path).read_text()

    assert "Final draft content" in package
    assert "Useful AI governance source" in package
    assert "ai-linkedin archive-post --draft-id draft-phase4" in package


def test_manual_posting_package_includes_article_assets(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    article_content = """# LinkedIn Article Package

## Feed Post

Most AI strategies fail at the handoff.

Full article: [PASTE ARTICLE LINK]

## Article Title

**The AI Checklist Leaders Are Missing**

## Article Body

**The opinions expressed here are my own.**

This is a long-form article body.

## References

- National Institute of Standards and Technology. (2023). *Artificial Intelligence Risk Management Framework*. NIST. https://www.nist.gov/itl/ai-risk-management-framework
- OECD. (2024). *OECD AI Principles*. OECD. https://oecd.ai/en/ai-principles

## Note On Sourcing

Primary source plus supporting governance sources.

## Suggested First Comment

Source note: start with the NIST framework.

## Advanced Image Brief

Create a cinematic LinkedIn thumbnail with a visible approval gate. No logos, no watermark.

## Image Alt Text

Original editorial illustration of AI workflow controls.
"""
    _insert_reviewable_draft(config, draft_id="draft-article", topic_id="topic-article")
    conn = sqlite3.connect(config.storage.sqlite_path)
    conn.execute(
        """
        UPDATE drafts
        SET content = ?, content_hash = ?, draft_length_type = ?, source_reference_count = ?
        WHERE id = ?
        """,
        (article_content, "article-hash", "article_package", 2, "draft-article"),
    )
    conn.commit()
    conn.close()
    _approve_draft(config, draft_id="draft-article")

    package_path = build_manual_posting_package(config, "draft-article")
    package = Path(package_path).read_text()

    assert "## Copy/paste feed post" in package
    assert "## Full LinkedIn article title" in package
    assert "The AI Checklist Leaders Are Missing" in package
    assert "## References [2]" in package
    assert "## Suggested first comment" in package
    assert "## Article thumbnail image prompt" in package
    assert "Create a cinematic LinkedIn thumbnail" in package


def test_archive_manual_post_records_post_row(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_reviewable_draft(config)
    _approve_draft(config)

    result = archive_manual_post(
        config,
        "draft-phase4",
        post_url="https://www.linkedin.com/feed/update/test",
        engagement_snapshot="0 reactions at archive time",
    )

    conn = sqlite3.connect(config.storage.sqlite_path)
    row = conn.execute(
        """
        SELECT id, draft_id, platform, post_url, status, posting_mode, final_text, engagement_snapshot
        FROM posts
        WHERE id = ?
        """,
        (result.post_id,),
    ).fetchone()
    conn.close()

    assert row == (
        result.post_id,
        "draft-phase4",
        "linkedin",
        "https://www.linkedin.com/feed/update/test",
        "posted",
        "manual",
        "Final draft content",
        "0 reactions at archive time",
    )
