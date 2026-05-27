from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ai_linkedin_automation.config import CONFIG_DIR, Config, load_yaml_file, resolve_project_path
from ai_linkedin_automation.scoring.scoring import top_topics


def load_weekly_config():
    """Load weekly package config from scoring.yaml."""
    scoring_file = CONFIG_DIR / "scoring.yaml"
    config = load_yaml_file(scoring_file)
    return config['weekly_package']


def _week_slug(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _target_week(week: str) -> str:
    if week == "current":
        return _week_slug(datetime.now())
    return week


def _scorecard_lines(topic: Dict[str, object]) -> str:
    return "\n".join(
        [
            f"- Executive relevance: {topic['executive_relevance']}/5",
            f"- Hidden gem value: {topic['hidden_gem_value']}/5",
            f"- Technical signal: {topic['technical_signal']}/5",
            f"- Source credibility: {topic['source_credibility']}/5",
            f"- Political risk: {str(topic['political_risk']).title()}",
            f"- Oracle-safe fit: {topic['oracle_safe_fit']}/5",
            f"- Draft readiness: {topic['draft_readiness']}/5",
            f"- Recommendation: {str(topic['recommendation']).replace('_', ' ').title()}",
        ]
    )


def _why_pick(topic: Dict[str, object]) -> str:
    if topic["recommendation"] == "draft_now":
        return (
            f"It combines strong executive relevance ({topic['executive_relevance']}/5), "
            f"hidden-gem value ({topic['hidden_gem_value']}/5), and source credibility "
            f"({topic['source_credibility']}/5). It also keeps political risk "
            f"{topic['political_risk']} and is ready for a short, practical draft."
        )
    return (
        f"It is the strongest available candidate this week, with political risk marked "
        f"{topic['political_risk']} and draft readiness at {topic['draft_readiness']}/5. "
        "It should still be reviewed carefully before becoming a public post."
    )


def _draft_starter(topic: Dict[str, object]) -> str:
    summary = topic.get("summary") or "This topic needs a short plain-English summary before posting."
    source_name = topic.get("source_name") or "the source"
    return f"""This caught my eye because it points to a practical AI question leaders are already facing.

{summary}

The useful part is not just the headline. It is what this says about how teams will evaluate, govern, and apply AI in real work. A source like {source_name} is enough to start the conversation, but the final post should stay modest and avoid overclaiming.

For leaders, the takeaway is simple: look for the operating change behind the AI news, not only the model or product announcement."""


def _source_note(topic: Dict[str, object]) -> str:
    return (
        f"{topic.get('source_name') or topic.get('source_id')} "
        f"({topic.get('trust_tier')}) - {topic.get('source_url')}"
    )


def _build_prompt_packet(topic: Dict[str, object]) -> str:
    return f"""# Draft this LinkedIn post

You are helping draft a weekly LinkedIn post for an AI and Emerging Technology Strategist.

## Voice

Write in a down-to-earth, warm, practical, non-hype style.
Use plain language.
Write for executives and technical audiences at the same time.
Keep it short unless the topic truly needs more.
Do not sound academic.
Do not sound like marketing.
Do not mention Oracle unless necessary.
Do not use partisan framing.
Do not compare vendors.
Avoid semicolon-heavy or dash-heavy structure.

## Length

Target 150 to 250 words.

## Topic

{topic['title']}

## What happened

{topic.get('summary') or 'Summarize the source in plain English.'}

## Why it matters

Translate the technical or market detail into a practical leadership implication.

## Hidden gem angle

Look for the overlooked operating, governance, or decision-quality implication.

## Sources

Use a subtle source mention in the post.

{_source_note(topic)}

## Claims you may make

- The source reported or published the finding above.
- This may matter for AI strategy, operations, governance, or technical investment decisions.

## Claims to avoid

- Do not say this changes everything.
- Do not imply inside information.
- Do not compare vendors.
- Do not make unsupported performance claims.

## Draft output required

Return:
1. LinkedIn post body.
2. Optional first comment.
3. Suggested image idea or carousel outline if helpful.
4. Short note explaining why the draft works.
"""


def generate_weekly_package(
    config: Config,
    week: str = "current",
    dry_run: bool = False,
) -> Optional[Tuple[str, str]]:
    """Generate the weekly briefing and no-API prompt packet."""
    weekly_config = load_weekly_config()
    max_findings = min(int(weekly_config.get("max_findings", 5)), 5)
    topics = top_topics(config, limit=max_findings)

    if dry_run:
        print(f"Would generate weekly package for {len(topics)} topics")
        for topic in topics[:3]:
            print(f"- {topic['title']} ({topic['recommendation']})")
        return None

    now = datetime.now()
    week_name = _target_week(week)
    output_dir = resolve_project_path(config.storage.review_packets_dir) / week_name
    output_dir.mkdir(parents=True, exist_ok=True)

    weekly_file = output_dir / "weekly_brief.md"
    prompt_file = output_dir / "recommended_winner_prompt_packet.md"

    recommended = topics[0] if topics else None
    lines: List[str] = [
        "# Weekly AI Thought Leadership Brief",
        "",
        f"Week: {week_name}",
        f"Prepared: {now.isoformat(timespec='minutes')}",
        f"Target: {config.publishing.target}",
        "Posting mode: Assisted manual posting",
        "",
        "## Recommended pick this week",
        "",
    ]

    if recommended:
        lines.extend(
            [
                f"**Topic:** {recommended['title']}",
                "",
                "**Why I would pick this one:**",
                _why_pick(recommended),
                "",
                "**Recommended format:**",
                "Text only first. Media requires separate approval.",
                "",
                "---",
                "",
                "# Top options",
                "",
            ]
        )
        for index, topic in enumerate(topics, start=1):
            lines.extend(
                [
                    f"## {index}. {topic['title']}",
                    "",
                    str(topic.get("summary") or "No summary available."),
                    "",
                    "Scorecard:",
                    _scorecard_lines(topic),
                    "",
                    "Source note:",
                    _source_note(topic),
                    "",
                    "Risk note:",
                    f"Political risk is {topic['political_risk']}; vendor comparison gate not triggered by the scorer.",
                    "",
                    "---",
                    "",
                ]
            )
        lines.extend(
            [
                "## Draft starter for recommended winner",
                "",
                _draft_starter(recommended),
                "",
                "---",
                "",
                "## Private source packet",
                "",
                _source_note(recommended),
                "",
                "---",
                "",
                "## Approval choices",
                "",
                "- Approve text only",
                "- Approve text plus media",
                "- Approve text, reject media",
                "- Needs edits",
                "- Pick different topic",
                "- Save for later",
                "- Reject",
                "",
            ]
        )
        prompt_file.write_text(_build_prompt_packet(recommended))
    else:
        lines.extend(
            [
                "No scored topic candidates are ready yet.",
                "",
                "Run ingestion, source loading, and scoring before building the weekly package.",
                "",
            ]
        )
        prompt_file.write_text("# Draft this LinkedIn post\n\nNo recommended topic is available yet.\n")

    weekly_file.write_text("\n".join(lines))
    return str(weekly_file), str(prompt_file)
