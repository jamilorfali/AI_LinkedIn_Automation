import sqlite3

from ai_linkedin_automation.approval import (
    approve_with_token,
    generate_approval_token,
    get_token_id_from_token,
    hash_token,
    mark_token_used,
    store_approval_token,
    validate_approval_token,
)
from ai_linkedin_automation.storage.db import init_db


def test_approval_token_lifecycle(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)

    # Create a dummy draft record for foreign key integrity
    draft_id = "draft-test-1"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO drafts (id, topic_id, version, content, content_hash, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (draft_id, "topic-test-1", 1, "sample content", "hash", "pending_approval", "2026-05-11T00:00:00")
    )
    conn.commit()
    conn.close()

    token = generate_approval_token(draft_id)
    assert token

    token_hash = hash_token(token)
    assert token_hash != token

    token_id = store_approval_token(db_path, draft_id, token_hash, expires_hours=1)
    assert token_id

    is_valid, returned_draft_id = validate_approval_token(db_path, token)
    assert is_valid is True
    assert returned_draft_id == draft_id

    stored_token_id = get_token_id_from_token(db_path, token)
    assert stored_token_id == token_id

    mark_token_used(db_path, token)
    is_valid_after_use, _ = validate_approval_token(db_path, token)
    assert is_valid_after_use is False


def test_expired_token_rejected(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)

    draft_id = "draft-test-expired"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO topics (id, title, summary, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("topic-expired", "Expired token topic", "summary", "2026-05-11T00:00:00", "2026-05-11T00:00:00"),
    )
    cursor.execute(
        "INSERT INTO drafts (id, topic_id, version, content, content_hash, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (draft_id, "topic-expired", 1, "sample content", "hash", "pending_approval", "2026-05-11T00:00:00")
    )
    conn.commit()
    conn.close()

    token = generate_approval_token(draft_id)
    store_approval_token(db_path, draft_id, hash_token(token), expires_hours=-1)

    is_valid, returned_draft_id = validate_approval_token(db_path, token)

    assert is_valid is False
    assert returned_draft_id is None


def test_approve_with_token_records_approval_and_consumes_token(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO topics (id, title, summary, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("topic-approve", "Approval topic", "summary", "2026-05-11T00:00:00", "2026-05-11T00:00:00"),
    )
    cursor.execute(
        "INSERT INTO drafts (id, topic_id, version, content, content_hash, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("draft-approve", "topic-approve", 1, "sample content", "hash", "pending_approval", "2026-05-11T00:00:00"),
    )
    conn.commit()
    conn.close()

    token = generate_approval_token("draft-approve")
    token_id = store_approval_token(db_path, "draft-approve", hash_token(token), expires_hours=1)

    draft_id, approval_id = approve_with_token(db_path, token, "approve_text_only", "approved")

    assert draft_id == "draft-approve"
    conn = sqlite3.connect(db_path)
    approval = conn.execute(
        "SELECT token_id, action, approval_channel FROM approvals WHERE id = ?",
        (approval_id,),
    ).fetchone()
    token_used_at = conn.execute("SELECT used_at FROM approval_tokens WHERE id = ?", (token_id,)).fetchone()[0]
    draft_status = conn.execute("SELECT status FROM drafts WHERE id = ?", ("draft-approve",)).fetchone()[0]
    conn.close()

    assert approval == (token_id, "approve_text_only", "local_cli")
    assert token_used_at
    assert draft_status == "approved_text_only"
