from ai_linkedin_automation.config import load_config

def test_config_loads_defaults():
    config = load_config()
    assert config.app.name == "ai-linkedin-automation"
    assert config.app.default_run_mode == "hard_zero"

def test_db_schema_initializes(tmp_path):
    from ai_linkedin_automation.storage.db import init_db
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    assert "runs" in tables
    assert "sources" in tables
    conn.close()
