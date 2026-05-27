import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List

from ai_linkedin_automation.config import Config
from ai_linkedin_automation.intelligence.common import (
    PUBLISHABLE_TIERS,
    intelligence_dir,
    stable_id,
    target_week,
    tokenize,
)
from ai_linkedin_automation.storage.db import connect_db, transaction


@dataclass
class ClusterItem:
    finding_id: str
    topic_id: str
    title: str
    summary: str
    url: str
    source_name: str
    trust_tier: str
    recommendation: str
    political_risk: str
    weighted_score: float
    tokens: set[str]


@dataclass
class ContentCluster:
    cluster_id: str
    label: str
    summary: str
    recommended_action: str
    publishable_source_count: int
    items: List[ClusterItem]


@dataclass
class ClusterReport:
    week_id: str
    generated_at: str
    clusters: List[ContentCluster]
    markdown_path: str
    json_path: str


def _rows(config: Config, week_id: str) -> List[ClusterItem]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        rows = conn.execute(
            """
            SELECT
                findings.id AS finding_id,
                COALESCE(topics.id, '') AS topic_id,
                findings.title,
                COALESCE(findings.summary, '') AS summary,
                findings.url,
                sources.name AS source_name,
                sources.trust_tier,
                COALESCE(topics.recommendation, 'unscored') AS recommendation,
                COALESCE(topics.political_risk, 'unknown') AS political_risk,
                COALESCE(topics.weighted_score, findings.score, 0) AS weighted_score
            FROM findings
            JOIN sources ON sources.id = findings.source_id
            LEFT JOIN topic_findings ON topic_findings.finding_id = findings.id
            LEFT JOIN topics ON topics.id = topic_findings.topic_id
            WHERE topics.week_id = ? OR topics.week_id IS NULL
            ORDER BY weighted_score DESC, findings.title
            """,
            (week_id,),
        ).fetchall()
    finally:
        conn.close()

    items = []
    for row in rows:
        row_dict = dict(row)
        items.append(
            ClusterItem(
                finding_id=row_dict["finding_id"],
                topic_id=row_dict["topic_id"],
                title=row_dict["title"],
                summary=row_dict["summary"],
                url=row_dict["url"],
                source_name=row_dict["source_name"],
                trust_tier=row_dict["trust_tier"],
                recommendation=row_dict["recommendation"],
                political_risk=row_dict["political_risk"],
                weighted_score=float(row_dict["weighted_score"] or 0),
                tokens=tokenize(f"{row_dict['title']} {row_dict['summary']}"),
            )
        )
    return items


def _similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _cluster_label(items: List[ClusterItem]) -> str:
    top_item = max(items, key=lambda item: item.weighted_score)
    common = set(items[0].tokens)
    for item in items[1:]:
        common &= item.tokens
    meaningful = [token for token in sorted(common) if token not in {"source", "research"}]
    if meaningful:
        return " / ".join(meaningful[:4]).title()
    return top_item.title


def _cluster_action(items: List[ClusterItem]) -> str:
    publishable = any(item.trust_tier in PUBLISHABLE_TIERS for item in items)
    low_risk = all(item.political_risk in {"low", "unknown"} for item in items)
    if any(item.recommendation == "reject" or item.political_risk == "high" for item in items):
        return "avoid_public_post"
    if publishable and low_risk and any(item.recommendation == "draft_now" for item in items):
        return "draft_candidate"
    if not publishable:
        return "verify_sources"
    return "watch"


def _cluster_summary(items: List[ClusterItem]) -> str:
    tiers = sorted({item.trust_tier for item in items})
    recommendations = sorted({item.recommendation for item in items})
    return (
        f"{len(items)} related finding(s). "
        f"Trust tiers: {', '.join(tiers)}. "
        f"Recommendations: {', '.join(recommendations)}."
    )


def _cluster_items(items: List[ClusterItem]) -> List[ContentCluster]:
    clusters: List[List[ClusterItem]] = []
    cluster_tokens: List[set[str]] = []
    for item in items:
        best_index = -1
        best_score = 0.0
        for index, tokens in enumerate(cluster_tokens):
            score = _similarity(item.tokens, tokens)
            if score > best_score:
                best_index = index
                best_score = score
        if best_index >= 0 and best_score >= 0.22:
            clusters[best_index].append(item)
            cluster_tokens[best_index] |= item.tokens
        else:
            clusters.append([item])
            cluster_tokens.append(set(item.tokens))

    result = []
    for items_in_cluster in clusters:
        label = _cluster_label(items_in_cluster)
        cluster_id = stable_id(
            "cluster",
            label,
            *sorted(item.finding_id for item in items_in_cluster),
            length=18,
        )
        publishable_count = sum(1 for item in items_in_cluster if item.trust_tier in PUBLISHABLE_TIERS)
        result.append(
            ContentCluster(
                cluster_id=cluster_id,
                label=label,
                summary=_cluster_summary(items_in_cluster),
                recommended_action=_cluster_action(items_in_cluster),
                publishable_source_count=publishable_count,
                items=items_in_cluster,
            )
        )
    result.sort(
        key=lambda cluster: (
            cluster.recommended_action != "draft_candidate",
            -cluster.publishable_source_count,
            -max(item.weighted_score for item in cluster.items),
        )
    )
    return result


def _dedupe_items(items: List[ClusterItem]) -> List[ClusterItem]:
    """Keep one row per finding when a finding is linked to multiple topic candidates."""
    by_finding: dict[str, ClusterItem] = {}
    for item in items:
        current = by_finding.get(item.finding_id)
        if current is None:
            by_finding[item.finding_id] = item
            continue
        if item.weighted_score > current.weighted_score:
            by_finding[item.finding_id] = item
        elif item.weighted_score == current.weighted_score and item.topic_id and not current.topic_id:
            by_finding[item.finding_id] = item
    return list(by_finding.values())


def _persist(config: Config, week_id: str, clusters: List[ContentCluster]) -> None:
    with transaction(config.storage.sqlite_path) as conn:
        old_ids = [
            row["id"]
            for row in conn.execute("SELECT id FROM content_clusters WHERE week_id = ?", (week_id,)).fetchall()
        ]
        if old_ids:
            placeholders = ",".join("?" for _ in old_ids)
            conn.execute(
                f"DELETE FROM content_cluster_findings WHERE cluster_id IN ({placeholders})",
                old_ids,
            )
        conn.execute("DELETE FROM content_clusters WHERE week_id = ?", (week_id,))

        for cluster in clusters:
            unique_items = _dedupe_items(cluster.items)
            conn.execute(
                """
                INSERT INTO content_clusters (
                    id, week_id, label, summary, finding_count,
                    publishable_source_count, recommended_action, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cluster.cluster_id,
                    week_id,
                    cluster.label,
                    cluster.summary,
                    len(unique_items),
                    cluster.publishable_source_count,
                    cluster.recommended_action,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            seen_memberships: set[tuple[str, str]] = set()
            for item in unique_items:
                membership_key = (cluster.cluster_id, item.finding_id)
                if membership_key in seen_memberships:
                    continue
                seen_memberships.add(membership_key)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO content_cluster_findings (
                        cluster_id, finding_id, topic_id, similarity_reason
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        cluster.cluster_id,
                        item.finding_id,
                        item.topic_id or None,
                        "Token overlap on normalized title and summary.",
                    ),
                )


def _jsonable_report(report: ClusterReport) -> dict:
    payload = asdict(report)
    for cluster in payload["clusters"]:
        for item in cluster["items"]:
            item["tokens"] = sorted(item["tokens"])
    return payload


def _render_markdown(report: ClusterReport) -> str:
    lines = [
        "# Topic Cluster Report",
        "",
        f"Week: {report.week_id}",
        f"Generated: {report.generated_at}",
        f"Clusters: {len(report.clusters)}",
        "",
    ]
    if not report.clusters:
        lines.append("No findings or topics available for clustering.")
    for cluster in report.clusters:
        lines.extend(
            [
                f"## {cluster.label}",
                "",
                f"- Action: {cluster.recommended_action}",
                f"- Findings: {len(cluster.items)}",
                f"- Publishable sources: {cluster.publishable_source_count}",
                f"- Summary: {cluster.summary}",
                "",
            ]
        )
        for item in cluster.items:
            lines.append(
                f"- {item.title} — {item.source_name} ({item.trust_tier}, {item.recommendation})"
            )
        lines.append("")
    return "\n".join(lines)


def cluster_topics(config: Config, week: str = "current") -> ClusterReport:
    week_id = target_week(week)
    clusters = _cluster_items(_dedupe_items(_rows(config, week_id)))
    _persist(config, week_id, clusters)

    output_dir = intelligence_dir(config, week_id)
    markdown_path = output_dir / "topic_clusters.md"
    json_path = output_dir / "topic_clusters.json"
    report = ClusterReport(
        week_id=week_id,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        clusters=clusters,
        markdown_path=str(markdown_path),
        json_path=str(json_path),
    )
    markdown_path.write_text(_render_markdown(report))
    json_path.write_text(json.dumps(_jsonable_report(report), indent=2))
    return report
