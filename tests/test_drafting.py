import sqlite3

from ai_linkedin_automation.article_package import extract_section, reference_count
from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.drafting import (
    generate_draft_from_topic,
    generate_draft_from_weekly_package,
    save_draft,
)
from ai_linkedin_automation.storage.db import init_db


def test_generate_draft_from_weekly_package(tmp_path):
    weekly_file = tmp_path / "weekly.md"
    weekly_file.write_text(
        "## AI insight\nThis is the best finding of the week.\nIt has a short summary.\n\n## Other insight\nAnother finding.\n"
    )

    draft_content = generate_draft_from_weekly_package(str(weekly_file))
    assert "AI insight" in draft_content
    assert "This is the best finding" in draft_content


def test_save_draft_creates_record(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)

    topic_id = "topic-123"
    content = "This is a test draft."
    draft_id = save_draft(db_path, topic_id, content)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, topic_id, content, status FROM drafts WHERE id = ?", (draft_id,))
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == draft_id
    assert row[1] == topic_id
    assert row[2] == content
    assert row[3] == "pending_approval"


def test_generate_draft_from_topic_creates_article_package(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()
    config.storage.sqlite_path = db_path

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sources (id, name, type, trust_tier, url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "nist",
            "NIST AI Risk Management Framework",
            "manual",
            "primary",
            "https://www.nist.gov/itl/ai-risk-management-framework",
            "2026-05-27",
            "2026-05-27",
        ),
    )
    cursor.execute(
        """
        INSERT INTO findings (id, source_id, url, title, summary, content_hash, raw_content, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "finding-article",
            "nist",
            "https://www.nist.gov/itl/ai-risk-management-framework",
            "AI governance works best when it becomes a checklist people can use",
            "A non-technical governance topic about translating risk principles into review steps.",
            "hash",
            "raw",
            "2026-05-27",
        ),
    )
    cursor.execute(
        """
        INSERT INTO topics (id, title, summary, recommendation, political_risk, draft_readiness, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "topic-article",
            "AI governance works best when it becomes a checklist people can use",
            "A practical governance story for leaders.",
            "draft_now",
            "low",
            5,
            "2026-05-27",
            "2026-05-27",
        ),
    )
    cursor.execute(
        "INSERT INTO topic_findings (topic_id, finding_id) VALUES (?, ?)",
        ("topic-article", "finding-article"),
    )
    conn.commit()
    conn.close()

    draft = generate_draft_from_topic(config, "topic-article")

    assert "# LinkedIn Article Package" in draft
    assert "## Feed Post" in draft
    assert "## Article Body" in draft
    assert "## References" in draft
    assert "## Note On Sourcing" in draft
    assert "## Suggested First Comment" in draft
    assert "## Advanced Image Brief" in draft
    assert len(extract_section(draft, "Feed Post").split()) <= 100
    assert reference_count(draft) >= 10


def test_save_article_package_records_reference_count(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    content = """# LinkedIn Article Package

## Feed Post

Short post.

## References

- One. (2026). *A*. Publisher. https://example.com/a
- Two. (2026). *B*. Publisher. https://example.com/b
"""

    draft_id = save_draft(db_path, "topic-article", content)

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT draft_length_type, source_reference_count FROM drafts WHERE id = ?",
        (draft_id,),
    ).fetchone()
    conn.close()

    assert row == ("article_package", 2)
