PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    finished_at TEXT,
    run_type TEXT NOT NULL,
    run_mode TEXT,
    status TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    source_type TEXT,
    trust_tier TEXT NOT NULL,
    url TEXT,
    rss_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    recurring_enabled INTEGER NOT NULL DEFAULT 0,
    political_risk_default TEXT DEFAULT 'low',
    last_fetched_at TEXT,
    fetch_error TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY NOT NULL,
    source_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT,
    summary TEXT,
    published_at TEXT,
    discovered_at TEXT,
    content_hash TEXT NOT NULL,
    raw_content TEXT,
    raw_excerpt TEXT,
    score INTEGER,
    category TEXT,
    scored_at TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    week_id TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    plain_english_summary TEXT,
    hidden_gem_angle TEXT,
    executive_relevance INTEGER,
    executive_relevance_score INTEGER,
    hidden_gem_value INTEGER,
    hidden_gem_score INTEGER,
    technical_signal INTEGER,
    technical_signal_score INTEGER,
    source_credibility INTEGER,
    source_credibility_score INTEGER,
    oracle_safe_fit INTEGER,
    oracle_safe_fit_score INTEGER,
    draft_readiness INTEGER,
    draft_readiness_score INTEGER,
    weighted_score REAL,
    political_risk TEXT,
    recommendation TEXT,
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_findings (
    topic_id TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    relationship TEXT NOT NULL DEFAULT 'supports',
    PRIMARY KEY (topic_id, finding_id),
    FOREIGN KEY (topic_id) REFERENCES topics(id),
    FOREIGN KEY (finding_id) REFERENCES findings(id)
);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    support_level TEXT NOT NULL,
    claim_type TEXT,
    support_status TEXT NOT NULL DEFAULT 'unchecked',
    primary_source_id TEXT,
    source_id TEXT,
    verification_notes TEXT,
    notes TEXT,
    created_at TEXT,
    FOREIGN KEY (topic_id) REFERENCES topics(id),
    FOREIGN KEY (source_id) REFERENCES sources(id),
    FOREIGN KEY (primary_source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    draft_text TEXT,
    draft_length_type TEXT NOT NULL DEFAULT 'short',
    source_reference_count INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    UNIQUE(topic_id, version),
    FOREIGN KEY (topic_id) REFERENCES topics(id)
);

CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL,
    type TEXT NOT NULL,
    media_type TEXT,
    url TEXT,
    content TEXT,
    prompt TEXT,
    file_path TEXT,
    approval_status TEXT,
    content_hash TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (draft_id) REFERENCES drafts(id)
);

CREATE TABLE IF NOT EXISTS approval_tokens (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (draft_id) REFERENCES drafts(id)
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    token_id TEXT NOT NULL,
    draft_id TEXT,
    draft_version INTEGER,
    content_hash TEXT,
    media_asset_id TEXT,
    approval_action TEXT,
    approved_by TEXT,
    approval_channel TEXT NOT NULL DEFAULT 'local_cli',
    action TEXT NOT NULL,
    notes TEXT,
    approved_at TEXT NOT NULL,
    FOREIGN KEY (token_id) REFERENCES approval_tokens(id),
    FOREIGN KEY (draft_id) REFERENCES drafts(id),
    FOREIGN KEY (media_asset_id) REFERENCES media_assets(id)
);

CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    post_url TEXT,
    linkedin_post_url TEXT,
    status TEXT NOT NULL,
    posted_at TEXT NOT NULL,
    posting_mode TEXT,
    final_text TEXT,
    engagement_snapshot TEXT,
    created_at TEXT,
    FOREIGN KEY (draft_id) REFERENCES drafts(id)
);

CREATE TABLE IF NOT EXISTS cost_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    action TEXT NOT NULL,
    estimated_cost_usd REAL DEFAULT 0.0,
    allowed INTEGER NOT NULL,
    reason TEXT,
    timestamp TEXT NOT NULL,
    created_at TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

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
);

CREATE TABLE IF NOT EXISTS content_clusters (
    id TEXT PRIMARY KEY,
    week_id TEXT NOT NULL,
    label TEXT NOT NULL,
    summary TEXT,
    finding_count INTEGER NOT NULL DEFAULT 0,
    publishable_source_count INTEGER NOT NULL DEFAULT 0,
    recommended_action TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_cluster_findings (
    cluster_id TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    topic_id TEXT,
    similarity_reason TEXT,
    PRIMARY KEY (cluster_id, finding_id),
    FOREIGN KEY (cluster_id) REFERENCES content_clusters(id),
    FOREIGN KEY (finding_id) REFERENCES findings(id),
    FOREIGN KEY (topic_id) REFERENCES topics(id)
);

CREATE TABLE IF NOT EXISTS source_audit_findings (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

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
);

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
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_findings_content_hash
ON findings(content_hash);

CREATE INDEX IF NOT EXISTS idx_topic_findings_finding
ON topic_findings(finding_id);

CREATE INDEX IF NOT EXISTS idx_approval_tokens_draft
ON approval_tokens(draft_id);

CREATE INDEX IF NOT EXISTS idx_editorial_reviews_draft
ON editorial_reviews(draft_id);

CREATE INDEX IF NOT EXISTS idx_content_clusters_week
ON content_clusters(week_id);

CREATE INDEX IF NOT EXISTS idx_discovery_queue_status
ON discovery_queue(status);

CREATE INDEX IF NOT EXISTS idx_citation_matrix_topic
ON citation_matrix_rows(topic_id);
