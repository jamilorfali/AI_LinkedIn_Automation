import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List, Optional

from ai_linkedin_automation.config import Config
from ai_linkedin_automation.intelligence.common import (
    PUBLISHABLE_TIERS,
    intelligence_dir,
    stable_id,
    target_week,
)
from ai_linkedin_automation.storage.db import connect_db, transaction


@dataclass
class CitationMatrixRow:
    row_id: str
    topic_id: str
    draft_id: str
    claim_id: str
    claim_text: str
    source_id: str
    source_name: str
    trust_tier: str
    url: str
    citation_role: str
    support_status: str
    notes: str


@dataclass
class CitationMatrixReport:
    week_id: str
    generated_at: str
    topic_id: str
    draft_id: str
    rows: List[CitationMatrixRow]
    markdown_path: str
    json_path: str

    @property
    def unsupported_count(self) -> int:
        return sum(1 for row in self.rows if row.support_status in {"unsupported", "cannot_support_claim"})

    @property
    def publishable_support_count(self) -> int:
        return sum(1 for row in self.rows if row.citation_role == "primary_support")


def _topic_for_draft(config: Config, draft_id: Optional[str], topic_id: Optional[str]) -> tuple[str, str]:
    if topic_id:
        return topic_id, draft_id or ""
    if not draft_id:
        raise ValueError("Either draft_id or topic_id is required")
    conn = connect_db(config.storage.sqlite_path)
    try:
        row = conn.execute("SELECT topic_id FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if not row:
            raise ValueError(f"Draft not found: {draft_id}")
        return row["topic_id"], draft_id
    finally:
        conn.close()


def _claims(config: Config, topic_id: str) -> List[dict]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        rows = conn.execute(
            """
            SELECT id, claim_text, support_status, support_level, verification_notes, notes
            FROM claims
            WHERE topic_id = ?
            ORDER BY created_at DESC, id
            """,
            (topic_id,),
        ).fetchall()
        claims = [dict(row) for row in rows]
        if claims:
            return claims

        topic = conn.execute(
            "SELECT id, summary, title FROM topics WHERE id = ?",
            (topic_id,),
        ).fetchone()
        if not topic:
            raise ValueError(f"Topic not found: {topic_id}")
        return [
            {
                "id": "",
                "claim_text": topic["summary"] or topic["title"],
                "support_status": "unchecked",
                "support_level": "",
                "verification_notes": "",
                "notes": "Synthetic matrix row from topic summary; run editorial review for draft claims.",
            }
        ]
    finally:
        conn.close()


def _sources(config: Config, topic_id: str) -> List[dict]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        rows = conn.execute(
            """
            SELECT
                sources.id AS source_id,
                sources.name AS source_name,
                sources.trust_tier,
                findings.url,
                findings.title AS finding_title
            FROM topic_findings
            JOIN findings ON findings.id = topic_findings.finding_id
            JOIN sources ON sources.id = findings.source_id
            WHERE topic_findings.topic_id = ?
            ORDER BY
                CASE sources.trust_tier
                    WHEN 'primary' THEN 0
                    WHEN 'high_trust' THEN 1
                    WHEN 'useful_but_verify' THEN 2
                    WHEN 'social_signal_only' THEN 3
                    ELSE 4
                END,
                sources.name
            """,
            (topic_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _role_and_status(claim: dict, source: dict) -> tuple[str, str, str]:
    trust_tier = source.get("trust_tier") or "useful_but_verify"
    claim_status = claim.get("support_status") or "unchecked"
    if trust_tier in PUBLISHABLE_TIERS and claim_status not in {"remove", "unsupported"}:
        return "primary_support", "supported", "Source can support publishable claims with modest wording."
    if trust_tier == "useful_but_verify":
        return "context_only", "verify_required", "Useful context, but find primary/high-trust support."
    if trust_tier == "social_signal_only":
        return "discovery_signal", "cannot_support_claim", "Social signal cannot support factual claims."
    return "not_usable", "unsupported", "Source cannot support this claim."


def _build_rows(topic_id: str, draft_id: str, claims: List[dict], sources: List[dict]) -> List[CitationMatrixRow]:
    if not sources:
        return [
            CitationMatrixRow(
                row_id=stable_id("citation", topic_id, draft_id, "no-source"),
                topic_id=topic_id,
                draft_id=draft_id,
                claim_id=claims[0].get("id", "") if claims else "",
                claim_text=claims[0].get("claim_text", "") if claims else "",
                source_id="",
                source_name="",
                trust_tier="none",
                url="",
                citation_role="missing_source",
                support_status="unsupported",
                notes="No source is attached to this topic.",
            )
        ]

    rows: List[CitationMatrixRow] = []
    for claim in claims:
        for source in sources:
            role, status, notes = _role_and_status(claim, source)
            rows.append(
                CitationMatrixRow(
                    row_id=stable_id(
                        "citation",
                        topic_id,
                        draft_id,
                        claim.get("id", ""),
                        source.get("source_id", ""),
                    ),
                    topic_id=topic_id,
                    draft_id=draft_id,
                    claim_id=claim.get("id", "") or "",
                    claim_text=claim.get("claim_text", "") or "",
                    source_id=source.get("source_id", "") or "",
                    source_name=source.get("source_name", "") or "",
                    trust_tier=source.get("trust_tier", "") or "",
                    url=source.get("url", "") or "",
                    citation_role=role,
                    support_status=status,
                    notes=notes,
                )
            )
    return rows


def _persist(config: Config, topic_id: str, draft_id: str, rows: List[CitationMatrixRow]) -> None:
    with transaction(config.storage.sqlite_path) as conn:
        if draft_id:
            conn.execute(
                "DELETE FROM citation_matrix_rows WHERE topic_id = ? AND draft_id = ?",
                (topic_id, draft_id),
            )
        else:
            conn.execute(
                "DELETE FROM citation_matrix_rows WHERE topic_id = ? AND draft_id IS NULL",
                (topic_id,),
            )
        for row in rows:
            conn.execute(
                """
                INSERT INTO citation_matrix_rows (
                    id, topic_id, draft_id, claim_id, source_id, source_name,
                    trust_tier, url, citation_role, support_status, notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.row_id,
                    row.topic_id,
                    row.draft_id or None,
                    row.claim_id or None,
                    row.source_id or None,
                    row.source_name,
                    row.trust_tier,
                    row.url,
                    row.citation_role,
                    row.support_status,
                    row.notes,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )


def _render_markdown(report: CitationMatrixReport) -> str:
    lines = [
        "# Citation Validation Matrix",
        "",
        f"Week: {report.week_id}",
        f"Topic ID: {report.topic_id}",
        f"Draft ID: {report.draft_id or 'none'}",
        f"Generated: {report.generated_at}",
        f"Publishable support rows: {report.publishable_support_count}",
        f"Unsupported rows: {report.unsupported_count}",
        "",
        "| Claim | Source | Trust Tier | Role | Status | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.rows:
        claim = row.claim_text.replace("|", "\\|")
        source = (row.source_name or row.source_id or "none").replace("|", "\\|")
        notes = row.notes.replace("|", "\\|")
        lines.append(
            f"| {claim} | {source} | {row.trust_tier} | {row.citation_role} | "
            f"{row.support_status} | {notes} |"
        )
    return "\n".join(lines)


def build_citation_matrix(
    config: Config,
    draft_id: Optional[str] = None,
    topic_id: Optional[str] = None,
    week: str = "current",
) -> CitationMatrixReport:
    topic_id, draft_id = _topic_for_draft(config, draft_id, topic_id)
    claims = _claims(config, topic_id)
    sources = _sources(config, topic_id)
    rows = _build_rows(topic_id, draft_id, claims, sources)
    _persist(config, topic_id, draft_id, rows)

    week_id = target_week(week)
    output_dir = intelligence_dir(config, week_id)
    suffix = draft_id or topic_id
    markdown_path = output_dir / f"citation_matrix_{suffix}.md"
    json_path = output_dir / f"citation_matrix_{suffix}.json"
    report = CitationMatrixReport(
        week_id=week_id,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        topic_id=topic_id,
        draft_id=draft_id,
        rows=rows,
        markdown_path=str(markdown_path),
        json_path=str(json_path),
    )
    markdown_path.write_text(_render_markdown(report))
    json_path.write_text(json.dumps(asdict(report), indent=2))
    return report

