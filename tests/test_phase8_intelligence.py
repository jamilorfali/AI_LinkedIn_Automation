import json
import sqlite3
from pathlib import Path

from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.intelligence.citations import build_citation_matrix
from ai_linkedin_automation.intelligence.clustering import cluster_topics
from ai_linkedin_automation.intelligence.discovery import build_discovery_queue
from ai_linkedin_automation.intelligence.report import build_intelligence_report
from ai_linkedin_automation.intelligence.source_audit import audit_sources
from ai_linkedin_automation.review import create_approval_packet
from ai_linkedin_automation.storage.db import init_db


def _config(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()
    config.storage.sqlite_path = db_path
    config.storage.review_packets_dir = str(tmp_path / "review_packets")
    config.storage.exports_dir = str(tmp_path / "exports")
    config.storage.logs_dir = str(tmp_path / "logs")
    init_db(config.storage.sqlite_path)
    return config


def _insert_source(conn, source_id, name, trust_tier, url, source_type="rss"):
    conn.execute(
        """
        INSERT INTO sources (
            id, name, type, source_type, trust_tier, url, rss_url,
            is_active, recurring_enabled, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            name,
            source_type,
            source_type,
            trust_tier,
            url,
            url if source_type == "rss" else None,
            1,
            1,
            "2026-05-14",
            "2026-05-14",
        ),
    )


def _insert_finding(conn, finding_id, source_id, title, summary, score=18):
    conn.execute(
        """
        INSERT INTO findings (
            id, source_id, url, title, summary, content_hash, raw_content,
            score, category, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            finding_id,
            source_id,
            f"https://example.com/{finding_id}",
            title,
            summary,
            f"{finding_id}-hash",
            summary,
            score,
            "high_impact",
            "2026-05-14",
        ),
    )


def _insert_topic(conn, topic_id, finding_id, title, summary, recommendation="draft_now", trust_score=5):
    conn.execute(
        """
        INSERT INTO topics (
            id, week_id, title, summary, executive_relevance, hidden_gem_value,
            technical_signal, source_credibility, oracle_safe_fit, draft_readiness,
            weighted_score, political_risk, recommendation, status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            topic_id,
            "2026-W20",
            title,
            summary,
            5,
            4,
            4,
            trust_score,
            5,
            5 if recommendation == "draft_now" else 2,
            4.8,
            "low",
            recommendation,
            "candidate",
            "2026-05-14",
            "2026-05-14",
        ),
    )
    conn.execute(
        "INSERT INTO topic_findings (topic_id, finding_id) VALUES (?, ?)",
        (topic_id, finding_id),
    )


def _insert_phase8_fixture(config):
    conn = sqlite3.connect(config.storage.sqlite_path)
    _insert_source(
        conn,
        "nist-phase8",
        "NIST Phase 8",
        "primary",
        "https://www.nist.gov/artificial-intelligence",
        "public_web",
    )
    _insert_source(
        conn,
        "arxiv-phase8",
        "arXiv Phase 8",
        "useful_but_verify",
        "https://arxiv.org/rss/cs.AI",
        "rss",
    )
    _insert_source(
        conn,
        "unknown-phase8",
        "Unknown Phase 8",
        "high_trust",
        "https://example.org/ai",
        "public_web",
    )

    _insert_finding(
        conn,
        "finding-nist-governance",
        "nist-phase8",
        "AI governance operating model",
        "Research about AI governance, operations, evaluation, and decision quality.",
    )
    _insert_finding(
        conn,
        "finding-arxiv-governance",
        "arxiv-phase8",
        "AI governance evaluation benchmark",
        "A paper about AI governance, operations, evaluation, and decision quality.",
        score=12,
    )
    _insert_finding(
        conn,
        "finding-unknown-agent",
        "unknown-phase8",
        "Agent productivity rumor",
        "A useful signal about agent productivity claims needing verification.",
        score=9,
    )

    _insert_topic(
        conn,
        "topic-governance",
        "finding-nist-governance",
        "AI governance operating model",
        "Research about AI governance, operations, evaluation, and decision quality.",
    )
    _insert_topic(
        conn,
        "topic-governance-paper",
        "finding-arxiv-governance",
        "AI governance evaluation benchmark",
        "A paper about AI governance, operations, evaluation, and decision quality.",
        recommendation="save_for_verification",
        trust_score=2,
    )
    _insert_topic(
        conn,
        "topic-agent-rumor",
        "finding-unknown-agent",
        "Agent productivity rumor",
        "A useful signal about agent productivity claims needing verification.",
        recommendation="watch",
        trust_score=3,
    )
    conn.execute(
        """
        INSERT INTO drafts (id, topic_id, version, content, content_hash, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "draft-phase8",
            "topic-governance",
            1,
            "NIST published AI governance guidance. Leaders should test AI systems before relying on them.",
            "draft-phase8-hash",
            "pending_approval",
            "2026-05-14",
        ),
    )
    conn.execute(
        """
        INSERT INTO claims (
            id, topic_id, claim_text, support_level, claim_type,
            support_status, primary_source_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "claim-phase8",
            "topic-governance",
            "NIST published AI governance guidance.",
            "Supported by primary source.",
            "draft_claim",
            "supported",
            "nist-phase8",
            "2026-05-14",
        ),
    )
    conn.commit()
    conn.close()


def test_source_audit_persists_governance_issues(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_phase8_fixture(config)

    report = audit_sources(config, week="2026-W20")

    assert Path(report.markdown_path).exists()
    assert Path(report.json_path).exists()
    assert any(issue.issue_type == "domain_not_whitelisted" for issue in report.issues)

    conn = sqlite3.connect(config.storage.sqlite_path)
    count = conn.execute("SELECT COUNT(*) FROM source_audit_findings").fetchone()[0]
    conn.close()

    assert count == len(report.issues)


def test_cluster_topics_groups_related_governance_findings(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_phase8_fixture(config)

    report = cluster_topics(config, week="2026-W20")

    assert Path(report.markdown_path).exists()
    assert report.clusters
    assert any(len(cluster.items) >= 2 for cluster in report.clusters)
    assert any(cluster.recommended_action == "draft_candidate" for cluster in report.clusters)

    conn = sqlite3.connect(config.storage.sqlite_path)
    cluster_count = conn.execute("SELECT COUNT(*) FROM content_clusters").fetchone()[0]
    linked_count = conn.execute("SELECT COUNT(*) FROM content_cluster_findings").fetchone()[0]
    conn.close()

    assert cluster_count == len(report.clusters)
    assert linked_count >= 3


def test_cluster_topics_deduplicates_findings_linked_to_multiple_topics(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_phase8_fixture(config)
    conn = sqlite3.connect(config.storage.sqlite_path)
    _insert_topic(
        conn,
        "topic-governance-second-angle",
        "finding-nist-governance",
        "AI governance operating checklist",
        "Research about AI governance, operations, evaluation, and decision quality.",
    )
    conn.commit()
    conn.close()

    report = cluster_topics(config, week="2026-W20")

    conn = sqlite3.connect(config.storage.sqlite_path)
    duplicate_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT cluster_id, finding_id, COUNT(*) AS row_count
            FROM content_cluster_findings
            GROUP BY cluster_id, finding_id
            HAVING row_count > 1
        )
        """
    ).fetchone()[0]
    conn.close()

    assert report.clusters
    assert duplicate_count == 0


def test_discovery_queue_captures_verification_candidates(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_phase8_fixture(config)

    report = build_discovery_queue(config, week="2026-W20")

    assert Path(report.csv_path).exists()
    assert any(item.finding_id == "finding-arxiv-governance" for item in report.items)
    assert any("primary or high-trust" in item.suggested_action for item in report.items)

    conn = sqlite3.connect(config.storage.sqlite_path)
    count = conn.execute("SELECT COUNT(*) FROM discovery_queue").fetchone()[0]
    conn.close()

    assert count == len(report.items)


def test_citation_matrix_persists_publishable_support_rows(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_phase8_fixture(config)

    report = build_citation_matrix(config, draft_id="draft-phase8", week="2026-W20")

    assert Path(report.markdown_path).exists()
    assert report.publishable_support_count >= 1
    assert report.unsupported_count == 0
    assert any(row.citation_role == "primary_support" for row in report.rows)

    conn = sqlite3.connect(config.storage.sqlite_path)
    row = conn.execute(
        "SELECT support_status, citation_role FROM citation_matrix_rows WHERE draft_id = ?",
        ("draft-phase8",),
    ).fetchone()
    conn.close()

    assert row == ("supported", "primary_support")


def test_approval_packet_includes_citation_matrix_summary(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_phase8_fixture(config)

    packet_path, _ = create_approval_packet(config, "draft-phase8", week="2026-W20")
    packet = json.loads(Path(packet_path).read_text())

    assert packet["citation_matrix_path"]
    assert Path(packet["citation_matrix_path"]).exists()
    assert packet["citation_matrix_summary"]["publishable_support_count"] >= 1
    assert packet["citation_matrix_summary"]["rows"] >= 1


def test_intelligence_report_builds_all_outputs(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_phase8_fixture(config)

    report = build_intelligence_report(config, week="2026-W20", draft_id="draft-phase8")

    assert Path(report.markdown_path).exists()
    assert Path(report.json_path).exists()
    assert Path(report.source_audit_path).exists()
    assert Path(report.cluster_report_path).exists()
    assert Path(report.discovery_queue_path).exists()
    assert Path(report.citation_matrix_path).exists()
