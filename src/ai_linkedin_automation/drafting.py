import hashlib
import logging
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

from ai_linkedin_automation.article_package import (
    generate_article_package_from_topic,
    is_article_package,
    reference_count,
)
from ai_linkedin_automation.config import Config
from ai_linkedin_automation.storage.db import connect_db
from ai_linkedin_automation.storage.db import transaction

logger = logging.getLogger(__name__)


class DraftingError(Exception):
    """Raised when a draft cannot be generated or stored."""


def _first_topic_block(package_content: str) -> tuple:
    lines = package_content.splitlines()
    title = ""
    body = []
    in_first_option = False

    for line in lines:
        if line.startswith("## 1. "):
            title = line[6:].strip()
            in_first_option = True
            continue
        if in_first_option and line.startswith("## "):
            break
        if in_first_option and line.strip():
            if line.strip() not in {"Scorecard:", "Source note:", "Risk note:"}:
                body.append(line.strip())

    if title:
        return title, body

    for line in lines:
        if line.startswith("## "):
            if title:
                break
            title = line[3:].strip()
            continue
        if title and line.strip():
            body.append(line.strip())
            if len(body) >= 3:
                break

    if not title:
        raise DraftingError("No topic found in weekly package")
    return title, body


def generate_draft_from_weekly_package(
    weekly_package_path: str,
    template_path: Optional[str] = None,
) -> str:
    """Generate a plain-language draft starter from a weekly package."""
    package_content = Path(weekly_package_path).read_text()
    title, body = _first_topic_block(package_content)
    summary = " ".join(body[:3]).strip()
    if not summary:
        summary = "This topic needs a little more source review before it becomes a final post."

    template = get_default_template() if not template_path else load_template(template_path)
    draft = template.format(title=title, summary=summary)
    logger.info("Generated draft starter for %s", title)
    return draft


def generate_draft_from_topic(config: Config, topic_id: str) -> str:
    """Generate a source-backed LinkedIn article package for a topic candidate."""
    package = generate_article_package_from_topic(config, topic_id)
    return package.markdown()


def generate_short_draft_from_topic(config: Config, topic_id: str) -> str:
    """Generate the legacy plain-language short draft starter for tests and fallbacks."""
    conn = connect_db(config.storage.sqlite_path)
    try:
        row = conn.execute(
            """
            SELECT
                topics.title,
                topics.summary,
                topics.recommendation,
                topics.political_risk,
                topics.draft_readiness,
                sources.name AS source_name,
                sources.trust_tier
            FROM topics
            LEFT JOIN topic_findings ON topic_findings.topic_id = topics.id
            LEFT JOIN findings ON findings.id = topic_findings.finding_id
            LEFT JOIN sources ON sources.id = findings.source_id
            WHERE topics.id = ?
            LIMIT 1
            """,
            (topic_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise DraftingError(f"Topic not found: {topic_id}")

    summary = _clean_topic_summary(row["summary"] or row["title"] or "")
    if not summary:
        summary = "This topic is still early, so it is worth treating as a signal rather than a conclusion."

    source_name = row["source_name"] or "a public source"
    trust_tier = (row["trust_tier"] or "unknown").replace("_", " ")
    source_note = (
        "I would treat it as a useful signal, not a final conclusion yet."
        if trust_tier not in {"primary", "high trust"}
        else "It is grounded enough to be useful for a leadership conversation."
    )

    return f"""A useful AI story this week is not about the model itself. It is about the operating habit it points to.

{summary}

What matters for leaders is the pattern underneath it: teams will need clearer rules for where AI can act, who checks the work, and when a person must stay in the loop.

{source_note}

The question I would bring back to the team is simple: if this kind of AI capability becomes normal, what decision or workflow should we redesign before it redesigns us?

Source: {source_name}"""


def _clean_topic_summary(value: str, max_chars: int = 520) -> str:
    """Turn source-heavy summaries into post-ready prose."""
    text = value.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"arXiv:\S+\s+Announce Type:\s+\w+\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bAbstract:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    selected = []
    total = 0
    for sentence in sentences:
        cleaned = sentence.strip()
        if not cleaned:
            continue
        if total + len(cleaned) > max_chars and selected:
            break
        selected.append(cleaned)
        total += len(cleaned) + 1
        if len(selected) >= 3:
            break
    result = " ".join(selected).strip()
    if len(result) > max_chars:
        result = result[: max_chars - 1].rstrip(" ,;:") + "."
    return result


def get_default_template() -> str:
    """Default no-hype LinkedIn draft starter."""
    return """This caught my eye because it points to a practical AI question leaders are already facing.

{summary}

The part that matters is not just the headline. It is what this says about how teams will evaluate, govern, and apply AI in real work.

For leaders, the useful question is: what operating habit needs to change if this becomes normal?

Source topic: {title}"""


def load_template(template_path: str) -> str:
    """Load a custom template from file."""
    return Path(template_path).read_text()


def _ensure_topic(conn, topic_id: str) -> None:
    row = conn.execute("SELECT id FROM topics WHERE id = ?", (topic_id,)).fetchone()
    if row:
        return
    conn.execute(
        """
        INSERT INTO topics (id, title, summary, recommendation, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            topic_id,
            topic_id,
            "Placeholder topic created when saving a draft directly.",
            "needs_review",
            datetime.now().isoformat(),
            datetime.now().isoformat(),
        ),
    )


def save_draft(db_path: str, topic_id: str, content: str) -> str:
    """Save draft to database and return draft_id."""
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    draft_id = f"draft_{secrets.token_urlsafe(12)}"
    draft_length_type = "article_package" if is_article_package(content) else "short"
    source_reference_count = reference_count(content)

    try:
        with transaction(db_path) as conn:
            _ensure_topic(conn, topic_id)
            row = conn.execute("SELECT MAX(version) FROM drafts WHERE topic_id = ?", (topic_id,)).fetchone()
            version = (row[0] or 0) + 1

            conn.execute(
                """
                INSERT INTO drafts (
                    id, topic_id, version, content, draft_text, draft_length_type,
                    source_reference_count, content_hash, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    topic_id,
                    version,
                    content,
                    content,
                    draft_length_type,
                    source_reference_count,
                    content_hash,
                    "pending_approval",
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ),
            )
            logger.info("Saved draft %s for topic %s", draft_id, topic_id)
            return draft_id
    except Exception as exc:
        logger.error("Failed to save draft: %s", exc)
        raise DraftingError(f"Failed to save draft: {exc}")
