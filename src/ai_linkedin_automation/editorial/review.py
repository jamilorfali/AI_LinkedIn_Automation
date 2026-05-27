import json
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from ai_linkedin_automation.config import CONFIG_DIR, Config, load_yaml_file, resolve_project_path
from ai_linkedin_automation.scoring.scoring import _has_vendor_comparison, _political_risk
from ai_linkedin_automation.storage.db import connect_db, transaction


UNSUPPORTED_CLAIM_PATTERNS = [
    r"\bguarantee[sd]?\b",
    r"\bprove[sd]?\b",
    r"\bfirst\b",
    r"\bonly\b",
    r"\balways\b",
    r"\bnever\b",
    r"\beveryone\b",
    r"\bno one\b",
    r"\brevolutionary\b",
    r"\bgame[- ]changing\b",
    r"\bchanges everything\b",
    r"\bbest\b",
    r"\bbeats\b",
]

FACTUAL_SIGNAL_PATTERNS = [
    r"\b\d+(\.\d+)?%?\b",
    r"\breport(ed|s)?\b",
    r"\bpaper\b",
    r"\bstudy\b",
    r"\bresearch\b",
    r"\bbenchmark\b",
    r"\bevaluat(e|es|ed|ion)\b",
    r"\baccording to\b",
    r"\bpublished\b",
    r"\blaunched\b",
    r"\bannounced\b",
]


@dataclass
class ClaimAssessment:
    text: str
    support_status: str
    support_level: str
    source_id: str
    notes: str


@dataclass
class VoiceCheck:
    name: str
    passed: bool
    notes: str


@dataclass
class EditorialReview:
    draft_id: str
    review_id: str
    status: str
    claim_assessments: List[ClaimAssessment]
    voice_checks: List[VoiceCheck]
    risk_notes: List[str]
    review_path: str
    json_path: str

    @property
    def unsupported_claim_count(self) -> int:
        return sum(1 for claim in self.claim_assessments if claim.support_status in {"unsupported", "remove"})

    @property
    def voice_issue_count(self) -> int:
        return sum(1 for check in self.voice_checks if not check.passed)


def _week_slug(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _target_week(week: str) -> str:
    if week == "current":
        return _week_slug(datetime.now())
    return week


def _packet_dir(config: Config, week: str) -> Path:
    output_dir = resolve_project_path(config.storage.review_packets_dir) / _target_week(week)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _sentences(text: str) -> List[str]:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def _looks_like_claim(sentence: str) -> bool:
    if sentence.endswith("?"):
        return False
    lowered = sentence.lower()
    if any(re.search(pattern, lowered) for pattern in FACTUAL_SIGNAL_PATTERNS):
        return True
    return len(sentence.split()) >= 8 and not lowered.startswith(("for leaders", "what are"))


def _source_support(sources: List[Dict[str, str]]) -> Tuple[str, str]:
    if not sources:
        return "", "No source attached to this draft topic."
    for tier in ("primary", "high_trust"):
        for source in sources:
            if source["trust_tier"] == tier:
                return source["source_id"], f"Supported by {tier.replace('_', ' ')} source."
    source = sources[0]
    return source["source_id"], f"Source is {source['trust_tier']}; verify before making strong claims."


def extract_claims(text: str) -> List[str]:
    claims = []
    for sentence in _sentences(text):
        if _looks_like_claim(sentence):
            claims.append(sentence)
    return claims


def assess_claims(text: str, sources: List[Dict[str, str]]) -> List[ClaimAssessment]:
    claims = extract_claims(text)
    if not claims and text.strip():
        claims = [text.strip()]

    assessments: List[ClaimAssessment] = []
    source_id, source_note = _source_support(sources)
    has_publishable_source = any(source["trust_tier"] in {"primary", "high_trust"} for source in sources)

    for claim in claims:
        lowered = claim.lower()
        if any(re.search(pattern, lowered) for pattern in UNSUPPORTED_CLAIM_PATTERNS):
            support_status = "remove"
            support_level = "unsupported"
            notes = "Overstrong or hype-like claim. Remove unless specifically verified."
        elif not sources:
            support_status = "unsupported"
            support_level = "unsupported"
            notes = "No source is attached to the topic."
        elif not has_publishable_source:
            support_status = "weak_support"
            support_level = "weak support"
            notes = source_note
        else:
            support_status = "supported"
            support_level = source_note
            notes = "Keep wording modest and source-tethered."
        assessments.append(
            ClaimAssessment(
                text=claim,
                support_status=support_status,
                support_level=support_level,
                source_id=source_id,
                notes=notes,
            )
        )
    return assessments


def _style_rules() -> Dict[str, object]:
    return load_yaml_file(CONFIG_DIR / "style_rules.yaml")


def voice_checks(text: str) -> List[VoiceCheck]:
    rules = _style_rules()
    banned = [phrase.lower() for phrase in rules.get("banned_phrases", [])]
    lowered = text.lower()
    word_count = len(re.findall(r"\b\w+\b", text))
    short_range = rules.get("voice", {}).get("short_word_range", [150, 250])

    checks = [
        VoiceCheck(
            "No banned AI-giveaway phrases",
            not any(phrase in lowered for phrase in banned),
            "Remove phrases that sound generic, hypey, or AI-written.",
        ),
        VoiceCheck(
            "No vendor scorekeeping",
            not _has_vendor_comparison(lowered),
            "Avoid vendor-versus-vendor framing.",
        ),
        VoiceCheck(
            "Low political risk",
            _political_risk(lowered) != "high",
            "Public posts should avoid high-risk political framing.",
        ),
        VoiceCheck(
            "Short-first length",
            word_count <= int(short_range[1]),
            f"Current length is {word_count} words; short target is {short_range[0]}-{short_range[1]}.",
        ),
        VoiceCheck(
            "Plain punctuation",
            text.count(";") <= 1,
            "Avoid semicolon-heavy phrasing.",
        ),
        VoiceCheck(
            "No hashtag pile",
            len(re.findall(r"#\w+", text)) <= 3,
            "Use hashtags sparingly.",
        ),
    ]
    return checks


def _risk_notes(text: str, claims: Iterable[ClaimAssessment], checks: Iterable[VoiceCheck]) -> List[str]:
    notes: List[str] = []
    if any(claim.support_status in {"unsupported", "remove"} for claim in claims):
        notes.append("Unsupported or overstrong claims must be edited before approval.")
    if any(not check.passed for check in checks):
        notes.append("Voice/style checklist has open issues.")
    political = _political_risk(text.lower())
    if political != "low":
        notes.append(f"Political risk classified as {political}.")
    if _has_vendor_comparison(text.lower()):
        notes.append("Vendor scorekeeping detected.")
    if not notes:
        notes.append("No editorial blockers detected by deterministic review.")
    return notes


def _draft_context(config: Config, draft_id: str) -> Tuple[Dict[str, object], List[Dict[str, str]]]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        draft = conn.execute(
            """
            SELECT
                drafts.id,
                drafts.topic_id,
                drafts.version,
                drafts.content,
                drafts.content_hash,
                topics.title AS topic_title
            FROM drafts
            LEFT JOIN topics ON topics.id = drafts.topic_id
            WHERE drafts.id = ?
            """,
            (draft_id,),
        ).fetchone()
        if not draft:
            raise ValueError(f"Draft not found: {draft_id}")

        sources = conn.execute(
            """
            SELECT
                sources.id AS source_id,
                sources.name AS source_name,
                sources.trust_tier,
                findings.title AS finding_title,
                findings.url
            FROM topic_findings
            JOIN findings ON findings.id = topic_findings.finding_id
            JOIN sources ON sources.id = findings.source_id
            WHERE topic_findings.topic_id = ?
            ORDER BY
                CASE sources.trust_tier
                    WHEN 'primary' THEN 0
                    WHEN 'high_trust' THEN 1
                    WHEN 'useful_but_verify' THEN 2
                    ELSE 3
                END,
                sources.name
            """,
            (draft["topic_id"],),
        ).fetchall()
        return dict(draft), [dict(source) for source in sources]
    finally:
        conn.close()


def _render_review(review: EditorialReview, draft: Dict[str, object], sources: List[Dict[str, str]]) -> str:
    source_lines = [
        f"- {source['source_name']} ({source['trust_tier']}): {source['url']}" for source in sources
    ]
    if not source_lines:
        source_lines = ["- No source attached to this draft topic."]

    claim_lines = [
        "\n".join(
            [
                f"### Claim {index}",
                claim.text,
                "",
                f"- Support status: {claim.support_status}",
                f"- Support level: {claim.support_level}",
                f"- Source ID: {claim.source_id or 'none'}",
                f"- Notes: {claim.notes}",
            ]
        )
        for index, claim in enumerate(review.claim_assessments, start=1)
    ]

    checklist_lines = [
        f"- [{'x' if check.passed else ' '}] {check.name}: {check.notes}"
        for check in review.voice_checks
    ]

    risk_lines = [f"- {note}" for note in review.risk_notes]

    return "\n".join(
        [
            "# Editorial Review Packet",
            "",
            f"Draft ID: {review.draft_id}",
            f"Topic: {draft.get('topic_title') or draft.get('topic_id')}",
            f"Status: {review.status}",
            f"Prepared: {datetime.now().isoformat(timespec='seconds')}",
            "",
            "## Claim Review",
            "",
            "\n\n".join(claim_lines),
            "",
            "## Voice And Style Checklist",
            "",
            "\n".join(checklist_lines),
            "",
            "## Risk Notes",
            "",
            "\n".join(risk_lines),
            "",
            "## Source Notes",
            "",
            "\n".join(source_lines),
            "",
            "## Prompt Packets To Use If Needed",
            "",
            "- `prompts/03_claim_extractor.md`",
            "- `prompts/04_citation_checker.md`",
            "- `prompts/07_voice_reviewer.md`",
            "- `prompts/08_political_risk_reviewer.md`",
            "- `prompts/09_vendor_sensitivity_reviewer.md`",
            "",
        ]
    )


def _persist_claims(config: Config, draft: Dict[str, object], claims: List[ClaimAssessment]) -> None:
    with transaction(config.storage.sqlite_path) as conn:
        conn.execute(
            """
            DELETE FROM citation_matrix_rows
            WHERE claim_id IN (
                SELECT id
                FROM claims
                WHERE topic_id = ? AND claim_type = 'draft_claim'
            )
            """,
            (draft["topic_id"],),
        )
        conn.execute(
            """
            DELETE FROM claims
            WHERE topic_id = ? AND claim_type = 'draft_claim'
            """,
            (draft["topic_id"],),
        )
        for claim in claims:
            claim_id = f"claim_{secrets.token_urlsafe(12)}"
            conn.execute(
                """
                INSERT INTO claims (
                    id, topic_id, claim_text, support_level, claim_type,
                    support_status, primary_source_id, source_id, verification_notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    draft["topic_id"],
                    claim.text,
                    claim.support_level,
                    "draft_claim",
                    claim.support_status,
                    claim.source_id or None,
                    claim.source_id or None,
                    claim.notes,
                    datetime.now().isoformat(),
                ),
            )


def _persist_review(config: Config, review: EditorialReview, draft: Dict[str, object]) -> None:
    with transaction(config.storage.sqlite_path) as conn:
        conn.execute(
            """
            INSERT INTO editorial_reviews (
                id, draft_id, content_hash, review_status, claim_count,
                unsupported_claim_count, voice_issue_count, review_path, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review.review_id,
                review.draft_id,
                draft["content_hash"],
                review.status,
                len(review.claim_assessments),
                review.unsupported_claim_count,
                review.voice_issue_count,
                review.review_path,
                datetime.now().isoformat(),
            ),
        )


def review_draft(config: Config, draft_id: str, week: str = "current") -> EditorialReview:
    """Run deterministic editorial review and write review artifacts."""
    draft, sources = _draft_context(config, draft_id)
    text = str(draft["content"])
    claims = assess_claims(text, sources)
    checks = voice_checks(text)
    risk_notes = _risk_notes(text, claims, checks)
    status = "needs_edits" if (
        any(claim.support_status in {"unsupported", "remove"} for claim in claims)
        or any(not check.passed for check in checks)
    ) else "ready_for_approval"

    review_id = f"editorial_{secrets.token_urlsafe(12)}"
    output_dir = _packet_dir(config, week)
    review_path = output_dir / f"editorial_review_{draft_id}.md"
    json_path = output_dir / f"editorial_review_{draft_id}.json"

    review = EditorialReview(
        draft_id=draft_id,
        review_id=review_id,
        status=status,
        claim_assessments=claims,
        voice_checks=checks,
        risk_notes=risk_notes,
        review_path=str(review_path),
        json_path=str(json_path),
    )

    review_path.write_text(_render_review(review, draft, sources))
    json_payload = asdict(review)
    json_path.write_text(json.dumps(json_payload, indent=2))
    _persist_claims(config, draft, claims)
    _persist_review(config, review, draft)
    return review
