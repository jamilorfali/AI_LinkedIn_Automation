import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from ai_linkedin_automation.config import Config, resolve_project_path


PUBLISHABLE_TIERS = {"primary", "high_trust"}

STOPWORDS = {
    "about",
    "after",
    "against",
    "again",
    "and",
    "are",
    "artificial",
    "but",
    "can",
    "for",
    "from",
    "has",
    "have",
    "how",
    "into",
    "its",
    "new",
    "not",
    "now",
    "the",
    "their",
    "this",
    "that",
    "with",
    "what",
    "when",
    "where",
    "will",
    "you",
}


def week_slug(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def target_week(week: str) -> str:
    if week == "current":
        return week_slug(datetime.now())
    return week


def intelligence_dir(config: Config, week: str) -> Path:
    output_dir = resolve_project_path(config.storage.review_packets_dir) / target_week(week) / "intelligence"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def tokenize(value: str) -> set[str]:
    tokens = set()
    for raw in re.findall(r"[a-zA-Z][a-zA-Z0-9]+", (value or "").lower()):
        token = raw[:-1] if raw.endswith("s") and len(raw) > 4 else raw
        if len(token) >= 3 and token not in STOPWORDS:
            tokens.add(token)
    return tokens


def domain_from_url(url: str | None) -> str:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def stable_id(prefix: str, *parts: object, length: int = 20) -> str:
    import hashlib

    digest = hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()[:length]
    return f"{prefix}_{digest}"

