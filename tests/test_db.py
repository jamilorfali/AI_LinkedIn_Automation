from ai_linkedin_automation.storage.db import init_db
import sqlite3

def test_db_schema_initializes(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    expected_tables = [
        "schema_migrations", "runs", "sources", "findings", "topics",
        "topic_findings", "claims", "drafts", "media_assets",
        "approval_tokens", "approvals", "posts", "cost_audit_log"
    ]
    for table in expected_tables:
        assert table in tables
    conn.close()
