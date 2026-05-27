import json
import sqlite3

from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.review import REVIEW_QUEUE_HEADERS, create_approval_packet, export_review_queue_csv
from ai_linkedin_automation.storage.db import init_db


def _insert_reviewable_draft(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO topics (
            id, title, summary, draft_readiness, political_risk,
            recommendation, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "topic-review",
            "AI evaluation workflow",
            "A practical evaluation story",
            5,
            "low",
            "draft_now",
            "2026-05-14",
            "2026-05-14",
        ),
    )
    cursor.execute(
        """
        INSERT INTO drafts (id, topic_id, version, content, content_hash, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "draft-review",
            "topic-review",
            1,
            "A practical draft",
            "hash-review",
            "pending_approval",
            "2026-05-14",
        ),
    )
    conn.commit()
    conn.close()


def test_create_approval_packet_hashes_token(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    _insert_reviewable_draft(db_path)
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()
    config.storage.review_packets_dir = str(tmp_path / "review_packets")

    packet_path, raw_token = create_approval_packet(config, "draft-review")
    packet = json.loads(open(packet_path).read())

    assert raw_token
    assert packet["token_hash"] != raw_token
    assert "raw_token" not in packet
    assert packet["content_hash"] == "hash-review"


def test_export_review_queue_csv_has_sheet_headers(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    _insert_reviewable_draft(db_path)
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()
    config.storage.review_packets_dir = str(tmp_path / "review_packets")
    create_approval_packet(config, "draft-review")

    csv_path = export_review_queue_csv(config)
    header_line = open(csv_path).readline().strip().split(",")

    assert header_line == REVIEW_QUEUE_HEADERS
