import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Tuple

from ai_linkedin_automation.config import CONFIG_DIR, Config, load_yaml_file
from ai_linkedin_automation.storage.db import transaction


EXECUTIVE_KEYWORDS = {
    "strategy",
    "operations",
    "productivity",
    "revenue",
    "cost",
    "workforce",
    "risk",
    "governance",
    "enterprise",
    "business",
    "leadership",
    "decision",
    "adoption",
}

HIDDEN_GEM_KEYWORDS = {
    "arxiv",
    "research",
    "paper",
    "study",
    "benchmark",
    "evaluation",
    "infrastructure",
    "architecture",
    "dataset",
    "open source",
    "standard",
}

TECHNICAL_KEYWORDS = {
    "agent",
    "agents",
    "model",
    "reasoning",
    "multimodal",
    "robotics",
    "compute",
    "chip",
    "context",
    "tool",
    "inference",
    "training",
    "benchmark",
    "eval",
    "data",
}

POLITICAL_HIGH_KEYWORDS = {
    "election",
    "candidate",
    "partisan",
    "democrat",
    "republican",
    "culture war",
    "geopolitical",
}

POLITICAL_MEDIUM_KEYWORDS = {
    "policy",
    "regulation",
    "law",
    "government",
    "copyright",
    "antitrust",
}

VENDOR_COMPARISON_PATTERNS = [
    r"\bvs\.?\b",
    r"\bversus\b",
    r"\bbetter than\b",
    r"\bbeats\b",
    r"\bwin(s|ner)?\b",
]

SOURCE_CREDIBILITY = {
    "primary": 5,
    "high_trust": 4,
    "useful_but_verify": 2,
    "social_signal_only": 1,
    "blocked": 0,
}


@dataclass
class Scorecard:
    executive_relevance: int
    hidden_gem_value: int
    technical_signal: int
    source_credibility: int
    oracle_safe_fit: int
    draft_readiness: int
    political_risk: str
    recommendation: str
    category: str
    numeric_score: int


def load_scoring_config():
    """Load scoring rules from config/scoring.yaml."""
    return load_yaml_file(CONFIG_DIR / "scoring.yaml")


def load_scoring_weights():
    """Load scorecard weighting and hard gate config."""
    return load_yaml_file(CONFIG_DIR / "scoring_weights.yaml")


def _count_matches(content: str, keywords: Iterable[str]) -> int:
    count = 0
    for keyword in keywords:
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
        if re.search(pattern, content):
            count += 1
    return count


def _score_from_matches(match_count: int, base: int = 2) -> int:
    return max(1, min(5, base + match_count))


def _political_risk(content: str) -> str:
    if _count_matches(content, POLITICAL_HIGH_KEYWORDS):
        return "high"
    if _count_matches(content, POLITICAL_MEDIUM_KEYWORDS):
        return "medium"
    return "low"


def _has_vendor_comparison(content: str) -> bool:
    return any(re.search(pattern, content) for pattern in VENDOR_COMPARISON_PATTERNS)


def _category_from_scorecard(scorecard: Scorecard) -> str:
    if scorecard.executive_relevance >= 4 and scorecard.technical_signal >= 4:
        return "high_impact"
    if scorecard.technical_signal >= 4:
        return "academic"
    if scorecard.executive_relevance >= 4:
        return "industry"
    return "general"


def score_finding(title: str, summary: str, scoring_rules: list) -> Tuple[int, str]:
    """Backward-compatible keyword score used by older tests and summaries."""
    content = f"{title} {summary}".lower()
    max_score = 0
    best_category = "general"

    for rule in scoring_rules:
        for keyword in rule['keywords']:
            if re.search(r'\b' + re.escape(keyword.lower()) + r'\b', content):
                if rule['score'] > max_score:
                    max_score = rule['score']
                    best_category = rule['category']
                break

    return max_score, best_category


def build_scorecard(title: str, summary: str, trust_tier: str) -> Scorecard:
    content = f"{title} {summary}".lower()
    source_credibility = SOURCE_CREDIBILITY.get(trust_tier, 1)
    political_risk = _political_risk(content)
    vendor_comparison = _has_vendor_comparison(content)

    executive_relevance = _score_from_matches(_count_matches(content, EXECUTIVE_KEYWORDS), base=2)
    hidden_gem_value = _score_from_matches(_count_matches(content, HIDDEN_GEM_KEYWORDS), base=2)
    technical_signal = _score_from_matches(_count_matches(content, TECHNICAL_KEYWORDS), base=2)
    oracle_safe_fit = 2 if vendor_comparison else 4
    if political_risk == "high":
        oracle_safe_fit = 1
    elif political_risk == "medium":
        oracle_safe_fit = min(oracle_safe_fit, 3)

    draft_readiness = min(
        5,
        max(1, int(round((executive_relevance + hidden_gem_value + source_credibility) / 3))),
    )
    if source_credibility < 4:
        draft_readiness = min(draft_readiness, 2)
    if political_risk == "high" or vendor_comparison:
        draft_readiness = 1

    recommendation = "watch"
    if political_risk == "high" or vendor_comparison or source_credibility == 0:
        recommendation = "reject"
    elif (
        executive_relevance >= 4
        and hidden_gem_value >= 3
        and source_credibility >= 4
        and oracle_safe_fit >= 4
        and draft_readiness >= 4
        and political_risk == "low"
    ):
        recommendation = "draft_now"
    elif source_credibility < 4:
        recommendation = "save_for_verification"

    numeric_score = (
        executive_relevance * 2
        + hidden_gem_value * 2
        + technical_signal
        + source_credibility * 2
        + oracle_safe_fit
        + draft_readiness
    )

    provisional = Scorecard(
        executive_relevance=executive_relevance,
        hidden_gem_value=hidden_gem_value,
        technical_signal=technical_signal,
        source_credibility=source_credibility,
        oracle_safe_fit=oracle_safe_fit,
        draft_readiness=draft_readiness,
        political_risk=political_risk,
        recommendation=recommendation,
        category="general",
        numeric_score=numeric_score,
    )
    provisional.category = _category_from_scorecard(provisional)
    return provisional


def _topic_id_for_finding(finding_id: str, title: str) -> str:
    seed = finding_id or title
    digest = hashlib.sha256(seed.encode()).hexdigest()[:24]
    return f"topic_{digest}"


def _topic_summary(summary: str) -> str:
    summary = (summary or "").strip()
    if len(summary) <= 650:
        return summary
    return summary[:647].rstrip() + "..."


def _week_id() -> str:
    year, week, _ = datetime.now().isocalendar()
    return f"{year}-W{week:02d}"


def _upsert_topic_for_finding(conn, finding, scorecard: Scorecard) -> str:
    topic_id = _topic_id_for_finding(finding["id"], finding["title"])
    conn.execute(
        """
        INSERT INTO topics (
            id, week_id, title, summary, plain_english_summary, hidden_gem_angle,
            executive_relevance, executive_relevance_score,
            hidden_gem_value, hidden_gem_score,
            technical_signal, technical_signal_score,
            source_credibility, source_credibility_score,
            oracle_safe_fit, oracle_safe_fit_score,
            draft_readiness, draft_readiness_score,
            weighted_score, political_risk, recommendation, status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            week_id = excluded.week_id,
            title = excluded.title,
            summary = excluded.summary,
            plain_english_summary = excluded.plain_english_summary,
            hidden_gem_angle = excluded.hidden_gem_angle,
            executive_relevance = excluded.executive_relevance,
            executive_relevance_score = excluded.executive_relevance_score,
            hidden_gem_value = excluded.hidden_gem_value,
            hidden_gem_score = excluded.hidden_gem_score,
            technical_signal = excluded.technical_signal,
            technical_signal_score = excluded.technical_signal_score,
            source_credibility = excluded.source_credibility,
            source_credibility_score = excluded.source_credibility_score,
            oracle_safe_fit = excluded.oracle_safe_fit,
            oracle_safe_fit_score = excluded.oracle_safe_fit_score,
            draft_readiness = excluded.draft_readiness,
            draft_readiness_score = excluded.draft_readiness_score,
            weighted_score = excluded.weighted_score,
            political_risk = excluded.political_risk,
            recommendation = excluded.recommendation,
            status = excluded.status,
            updated_at = datetime('now')
        """,
        (
            topic_id,
            _week_id(),
            finding["title"],
            _topic_summary(finding["summary"] or ""),
            _topic_summary(finding["summary"] or ""),
            "Look for the practical leadership implication below the technical headline.",
            scorecard.executive_relevance,
            scorecard.executive_relevance,
            scorecard.hidden_gem_value,
            scorecard.hidden_gem_value,
            scorecard.technical_signal,
            scorecard.technical_signal,
            scorecard.source_credibility,
            scorecard.source_credibility,
            scorecard.oracle_safe_fit,
            scorecard.oracle_safe_fit,
            scorecard.draft_readiness,
            scorecard.draft_readiness,
            scorecard.numeric_score / 10,
            scorecard.political_risk,
            scorecard.recommendation,
            "candidate",
        ),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO topic_findings (topic_id, finding_id)
        VALUES (?, ?)
        """,
        (topic_id, finding["id"]),
    )
    return topic_id


def score_all_findings(config: Config):
    """Score unscored findings and create/update one topic candidate per finding."""
    scoring_config = load_scoring_config()
    scoring_rules = scoring_config['scoring_rules']

    with transaction(config.storage.sqlite_path) as conn:
        findings = conn.execute(
            """
            SELECT
                findings.id,
                findings.title,
                findings.summary,
                findings.score,
                sources.trust_tier
            FROM findings
            JOIN sources ON sources.id = findings.source_id
            WHERE findings.score IS NULL
            """
        ).fetchall()

        scored_count = 0
        for finding in findings:
            legacy_score, legacy_category = score_finding(
                finding["title"],
                finding["summary"] or "",
                scoring_rules,
            )
            scorecard = build_scorecard(
                finding["title"],
                finding["summary"] or "",
                finding["trust_tier"],
            )
            category = scorecard.category if scorecard.category != "general" else legacy_category
            numeric_score = max(legacy_score, scorecard.numeric_score)

            conn.execute(
                """
                UPDATE findings
                SET score = ?, category = ?, scored_at = datetime('now')
                WHERE id = ?
                """,
                (numeric_score, category, finding["id"]),
            )
            scorecard.category = category
            _upsert_topic_for_finding(conn, finding, scorecard)
            scored_count += 1

        return scored_count


def top_topics(config: Config, limit: int = 5) -> List[Dict[str, object]]:
    """Return ranked topic candidates for weekly package generation."""
    with transaction(config.storage.sqlite_path) as conn:
        rows = conn.execute(
            """
            SELECT
                topics.*,
                findings.url AS source_url,
                findings.source_id,
                sources.name AS source_name,
                sources.trust_tier,
                findings.score AS finding_score
            FROM topics
            JOIN topic_findings ON topic_findings.topic_id = topics.id
            JOIN findings ON findings.id = topic_findings.finding_id
            JOIN sources ON sources.id = findings.source_id
            WHERE topics.recommendation != 'reject'
              AND COALESCE(topics.status, 'candidate') NOT IN ('replaced_by_refresh', 'undone_refresh')
            ORDER BY
                CASE topics.recommendation WHEN 'draft_now' THEN 0 ELSE 1 END,
                topics.executive_relevance DESC,
                topics.hidden_gem_value DESC,
                topics.source_credibility DESC,
                topics.draft_readiness DESC,
                findings.score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
