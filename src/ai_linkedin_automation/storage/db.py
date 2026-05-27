from contextlib import contextmanager
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"


def resolve_db_path(db_path: str) -> Path:
    """Resolve configured SQLite paths relative to the project root."""
    path = Path(db_path)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def connect_db(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with foreign key enforcement enabled."""
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction(db_path: str):
    """Context manager that commits on success and rolls back on failure."""
    conn = connect_db(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _column_names(conn: sqlite3.Connection, table: str) -> set:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row["name"] for row in cursor.fetchall()}


def _apply_lightweight_migrations(conn: sqlite3.Connection) -> None:
    """Bring older local databases forward without destructive rebuilds."""
    run_columns = _column_names(conn, "runs")
    if "finished_at" not in run_columns:
        conn.execute("ALTER TABLE runs ADD COLUMN finished_at TEXT")
    if "run_mode" not in run_columns:
        conn.execute("ALTER TABLE runs ADD COLUMN run_mode TEXT")

    source_columns = _column_names(conn, "sources")
    if "source_type" not in source_columns:
        conn.execute("ALTER TABLE sources ADD COLUMN source_type TEXT")
    if "recurring_enabled" not in source_columns:
        conn.execute("ALTER TABLE sources ADD COLUMN recurring_enabled INTEGER NOT NULL DEFAULT 0")
    if "political_risk_default" not in source_columns:
        conn.execute("ALTER TABLE sources ADD COLUMN political_risk_default TEXT DEFAULT 'low'")

    approval_columns = _column_names(conn, "approvals")
    if "draft_id" not in approval_columns:
        conn.execute("ALTER TABLE approvals ADD COLUMN draft_id TEXT")
    if "draft_version" not in approval_columns:
        conn.execute("ALTER TABLE approvals ADD COLUMN draft_version INTEGER")
    if "content_hash" not in approval_columns:
        conn.execute("ALTER TABLE approvals ADD COLUMN content_hash TEXT")
    if "media_asset_id" not in approval_columns:
        conn.execute("ALTER TABLE approvals ADD COLUMN media_asset_id TEXT")
    if "approval_action" not in approval_columns:
        conn.execute("ALTER TABLE approvals ADD COLUMN approval_action TEXT")
    if "approved_by" not in approval_columns:
        conn.execute("ALTER TABLE approvals ADD COLUMN approved_by TEXT")
    if "approval_channel" not in approval_columns:
        conn.execute("ALTER TABLE approvals ADD COLUMN approval_channel TEXT NOT NULL DEFAULT 'local_cli'")

    finding_columns = _column_names(conn, "findings")
    if "author" not in finding_columns:
        conn.execute("ALTER TABLE findings ADD COLUMN author TEXT")
    if "discovered_at" not in finding_columns:
        conn.execute("ALTER TABLE findings ADD COLUMN discovered_at TEXT")
    if "raw_excerpt" not in finding_columns:
        conn.execute("ALTER TABLE findings ADD COLUMN raw_excerpt TEXT")
    if "score" not in finding_columns:
        conn.execute("ALTER TABLE findings ADD COLUMN score INTEGER")
    if "category" not in finding_columns:
        conn.execute("ALTER TABLE findings ADD COLUMN category TEXT")
    if "scored_at" not in finding_columns:
        conn.execute("ALTER TABLE findings ADD COLUMN scored_at TEXT")
    if "status" not in finding_columns:
        conn.execute("ALTER TABLE findings ADD COLUMN status TEXT NOT NULL DEFAULT 'new'")

    topic_columns = _column_names(conn, "topics")
    topic_column_defs = {
        "week_id": "TEXT",
        "plain_english_summary": "TEXT",
        "hidden_gem_angle": "TEXT",
        "executive_relevance_score": "INTEGER",
        "hidden_gem_score": "INTEGER",
        "technical_signal_score": "INTEGER",
        "source_credibility_score": "INTEGER",
        "oracle_safe_fit_score": "INTEGER",
        "draft_readiness_score": "INTEGER",
        "weighted_score": "REAL",
        "status": "TEXT NOT NULL DEFAULT 'candidate'",
    }
    for column, definition in topic_column_defs.items():
        if column not in topic_columns:
            conn.execute(f"ALTER TABLE topics ADD COLUMN {column} {definition}")

    topic_finding_columns = _column_names(conn, "topic_findings")
    if "relationship" not in topic_finding_columns:
        conn.execute("ALTER TABLE topic_findings ADD COLUMN relationship TEXT NOT NULL DEFAULT 'supports'")

    claim_columns = _column_names(conn, "claims")
    claim_column_defs = {
        "claim_type": "TEXT",
        "support_status": "TEXT NOT NULL DEFAULT 'unchecked'",
        "primary_source_id": "TEXT",
        "verification_notes": "TEXT",
        "created_at": "TEXT",
    }
    for column, definition in claim_column_defs.items():
        if column not in claim_columns:
            conn.execute(f"ALTER TABLE claims ADD COLUMN {column} {definition}")

    draft_columns = _column_names(conn, "drafts")
    draft_column_defs = {
        "draft_text": "TEXT",
        "draft_length_type": "TEXT NOT NULL DEFAULT 'short'",
        "source_reference_count": "INTEGER NOT NULL DEFAULT 0",
        "updated_at": "TEXT",
    }
    for column, definition in draft_column_defs.items():
        if column not in draft_columns:
            conn.execute(f"ALTER TABLE drafts ADD COLUMN {column} {definition}")

    media_columns = _column_names(conn, "media_assets")
    media_column_defs = {
        "media_type": "TEXT",
        "prompt": "TEXT",
        "file_path": "TEXT",
        "content_hash": "TEXT",
    }
    for column, definition in media_column_defs.items():
        if column not in media_columns:
            conn.execute(f"ALTER TABLE media_assets ADD COLUMN {column} {definition}")

    post_columns = _column_names(conn, "posts")
    post_column_defs = {
        "linkedin_post_url": "TEXT",
        "posting_mode": "TEXT",
        "final_text": "TEXT",
        "engagement_snapshot": "TEXT",
        "created_at": "TEXT",
    }
    for column, definition in post_column_defs.items():
        if column not in post_columns:
            conn.execute(f"ALTER TABLE posts ADD COLUMN {column} {definition}")

    cost_columns = _column_names(conn, "cost_audit_log")
    if "reason" not in cost_columns:
        conn.execute("ALTER TABLE cost_audit_log ADD COLUMN reason TEXT")
    if "created_at" not in cost_columns:
        conn.execute("ALTER TABLE cost_audit_log ADD COLUMN created_at TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS editorial_reviews (
            id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            review_status TEXT NOT NULL,
            claim_count INTEGER NOT NULL DEFAULT 0,
            unsupported_claim_count INTEGER NOT NULL DEFAULT 0,
            voice_issue_count INTEGER NOT NULL DEFAULT 0,
            review_path TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (draft_id) REFERENCES drafts(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS content_clusters (
            id TEXT PRIMARY KEY,
            week_id TEXT NOT NULL,
            label TEXT NOT NULL,
            summary TEXT,
            finding_count INTEGER NOT NULL DEFAULT 0,
            publishable_source_count INTEGER NOT NULL DEFAULT 0,
            recommended_action TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS content_cluster_findings (
            cluster_id TEXT NOT NULL,
            finding_id TEXT NOT NULL,
            topic_id TEXT,
            similarity_reason TEXT,
            PRIMARY KEY (cluster_id, finding_id),
            FOREIGN KEY (cluster_id) REFERENCES content_clusters(id),
            FOREIGN KEY (finding_id) REFERENCES findings(id),
            FOREIGN KEY (topic_id) REFERENCES topics(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_audit_findings (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            detail TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (source_id) REFERENCES sources(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS discovery_queue (
            id TEXT PRIMARY KEY,
            finding_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            reason TEXT NOT NULL,
            suggested_action TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (finding_id) REFERENCES findings(id),
            FOREIGN KEY (source_id) REFERENCES sources(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS citation_matrix_rows (
            id TEXT PRIMARY KEY,
            topic_id TEXT NOT NULL,
            draft_id TEXT,
            claim_id TEXT,
            source_id TEXT,
            source_name TEXT,
            trust_tier TEXT,
            url TEXT,
            citation_role TEXT NOT NULL,
            support_status TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (topic_id) REFERENCES topics(id),
            FOREIGN KEY (draft_id) REFERENCES drafts(id),
            FOREIGN KEY (claim_id) REFERENCES claims(id),
            FOREIGN KEY (source_id) REFERENCES sources(id)
        )
        """
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_approvals_draft ON approvals(draft_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_editorial_reviews_draft ON editorial_reviews(draft_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_content_clusters_week ON content_clusters(week_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_discovery_queue_status ON discovery_queue(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_citation_matrix_topic ON citation_matrix_rows(topic_id)")


def init_db(db_path: str):
    """Initialize or migrate the database with the project schema."""
    db_dir = resolve_db_path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    conn = connect_db(db_path)
    try:
        schema = SCHEMA_PATH.read_text()
        conn.executescript(schema)
        _apply_lightweight_migrations(conn)
        conn.commit()
    finally:
        conn.close()
