import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

from ai_linkedin_automation.config import Config
from ai_linkedin_automation.intelligence.citations import build_citation_matrix
from ai_linkedin_automation.intelligence.clustering import cluster_topics
from ai_linkedin_automation.intelligence.common import intelligence_dir, target_week
from ai_linkedin_automation.intelligence.discovery import build_discovery_queue
from ai_linkedin_automation.intelligence.source_audit import audit_sources


@dataclass
class IntelligenceReport:
    week_id: str
    generated_at: str
    source_audit_path: str
    cluster_report_path: str
    discovery_queue_path: str
    citation_matrix_path: str
    markdown_path: str
    json_path: str


def build_intelligence_report(
    config: Config,
    week: str = "current",
    draft_id: Optional[str] = None,
    topic_id: Optional[str] = None,
) -> IntelligenceReport:
    week_id = target_week(week)
    source_audit = audit_sources(config, week=week_id)
    clusters = cluster_topics(config, week=week_id)
    discovery = build_discovery_queue(config, week=week_id)
    citation = None
    if draft_id or topic_id:
        citation = build_citation_matrix(config, draft_id=draft_id, topic_id=topic_id, week=week_id)

    output_dir = intelligence_dir(config, week_id)
    markdown_path = output_dir / "intelligence_report.md"
    json_path = output_dir / "intelligence_report.json"
    report = IntelligenceReport(
        week_id=week_id,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        source_audit_path=source_audit.markdown_path,
        cluster_report_path=clusters.markdown_path,
        discovery_queue_path=discovery.markdown_path,
        citation_matrix_path=citation.markdown_path if citation else "",
        markdown_path=str(markdown_path),
        json_path=str(json_path),
    )

    lines = [
        "# Weekly Content Intelligence Report",
        "",
        f"Week: {week_id}",
        f"Generated: {report.generated_at}",
        "",
        "## Outputs",
        "",
        f"- Source governance audit: {report.source_audit_path}",
        f"- Topic clusters: {report.cluster_report_path}",
        f"- Discovery queue: {report.discovery_queue_path}",
    ]
    if report.citation_matrix_path:
        lines.append(f"- Citation matrix: {report.citation_matrix_path}")
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Source audit issues: {len(source_audit.issues)}",
            f"- Topic clusters: {len(clusters.clusters)}",
            f"- Discovery queue items: {len(discovery.items)}",
        ]
    )
    markdown_path.write_text("\n".join(lines) + "\n")
    json_path.write_text(json.dumps(asdict(report), indent=2))
    return report
