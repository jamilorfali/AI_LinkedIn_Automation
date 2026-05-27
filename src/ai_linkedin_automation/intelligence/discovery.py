import csv
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
)
from ai_linkedin_automation.storage.db import connect_db, transaction


@dataclass
class DiscoveryItem:
    queue_id: str
    finding_id: str
    source_id: str
    title: str
    url: str
    trust_tier: str
    recommendation: str
    reason: str
    suggested_action: str


@dataclass
class DiscoveryQueueReport:
    week_id: str
    generated_at: str
    items: List[DiscoveryItem]
    markdown_path: str
    json_path: str
    csv_path: str


def _candidate_rows(config: Config, week_id: str) -> List[dict]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        rows = conn.execute(
            """
            SELECT
                findings.id AS finding_id,
                findings.source_id,
                findings.title,
                findings.url,
                sources.trust_tier,
                COALESCE(topics.recommendation, 'unscored') AS recommendation,
                COALESCE(topics.week_id, ?) AS week_id
            FROM findings
            JOIN sources ON sources.id = findings.source_id
            LEFT JOIN topic_findings ON topic_findings.finding_id = findings.id
            LEFT JOIN topics ON topics.id = topic_findings.topic_id
            WHERE
                topics.week_id = ?
                OR topics.week_id IS NULL
            ORDER BY findings.created_at DESC, findings.title
            """,
            (week_id, week_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _item_from_row(row: dict) -> DiscoveryItem | None:
    trust_tier = row.get("trust_tier") or "useful_but_verify"
    recommendation = row.get("recommendation") or "unscored"
    if trust_tier in PUBLISHABLE_TIERS and recommendation == "draft_now":
        return None

    if trust_tier not in PUBLISHABLE_TIERS:
        reason = f"Source tier is {trust_tier}; not enough for publishable factual claims."
        suggested_action = "Find a primary or high-trust corroborating source before drafting."
    elif recommendation in {"save_for_verification", "watch", "unscored"}:
        reason = f"Recommendation is {recommendation}; needs more review before public use."
        suggested_action = "Review source context, rescore if needed, or save for a future week."
    else:
        reason = f"Recommendation is {recommendation}; do not move directly to approval."
        suggested_action = "Leave out of the weekly winner unless a human overrides after review."

    return DiscoveryItem(
        queue_id=stable_id("discovery", row["finding_id"], reason),
        finding_id=row["finding_id"],
        source_id=row["source_id"],
        title=row["title"],
        url=row.get("url") or "",
        trust_tier=trust_tier,
        recommendation=recommendation,
        reason=reason,
        suggested_action=suggested_action,
    )


def _persist(config: Config, items: List[DiscoveryItem]) -> None:
    with transaction(config.storage.sqlite_path) as conn:
        for item in items:
            conn.execute(
                """
                INSERT INTO discovery_queue (
                    id, finding_id, source_id, title, url, reason,
                    suggested_action, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    url = excluded.url,
                    reason = excluded.reason,
                    suggested_action = excluded.suggested_action
                """,
                (
                    item.queue_id,
                    item.finding_id,
                    item.source_id,
                    item.title,
                    item.url,
                    item.reason,
                    item.suggested_action,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )


def _render_markdown(report: DiscoveryQueueReport) -> str:
    lines = [
        "# Discovery Queue",
        "",
        f"Week: {report.week_id}",
        f"Generated: {report.generated_at}",
        f"Items: {len(report.items)}",
        "",
    ]
    if not report.items:
        lines.append("No discovery queue items found.")
    for item in report.items:
        lines.extend(
            [
                f"## {item.title}",
                "",
                f"- Source ID: {item.source_id}",
                f"- Trust tier: {item.trust_tier}",
                f"- Recommendation: {item.recommendation}",
                f"- URL: {item.url}",
                f"- Reason: {item.reason}",
                f"- Suggested action: {item.suggested_action}",
                "",
            ]
        )
    return "\n".join(lines)


def build_discovery_queue(config: Config, week: str = "current") -> DiscoveryQueueReport:
    week_id = target_week(week)
    items = [item for row in _candidate_rows(config, week_id) if (item := _item_from_row(row))]
    _persist(config, items)

    output_dir = intelligence_dir(config, week_id)
    markdown_path = output_dir / "discovery_queue.md"
    json_path = output_dir / "discovery_queue.json"
    csv_path = output_dir / "discovery_queue.csv"
    report = DiscoveryQueueReport(
        week_id=week_id,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        items=items,
        markdown_path=str(markdown_path),
        json_path=str(json_path),
        csv_path=str(csv_path),
    )
    markdown_path.write_text(_render_markdown(report))
    json_path.write_text(json.dumps(asdict(report), indent=2))

    with open(csv_path, "w", newline="") as f:
        fieldnames = [
            "queue_id",
            "finding_id",
            "source_id",
            "title",
            "url",
            "trust_tier",
            "recommendation",
            "reason",
            "suggested_action",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            writer.writerow(asdict(item))
    return report

