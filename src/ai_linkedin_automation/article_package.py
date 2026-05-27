from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

from ai_linkedin_automation.config import Config
from ai_linkedin_automation.storage.db import connect_db


ARTICLE_PACKAGE_MARKER = "# LinkedIn Article Package"


@dataclass
class ArticleReference:
    author: str
    year: str
    title: str
    publisher: str
    url: str
    role: str = "supporting"

    def citation(self) -> str:
        return f"{self.author} ({self.year})"

    def markdown(self) -> str:
        return f"- {self.author}. ({self.year}). *{self.title}*. {self.publisher}. {self.url}"


@dataclass
class ArticlePackage:
    title: str
    feed_post: str
    article_body: str
    references: List[ArticleReference]
    sourcing_note: str
    first_comment: str
    image_prompt: str
    image_alt_text: str

    def markdown(self) -> str:
        references = "\n".join(reference.markdown() for reference in self.references)
        return f"""{ARTICLE_PACKAGE_MARKER}

## Feed Post

{self.feed_post}

## Article Title

**{self.title}**

## Article Body

{self.article_body}

## References

{references}

## Note On Sourcing

{self.sourcing_note}

## Suggested First Comment

{self.first_comment}

## Advanced Image Brief

{self.image_prompt}

## Image Alt Text

{self.image_alt_text}
"""


def is_article_package(content: str) -> bool:
    return ARTICLE_PACKAGE_MARKER in (content or "")


def extract_section(content: str, heading: str) -> str:
    """Extract a second-level markdown section from a generated article package."""
    pattern = rf"^## {re.escape(heading)}\s*$"
    lines = (content or "").splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            start = index + 1
            break
    if start is None:
        return ""
    collected: List[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        collected.append(line)
    return "\n".join(collected).strip()


def reference_count(content: str) -> int:
    references = extract_section(content, "References")
    return len([line for line in references.splitlines() if line.strip().startswith("- ")])


CURATED_REFERENCES: List[ArticleReference] = [
    ArticleReference(
        "National Institute of Standards and Technology",
        "2023",
        "Artificial Intelligence Risk Management Framework (AI RMF 1.0)",
        "U.S. Department of Commerce",
        "https://www.nist.gov/itl/ai-risk-management-framework",
        "governance",
    ),
    ArticleReference(
        "National Institute of Standards and Technology",
        "2024",
        "Artificial Intelligence Risk Management Framework: Generative AI Profile",
        "U.S. Department of Commerce",
        "https://www.nist.gov/itl/ai-risk-management-framework",
        "governance",
    ),
    ArticleReference(
        "OECD",
        "2024",
        "OECD AI Principles",
        "Organisation for Economic Co-operation and Development",
        "https://oecd.ai/en/ai-principles",
        "governance",
    ),
    ArticleReference(
        "European Parliament and Council of the European Union",
        "2024",
        "Regulation (EU) 2024/1689 laying down harmonised rules on artificial intelligence",
        "Official Journal of the European Union",
        "https://data.europa.eu/eli/reg/2024/1689/oj",
        "governance",
    ),
    ArticleReference(
        "International Organization for Standardization",
        "2023",
        "ISO/IEC 42001: Artificial intelligence management system",
        "ISO",
        "https://www.iso.org/standard/81230.html",
        "governance",
    ),
    ArticleReference(
        "Stanford Institute for Human-Centered Artificial Intelligence",
        "2025",
        "AI Index Report",
        "Stanford University",
        "https://aiindex.stanford.edu/report/",
        "market",
    ),
    ArticleReference(
        "McKinsey & Company",
        "2025",
        "The State of AI",
        "McKinsey Global Survey",
        "https://www.mckinsey.com/capabilities/quantumblack/our-insights",
        "enterprise",
    ),
    ArticleReference(
        "MIT Sloan Management Review",
        "2025",
        "Artificial intelligence insights for managers",
        "MIT Sloan Management Review",
        "https://sloanreview.mit.edu/tag/artificial-intelligence/",
        "enterprise",
    ),
    ArticleReference(
        "Microsoft WorkLab",
        "2025",
        "Work Trend Index and AI at work research",
        "Microsoft",
        "https://www.microsoft.com/en-us/worklab/",
        "enterprise",
    ),
    ArticleReference(
        "World Economic Forum",
        "2025",
        "Artificial intelligence and work transformation",
        "World Economic Forum",
        "https://www.weforum.org/topics/artificial-intelligence/",
        "enterprise",
    ),
    ArticleReference(
        "Brookings Institution",
        "2024",
        "Artificial intelligence governance and competition research",
        "Brookings Institution",
        "https://www.brookings.edu/topics/artificial-intelligence/",
        "governance",
    ),
    ArticleReference(
        "Pew Research Center",
        "2025",
        "Public attitudes toward artificial intelligence",
        "Pew Research Center",
        "https://www.pewresearch.org/topic/internet-technology/artificial-intelligence/",
        "trust",
    ),
    ArticleReference(
        "Google Cloud",
        "2025",
        "AI and machine learning product research and implementation guidance",
        "Google Cloud Blog",
        "https://cloud.google.com/blog/products/ai-machine-learning",
        "implementation",
    ),
    ArticleReference(
        "MIT News",
        "2025",
        "Artificial intelligence research and deployment coverage",
        "Massachusetts Institute of Technology",
        "https://news.mit.edu/topic/artificial-intelligence2",
        "research",
    ),
    ArticleReference(
        "Boston Consulting Group",
        "2025",
        "Artificial intelligence transformation insights",
        "Boston Consulting Group",
        "https://www.bcg.com/capabilities/artificial-intelligence",
        "enterprise",
    ),
    ArticleReference(
        "VentureBeat",
        "2025",
        "AI product and enterprise technology reporting",
        "VentureBeat",
        "https://venturebeat.com/category/ai/",
        "market",
    ),
]


def _clean(text: str, max_chars: int = 900) -> str:
    text = re.sub(r"\s+", " ", (text or "").replace("\r", " ").replace("\n", " ")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "."


def _topic_context(config: Config, topic_id: str) -> Dict[str, object]:
    with connect_db(config.storage.sqlite_path) as conn:
        topic = conn.execute(
            """
            SELECT id, title, summary, plain_english_summary, hidden_gem_angle,
                   recommendation, political_risk, draft_readiness
            FROM topics
            WHERE id = ?
            """,
            (topic_id,),
        ).fetchone()
        if not topic:
            raise ValueError(f"Topic not found: {topic_id}")
        sources = conn.execute(
            """
            SELECT findings.title, findings.summary, findings.url,
                   sources.name AS source_name, sources.trust_tier
            FROM topic_findings
            JOIN findings ON findings.id = topic_findings.finding_id
            LEFT JOIN sources ON sources.id = findings.source_id
            WHERE topic_findings.topic_id = ?
            ORDER BY
              CASE sources.trust_tier
                WHEN 'primary' THEN 1
                WHEN 'high_trust' THEN 2
                ELSE 3
              END,
              findings.title
            """,
            (topic_id,),
        ).fetchall()
    return {"topic": dict(topic), "sources": [dict(row) for row in sources]}


def _source_references(sources: List[Dict[str, object]]) -> List[ArticleReference]:
    refs: List[ArticleReference] = []
    seen_urls = set()
    for source in sources:
        url = str(source.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        source_name = str(source.get("source_name") or "Source").strip()
        title = _clean(str(source.get("title") or source_name), max_chars=140)
        refs.append(
            ArticleReference(
                source_name,
                "n.d.",
                title,
                source_name,
                url,
                "primary_source",
            )
        )
    return refs


def _reference_dossier(sources: List[Dict[str, object]], limit: int = 16) -> List[ArticleReference]:
    refs = _source_references(sources)
    seen_urls = {ref.url for ref in refs}
    for reference in CURATED_REFERENCES:
        if len(refs) >= limit:
            break
        if reference.url in seen_urls:
            continue
        refs.append(reference)
        seen_urls.add(reference.url)
    return refs


def _bold_title(topic_title: str, summary: str) -> str:
    text = f"{topic_title} {summary}".lower()
    if "govern" in text or "risk" in text or "checklist" in text:
        return "The AI Checklist Leaders Are Missing"
    if "agent" in text:
        return "AI Agents Need Permission Slips"
    if "legacy" in text or "architecture" in text:
        return "Your AI Strategy Has a Legacy-System Problem"
    if "productivity" in text or "work" in text:
        return "AI Productivity Is a Workflow Bet"
    if "benchmark" in text or "evaluation" in text:
        return "Benchmark Wins Are Not Business Readiness"
    return "The AI Story Hiding in Plain Sight"


def _lede(title: str, source_name: str) -> str:
    if "Checklist" in title:
        return "Most AI governance fails in the same boring place: the handoff."
    if "Permission" in title:
        return "The next AI risk is not a smarter model. It is a model that can act without a clear permission boundary."
    if "Legacy" in title:
        return "The companies most excited about AI may be about to automate around systems they should have redesigned."
    if "Productivity" in title:
        return "AI productivity will not come from giving every employee a chatbot and hoping the calendar gets lighter."
    return "The useful AI signal this week is not the headline. It is the operating model hiding underneath it."


def _feed_post(title: str, thesis: str) -> str:
    post = f"""{_lede(title, '')}

The better question is this: {thesis}

I wrote the full article as a practical read for leaders who need the AI conversation to move from demos to decisions.

Full article: [PASTE ARTICLE LINK]"""
    words = post.split()
    if len(words) <= 95:
        return post
    return " ".join(words[:92]).rstrip(" ,;:") + "...\n\nFull article: [PASTE ARTICLE LINK]"


def _article_body(
    title: str,
    topic: Dict[str, object],
    sources: List[Dict[str, object]],
    refs: List[ArticleReference],
) -> str:
    topic_title = str(topic.get("title") or title)
    summary = _clean(str(topic.get("summary") or topic.get("plain_english_summary") or topic_title))
    source_name = str((sources[0] or {}).get("source_name") or "a public source") if sources else "a public source"
    source_ref = refs[0].citation() if refs else source_name
    governance_ref = next((ref.citation() for ref in refs if "NIST" in ref.author), "NIST (2023)")
    eu_ref = next((ref.citation() for ref in refs if "European" in ref.author), "European Parliament and Council of the European Union (2024)")
    oecd_ref = next((ref.citation() for ref in refs if ref.author == "OECD"), "OECD (2024)")
    enterprise_ref = next((ref.citation() for ref in refs if "McKinsey" in ref.author), "McKinsey & Company (2025)")
    trust_ref = next((ref.citation() for ref in refs if "Pew" in ref.author), "Pew Research Center (2025)")

    thesis = (
        "what must be true in the workflow before AI output is allowed to become action?"
    )
    return f"""**The opinions expressed here are my own and do not reflect the views of my employer.**

{_lede(title, source_name)}

The source that started this draft is {source_ref}. The surface topic is "{topic_title}." The more useful business question is narrower and harder: {thesis}

{summary}

Strip away the product language and the lesson is practical. AI does not become safe, useful, or trusted because a policy says it should. It becomes those things when the work has visible checkpoints: what the system saw, what it inferred, what it changed, who reviewed it, and what happens when it is wrong.

### 1. The control layer matters more than the demo

The first mistake leaders make is treating AI governance as a document exercise. Frameworks such as {governance_ref}, {oecd_ref}, and {eu_ref} point in a different direction. They push organizations toward accountability, transparency, contestability, risk management, and traceability. Those are not abstract values. They are workflow requirements.

If an AI system summarizes a customer issue, drafts a financial explanation, ranks a supplier risk, or recommends a next action, the organization needs to know which step is assistance and which step is decision. That boundary is where most real adoption either becomes durable or quietly breaks.

### 2. The operating model is the product

AI strategy is often described as a model choice, a vendor choice, or a tooling choice. For most enterprises, that framing is too small. The operating model is the product: who owns the workflow, who approves exceptions, who validates sources, who monitors failure, and who can pause the system when the output looks plausible but wrong.

That is why the enterprise research base matters. Adoption studies such as {enterprise_ref} keep showing that the gap is not only technical capability. The gap is whether organizations redesign work around the capability. A chatbot dropped into a messy process usually gives you a faster messy process.

### 3. Trust is built in the review moments

The public conversation about AI trust can sound philosophical, but inside a company it becomes concrete quickly. Employees want to know when AI is helping, when it is guessing, and whether they will be blamed for a tool's confident mistake. Public-trust research such as {trust_ref} is useful here because it reminds leaders that confidence in AI is social as much as technical.

The review moment is where that trust gets earned. A good AI workflow should make it easy for a person to see the source, the claim, the recommended action, and the uncertainty. If a user has to reverse-engineer the system to understand why it produced an answer, the workflow is not ready for high-stakes use.

### What I would do next

Before funding another broad AI pilot, I would ask for one page:

1. What decision or work product will AI touch?
2. What sources or inputs is it allowed to use?
3. What evidence must it show?
4. Who approves the output before it affects a customer, employee, dollar, or public commitment?
5. What gets logged so the team can learn from mistakes?

That one page will reveal more about readiness than a polished demo. It also turns the AI conversation into something executives can actually govern.

The headline is not that AI needs more rules. The headline is that AI needs better-designed moments of human judgment. Without those moments, the organization is not scaling intelligence. It is scaling ambiguity."""


def _sourcing_note(refs: List[ArticleReference]) -> str:
    primary = [ref for ref in refs if ref.role == "primary_source"]
    primary_text = (
        f"The opening argument is anchored in the source article ({primary[0].citation()}). "
        if primary
        else "The opening argument is anchored in the selected public source. "
    )
    return (
        primary_text
        + "The additional references are included to support the governance, legal, trust, and enterprise-adoption claims around the thesis. "
        "Official standards, laws, and institutional frameworks are cited where the article discusses obligations or control principles. "
        "Industry and research sources are used for adoption context. This package is still a human review artifact: before posting, verify that every source is current, public, and appropriate for the exact claims being made."
    )


def _image_prompt(title: str, topic: Dict[str, object], refs: List[ArticleReference]) -> str:
    context = _clean(str(topic.get("summary") or topic.get("title") or ""), max_chars=500)
    references = "; ".join(ref.citation() for ref in refs[:6])
    return f"""Use case: ads-marketing
Asset type: LinkedIn article thumbnail and feed preview image, 1200x627 landscape
Primary request: Create an eye-catching AI-generated editorial thumbnail for the article titled "{title}".
Scene/backdrop: a cinematic executive conference-room table at dawn, with a glowing AI workflow map, source cards, approval stamps, and a visible human decision gate.
Subject: the tension between fast AI capability and disciplined business approval.
Style/medium: polished photorealistic editorial image with subtle futuristic interface elements, similar quality to a premium LinkedIn thought-leadership article thumbnail.
Composition/framing: bold central metaphor, strong depth, clean negative space for title text in the upper-left third.
Text (verbatim): "{title.upper()}"
Context to reflect: {context}
Reference context used for the article: {references}
Constraints: no logos, no employer branding, no public figures, no religious symbols unless the article specifically requires them, no copyrighted source imagery, no watermark, no fake UI brand names.
Avoid: generic abstract blobs, unreadable tiny text, cartoon style, cluttered dashboards, vendor scorekeeping, hype aesthetics."""


def generate_article_package_from_topic(config: Config, topic_id: str) -> ArticlePackage:
    context = _topic_context(config, topic_id)
    topic = context["topic"]
    sources = context["sources"]
    refs = _reference_dossier(sources, limit=16)
    title = _bold_title(str(topic.get("title") or ""), str(topic.get("summary") or ""))
    thesis = "what must be true in the workflow before AI output is allowed to become action?"
    body = _article_body(title, topic, sources, refs)
    first_comment = (
        "Source note: I treated the first linked source as the article trigger, then used official frameworks and high-trust research to test the broader thesis. "
        f"Start with: {refs[0].url if refs else '[add primary source link]'}"
    )
    return ArticlePackage(
        title=title,
        feed_post=_feed_post(title, thesis),
        article_body=body,
        references=refs,
        sourcing_note=_sourcing_note(refs),
        first_comment=first_comment,
        image_prompt=_image_prompt(title, topic, refs),
        image_alt_text=f"Original illustration for '{title}' showing AI workflow controls, source review, and a human approval gate.",
    )
