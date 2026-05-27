from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.ingestion.sources import load_sources_from_config
import sqlite3

def test_load_sources():
    config = load_config()
    load_sources_from_config(config)
    
    conn = sqlite3.connect(config.storage.sqlite_path)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM sources')
    count = cursor.fetchone()[0]
    assert count > 0
    conn.close()

def test_ingest_dry_run():
    from ai_linkedin_automation.ingestion.ingest import run_ingestion
    config = load_config()
    run_ingestion(config, dry_run=True)
    # Should not raise errors

def test_manual_links_ingestion():
    from ai_linkedin_automation.ingestion.ingest import ingest_manual_links
    config = load_config()
    assert isinstance(ingest_manual_links(config, dry_run=True), list)
    # Should return list, even if empty
