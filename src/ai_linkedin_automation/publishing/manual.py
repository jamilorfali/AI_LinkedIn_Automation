from datetime import datetime
from ai_linkedin_automation.article_package import extract_section, is_article_package, reference_count
from ai_linkedin_automation.config import Config, resolve_project_path
from ai_linkedin_automation.publishing.safety_gate import evaluate_manual_posting_gate
from ai_linkedin_automation.storage.db import connect_db


def _week_slug(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _squash_blank_lines(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                cleaned.append("")
            blank = True
            continue
        cleaned.append(line)
        blank = False
    return "\n".join(cleaned).strip()


def _clean_post_body(content: str, source_names: list[str]) -> str:
    """Keep the manual package copy/paste body free of operator-only notes."""
    if is_article_package(content):
        return extract_section(content, "Feed Post")

    names = [name for name in source_names if name]
    lines = []
    for line in (content or "").splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered.startswith("source topic:") or lowered.startswith("draft id:"):
            continue
        if lowered.startswith("source:") and any(name in stripped for name in names):
            continue
        if "trust tier" in lowered or "current recommendation" in lowered:
            continue
        if lowered.startswith("abstract:") or lowered.startswith("announce type:"):
            continue
        lines.append(line.rstrip())
    return _squash_blank_lines("\n".join(lines))


def _article_package_sections(content: str) -> dict[str, str]:
    if not is_article_package(content):
        return {}
    return {
        "feed_post": extract_section(content, "Feed Post"),
        "article_title": extract_section(content, "Article Title").replace("*", "").strip(),
        "article_body": extract_section(content, "Article Body"),
        "references": extract_section(content, "References"),
        "sourcing_note": extract_section(content, "Note On Sourcing"),
        "first_comment": extract_section(content, "Suggested First Comment"),
        "image_prompt": extract_section(content, "Advanced Image Brief"),
        "image_alt_text": extract_section(content, "Image Alt Text"),
    }


def build_manual_posting_package(config: Config, draft_id: str) -> str:
    decision = evaluate_manual_posting_gate(config, draft_id)
    if not decision.allowed:
        raise RuntimeError(f"Manual posting package blocked. Reason: {decision.reason}")

    conn = connect_db(config.storage.sqlite_path)
    try:
        row = conn.execute(
            """
            SELECT
                drafts.content,
                drafts.content_hash,
                drafts.version,
                topics.title AS topic_title,
                topics.summary AS topic_summary,
                topics.political_risk,
                topics.recommendation
            FROM drafts
            LEFT JOIN topics ON topics.id = drafts.topic_id
            WHERE drafts.id = ?
            """,
            (draft_id,),
        ).fetchone()
        sources = conn.execute(
            """
            SELECT findings.title, findings.url, sources.name AS source_name, sources.trust_tier
            FROM drafts
            LEFT JOIN topic_findings ON topic_findings.topic_id = drafts.topic_id
            LEFT JOIN findings ON findings.id = topic_findings.finding_id
            LEFT JOIN sources ON sources.id = findings.source_id
            WHERE drafts.id = ? AND findings.id IS NOT NULL
            ORDER BY sources.trust_tier, findings.title
            """,
            (draft_id,),
        ).fetchall()
    finally:
        conn.close()

    if not row:
        raise RuntimeError("Draft not found.")

    now = datetime.now()
    output_dir = resolve_project_path(config.storage.exports_dir) / "manual_posting" / _week_slug(now)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{draft_id}_final_post_package.md"

    topic = row["topic_title"] or draft_id
    content = row["content"]
    approval_action = decision.approval_action or "approved"
    article_sections = _article_package_sections(content)
    source_lines = []
    source_names = []
    for source in sources:
        source_names.append(source["source_name"] or "")
        source_lines.append(
            f"- {source['title']} - {source['source_name']} ({source['trust_tier']}): {source['url']}"
        )
    source_text = "\n".join(source_lines) if source_lines else "See the weekly review packet for source links and claim notes."
    post_body = _clean_post_body(content, source_names)
    article_title = article_sections.get("article_title") or topic
    article_body = article_sections.get("article_body", "")
    references = article_sections.get("references", "")
    sourcing_note = article_sections.get("sourcing_note", "")
    first_comment = article_sections.get("first_comment") or "Add a short sourcing note or the most important primary source link after the article is live."
    image_prompt = article_sections.get("image_prompt") or "Create a polished LinkedIn thumbnail that represents the article thesis. No logos, no watermark, no copyrighted source imagery."
    image_alt_text = article_sections.get("image_alt_text") or f"Editorial image for {article_title}."
    references_count = reference_count(content)
    package = f"""# Final LinkedIn Posting Package

Status: {approval_action}
Target: {config.publishing.target}
Posting mode: Manual
Draft ID: {draft_id}
Draft version: {row["version"]}
Content hash: {row["content_hash"]}
Prepared: {now.isoformat(timespec="seconds")}

## Topic

{topic}

## Copy/paste feed post

Legacy label: Copy/paste post body

Use this as the short LinkedIn post. Replace `[PASTE ARTICLE LINK]` after the article is published.

{post_body}

## Full LinkedIn article title

{article_title}

## Full LinkedIn article body

{article_body or "No long-form article body was generated for this legacy draft."}

## References [{references_count}]

{references or source_text}

## Note on sourcing

{sourcing_note or "Review source quality manually before posting. Add more sources if the thesis makes legal, empirical, or scholarly claims."}

## Suggested first comment

{first_comment}

## Article thumbnail image prompt

Use this prompt in Gemini, ChatGPT image generation, or another explicitly approved image tool. Hard Zero Mode does not call paid image APIs automatically.

{image_prompt}

Alt text: {image_alt_text}

## Suggested hashtags

#AI #AIStrategy #EnterpriseAI #DigitalTransformation #Leadership

Use hashtags sparingly. Remove anything that feels performative.

## Source links for your own review

{source_text}

## Visual recommendation

Create the article thumbnail before posting the article. Media still requires separate approval and should be reviewed against the exact article thesis.

## Posting checklist

- Read once out loud.
- Remove anything that sounds too polished or too AI-written.
- Confirm the feed post is under 100 words before the link.
- Confirm the article is under roughly 2,000 words unless the topic earns more.
- Confirm the References section has enough support for the claims, ideally 10-20 sources.
- Confirm the first comment adds source context rather than repeating the post.
- Confirm no internal or confidential context.
- Confirm no client or prospect reference.
- Confirm no vendor comparison.
- Confirm every source is public and appropriate to cite.
- Generate or attach an eye-catching article thumbnail manually.
- Post manually on personal LinkedIn.
- Archive the final post URL with:

```bash
ai-linkedin archive-post --draft-id {draft_id} --post-url LINKEDIN_POST_URL
```
"""
    output_file.write_text(package)
    return str(output_file)
