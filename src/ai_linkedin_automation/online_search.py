from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from html import unescape
from typing import Callable, Iterable, List

from ai_linkedin_automation.cost_guard import require_cost_allowed
from ai_linkedin_automation.intelligence.common import tokenize


Fetcher = Callable[[str], str]


SOCIAL_HOSTS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "m.facebook.com",
    "t.co",
    "threads.net",
    "twitter.com",
    "x.com",
}


@dataclass(frozen=True)
class OnlineSearchResult:
    provider: str
    title: str
    summary: str
    url: str
    source_name: str
    trust_tier: str
    published_at: str = ""
    result_type: str = "article"


@dataclass
class OnlineSearchReport:
    query: str
    generated_at: str
    results: List[OnlineSearchResult]
    provider_errors: List[str] = field(default_factory=list)
    searched_urls: List[str] = field(default_factory=list)


def _default_fetch(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, application/atom+xml, text/xml;q=0.9, */*;q=0.8",
            "User-Agent": "AI-LinkedIn-Automation/0.1 public-web-fetch",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _clean_text(value: object, max_chars: int = 800) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "."


def _safe_query_terms(query: str) -> list[str]:
    return [token for token in sorted(tokenize(query)) if len(token) >= 3][:8]


def _host(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _is_allowed_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = _host(url)
    return bool(host) and not any(host == blocked or host.endswith(f".{blocked}") for blocked in SOCIAL_HOSTS)


def _unwrap_redirect_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    for key in ["uddg", "u", "url", "q"]:
        value = query.get(key, [""])[0]
        if value.startswith(("http://", "https://")):
            return urllib.parse.unquote(value)
    if url.startswith("//"):
        return "https:" + url
    return url


def _source_name_from_url(url: str) -> str:
    host = _host(url)
    if not host:
        return "Public web"
    parts = host.split(".")
    if len(parts) >= 2:
        label = parts[-2]
    else:
        label = parts[0]
    return label.replace("-", " ").replace("_", " ").title()


def _trust_tier_for_web_url(url: str) -> str:
    host = _host(url)
    if host.endswith((".gov", ".edu", ".mil")):
        return "high_trust"
    if any(
        marker in host
        for marker in [
            "acm.org",
            "brookings.edu",
            "ieee.org",
            "iso.org",
            "mckinsey.com",
            "mit.edu",
            "nist.gov",
            "oecd.org",
            "pewresearch.org",
            "stanford.edu",
            "weforum.org",
        ]
    ):
        return "high_trust"
    return "useful_but_verify"


def _relevance_score(result: OnlineSearchResult, query: str) -> int:
    haystack = tokenize(" ".join([result.title, result.summary, result.source_name, result.url]))
    query_tokens = set(_safe_query_terms(query))
    score = len(haystack & query_tokens) * 2
    ai_terms = {"agent", "agents", "ai", "artificial", "automation", "intelligence", "llm", "model"}
    score += len(haystack & ai_terms)
    if result.trust_tier in {"primary", "high_trust"}:
        score += 3
    return score


def _dedupe_and_rank(results: Iterable[OnlineSearchResult], query: str, limit: int) -> list[OnlineSearchResult]:
    by_url: dict[str, OnlineSearchResult] = {}
    for result in results:
        title = _clean_text(result.title, max_chars=180)
        summary = _clean_text(result.summary)
        url = str(result.url or "").strip()
        if not title or not _is_allowed_url(url):
            continue
        by_url.setdefault(
            url,
            OnlineSearchResult(
                provider=result.provider,
                title=title,
                summary=summary or title,
                url=url,
                source_name=_clean_text(result.source_name, max_chars=120) or result.provider,
                trust_tier=result.trust_tier,
                published_at=str(result.published_at or ""),
                result_type=result.result_type,
            ),
        )
    ranked = sorted(by_url.values(), key=lambda item: _relevance_score(item, query), reverse=True)
    return ranked[:limit]


def _general_web_url(query: str, limit: int) -> str:
    web_query = f"{query} AI artificial intelligence"
    return "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": web_query})


def _parse_duckduckgo_lite(text: str) -> list[OnlineSearchResult]:
    results: list[OnlineSearchResult] = []
    anchor_pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    for raw_url, raw_title in anchor_pattern.findall(text or ""):
        title = _clean_text(raw_title, max_chars=180)
        url = _unwrap_redirect_url(unescape(raw_url).strip())
        if not title or not _is_allowed_url(url):
            continue
        host = _host(url)
        if host in {"duckduckgo.com", "lite.duckduckgo.com"}:
            continue
        results.append(
            OnlineSearchResult(
                provider="General Web Search",
                title=title,
                summary=f"General web search result from {_source_name_from_url(url)}.",
                url=url,
                source_name=_source_name_from_url(url),
                trust_tier=_trust_tier_for_web_url(url),
                result_type="general_web_result",
            )
        )
    return results


def _arxiv_url(query: str, limit: int) -> str:
    terms = _safe_query_terms(query) or ["artificial", "intelligence"]
    search_query = " AND ".join(f"all:{term}" for term in terms)
    search_query = f"({search_query}) AND (cat:cs.AI OR cat:cs.CL OR cat:cs.LG)"
    return "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {
            "search_query": search_query,
            "start": 0,
            "max_results": min(limit, 10),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )


def _parse_arxiv(text: str) -> list[OnlineSearchResult]:
    root = ET.fromstring(text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results: list[OnlineSearchResult] = []
    for entry in root.findall("atom:entry", ns):
        title = _clean_text(entry.findtext("atom:title", default="", namespaces=ns), max_chars=180)
        summary = _clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
        url = entry.findtext("atom:id", default="", namespaces=ns)
        published = entry.findtext("atom:published", default="", namespaces=ns)
        if title and url:
            results.append(
                OnlineSearchResult(
                    provider="arXiv",
                    title=title,
                    summary=summary,
                    url=url,
                    source_name="arXiv",
                    trust_tier="primary",
                    published_at=published,
                    result_type="research_paper",
                )
            )
    return results


def _semantic_scholar_url(query: str, limit: int) -> str:
    return "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(
        {
            "query": f"{query} artificial intelligence",
            "limit": min(limit, 10),
            "fields": "title,abstract,year,url,venue,publicationDate,externalIds",
        }
    )


def _parse_semantic_scholar(text: str) -> list[OnlineSearchResult]:
    data = json.loads(text or "{}")
    results: list[OnlineSearchResult] = []
    for item in data.get("data", []) or []:
        title = _clean_text(item.get("title"), max_chars=180)
        external = item.get("externalIds") or {}
        doi = str(external.get("DOI") or "").strip()
        url = f"https://doi.org/{doi}" if doi else str(item.get("url") or "").strip()
        if not title or not url:
            continue
        venue = _clean_text(item.get("venue"), max_chars=120) or "Semantic Scholar"
        published = str(item.get("publicationDate") or item.get("year") or "")
        results.append(
            OnlineSearchResult(
                provider="Semantic Scholar",
                title=title,
                summary=_clean_text(item.get("abstract")),
                url=url,
                source_name=venue,
                trust_tier="high_trust",
                published_at=published,
                result_type="research_paper",
            )
        )
    return results


def _crossref_url(query: str, limit: int) -> str:
    return "https://api.crossref.org/works?" + urllib.parse.urlencode(
        {
            "query.bibliographic": f"{query} artificial intelligence",
            "rows": min(limit, 10),
            "sort": "published",
            "order": "desc",
            "select": "DOI,title,container-title,publisher,published-print,published-online,issued,URL,abstract,type",
        }
    )


def _date_parts(item: dict) -> str:
    for key in ["published-online", "published-print", "issued"]:
        parts = ((item.get(key) or {}).get("date-parts") or [[]])[0]
        if parts:
            return "-".join(str(part).zfill(2) for part in parts)
    return ""


def _parse_crossref(text: str) -> list[OnlineSearchResult]:
    data = json.loads(text or "{}")
    results: list[OnlineSearchResult] = []
    for item in (data.get("message") or {}).get("items", []) or []:
        title = _clean_text((item.get("title") or [""])[0], max_chars=180)
        doi = str(item.get("DOI") or "").strip()
        url = str(item.get("URL") or "").strip() or (f"https://doi.org/{doi}" if doi else "")
        if not title or not url:
            continue
        container = _clean_text((item.get("container-title") or [""])[0], max_chars=120)
        publisher = _clean_text(item.get("publisher"), max_chars=120)
        source_name = container or publisher or "Crossref"
        results.append(
            OnlineSearchResult(
                provider="Crossref",
                title=title,
                summary=_clean_text(item.get("abstract")),
                url=url,
                source_name=source_name,
                trust_tier="high_trust",
                published_at=_date_parts(item),
                result_type=str(item.get("type") or "published_work"),
            )
        )
    return results


def _gdelt_url(query: str, limit: int) -> str:
    gdelt_query = f'("{query}" OR "{query} AI") "artificial intelligence"'
    return "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(
        {
            "query": gdelt_query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": min(limit, 10),
            "sort": "hybridrel",
        }
    )


def _parse_gdelt(text: str) -> list[OnlineSearchResult]:
    data = json.loads(text or "{}")
    results: list[OnlineSearchResult] = []
    for article in data.get("articles", []) or []:
        url = str(article.get("url") or "").strip()
        title = _clean_text(article.get("title"), max_chars=180)
        if not title or not url:
            continue
        domain = _clean_text(article.get("domain"), max_chars=120) or _host(url) or "GDELT"
        seen = str(article.get("seendate") or article.get("publishedAt") or "")
        summary = f"Public web article indexed by GDELT from {domain}."
        results.append(
            OnlineSearchResult(
                provider="GDELT",
                title=title,
                summary=summary,
                url=url,
                source_name=domain,
                trust_tier="useful_but_verify",
                published_at=seen,
                result_type="public_web_article",
            )
        )
    return results


def _html_attr(pattern: str, html: str) -> str:
    match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
    return _clean_text(match.group(1), max_chars=800) if match else ""


def _extract_page_description(html: str) -> tuple[str, str]:
    description_patterns = [
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
    ]
    title = _html_attr(r"<title[^>]*>(.*?)</title>", html)
    for pattern in description_patterns:
        description = _html_attr(pattern, html)
        if description:
            return title, description
    return title, ""


def _enrich_public_web_articles(
    results: list[OnlineSearchResult],
    fetcher: Fetcher,
) -> list[OnlineSearchResult]:
    enriched: list[OnlineSearchResult] = []
    public_web_fetches = 0
    for result in results:
        if result.provider not in {"GDELT", "General Web Search"} or public_web_fetches >= 5:
            enriched.append(result)
            continue
        public_web_fetches += 1
        try:
            title, description = _extract_page_description(fetcher(result.url))
        except Exception:
            enriched.append(result)
            continue
        enriched.append(
            OnlineSearchResult(
                provider=result.provider,
                title=title or result.title,
                summary=description or result.summary,
                url=result.url,
                source_name=result.source_name,
                trust_tier=result.trust_tier,
                published_at=result.published_at,
                result_type=result.result_type,
            )
        )
    return enriched


PROVIDERS = [
    ("General Web Search", _general_web_url, _parse_duckduckgo_lite),
    ("arXiv", _arxiv_url, _parse_arxiv),
    ("Semantic Scholar", _semantic_scholar_url, _parse_semantic_scholar),
    ("Crossref", _crossref_url, _parse_crossref),
    ("GDELT", _gdelt_url, _parse_gdelt),
]


def search_public_ai_sources(
    query: str,
    limit: int = 12,
    fetcher: Fetcher | None = None,
) -> OnlineSearchReport:
    """Search the open web plus public research indexes for real URL-bearing AI source material."""
    cleaned_query = _clean_text(query, max_chars=180)
    if not cleaned_query:
        raise ValueError("Enter a topic to search.")
    require_cost_allowed("public_web_fetch", "online_topic_search", 0.0)

    fetch = fetcher or _default_fetch
    collected: list[OnlineSearchResult] = []
    errors: list[str] = []
    searched_urls: list[str] = []
    per_provider_limit = max(3, min(limit, 10))

    for provider, make_url, parser in PROVIDERS:
        url = make_url(cleaned_query, per_provider_limit)
        searched_urls.append(url)
        try:
            collected.extend(parser(fetch(url)))
        except Exception as exc:
            errors.append(f"{provider}: {exc}")

    enriched = _enrich_public_web_articles(collected, fetch)
    results = _dedupe_and_rank(enriched, cleaned_query, limit)
    return OnlineSearchReport(
        query=cleaned_query,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        results=results,
        provider_errors=errors,
        searched_urls=searched_urls,
    )
