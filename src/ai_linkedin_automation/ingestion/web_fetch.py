from dataclasses import dataclass

from ai_linkedin_automation.cost_guard import require_cost_allowed


@dataclass
class WebFetchResult:
    url: str
    title: str
    text_excerpt: str


def fetch_public_page_excerpt(url: str) -> WebFetchResult:
    """Respectful public web fetch placeholder for a later phase."""
    require_cost_allowed("public_web_fetch", "fetch_public_page", 0.0)
    raise NotImplementedError("Public web extraction is scaffolded but not implemented in v0.")
