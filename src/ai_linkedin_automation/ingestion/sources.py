from ai_linkedin_automation.config import CONFIG_DIR, Config, load_yaml_file
from ai_linkedin_automation.storage.db import init_db, transaction

def load_sources_from_config(config: Config):
    """Load sources from config/sources.yaml into the database"""
    init_db(config.storage.sqlite_path)
    sources_file = CONFIG_DIR / "sources.yaml"
    sources_data = load_yaml_file(sources_file)

    with transaction(config.storage.sqlite_path) as conn:
        # Load recurring sources
        if 'recurring_sources' in sources_data:
            for source in sources_data['recurring_sources']:
                source_type = source.get("type") or source.get("source_type") or "public_web"
                url = source.get("url")
                rss_url = source.get("rss_url")
                if not rss_url and source_type in {"rss", "arxiv"}:
                    rss_url = url
                is_active = source.get("is_active", source.get("enabled", True))
                conn.execute(
                    """
                    INSERT INTO sources
                        (
                            id, name, type, source_type, trust_tier, url, rss_url,
                            is_active, recurring_enabled, created_at, updated_at
                        )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        type = excluded.type,
                        source_type = excluded.source_type,
                        trust_tier = excluded.trust_tier,
                        url = excluded.url,
                        rss_url = excluded.rss_url,
                        is_active = excluded.is_active,
                        recurring_enabled = excluded.recurring_enabled,
                        updated_at = datetime('now')
                    """,
                    (
                        source['id'],
                        source['name'],
                        source_type,
                        source.get("source_type", source_type),
                        source['trust_tier'],
                        url,
                        rss_url,
                        int(bool(is_active)),
                        int(bool(is_active)),
                    ),
                )

        # Load manual sources
        if 'manual_sources' in sources_data:
            for source_id, source in sources_data['manual_sources'].items():
                trust_tier = source.get("trust_tier") or source.get("default_trust_tier", "useful_but_verify")
                conn.execute(
                    """
                    INSERT INTO sources
                        (id, name, type, source_type, trust_tier, is_active, recurring_enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        type = excluded.type,
                        source_type = excluded.source_type,
                        trust_tier = excluded.trust_tier,
                        is_active = excluded.is_active,
                        recurring_enabled = excluded.recurring_enabled,
                        updated_at = datetime('now')
                    """,
                    (
                        source_id,
                        source.get('name', source_id),
                        source.get('type', 'manual'),
                        source.get('source_type', source.get('type', 'manual')),
                        trust_tier,
                        1,
                        1,
                    ),
                )
