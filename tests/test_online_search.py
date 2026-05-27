import json
from urllib.parse import urlparse

from ai_linkedin_automation.online_search import search_public_ai_sources


def _html_results(urls: list[str]) -> str:
    links = "\n".join(
        f'<a rel="nofollow" href="{url}">Agentic AI evidence source {index}</a>'
        for index, url in enumerate(urls, start=1)
    )
    return f"<html><body>{links}</body></html>"


def _rss_results(urls: list[str]) -> str:
    items = "\n".join(
        f"""
        <item>
          <title>AI governance news source {index}</title>
          <link>{url}</link>
          <description>Public reporting on AI governance, agentic systems, and enterprise workflow controls.</description>
          <pubDate>Wed, 27 May 2026 12:00:00 GMT</pubDate>
          <source>{urlparse(url).netloc}</source>
        </item>
        """
        for index, url in enumerate(urls, start=1)
    )
    return f"<?xml version='1.0'?><rss><channel>{items}</channel></rss>"


def _fixture_fetcher(url: str) -> str:
    if "lite.duckduckgo.com" in url:
        return _html_results(
            [
                "//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.example.com%2Fagentic-ai-enterprise-governance",
                "https://www.nist.gov/itl/ai-risk-management-framework",
                "https://www.linkedin.com/posts/not-allowed",
                "https://www.mckinsey.com/capabilities/quantumblack/our-insights/ai-controls",
            ]
        )
    if "html.duckduckgo.com" in url:
        return _html_results(
            [
                "https://hai.stanford.edu/news/agentic-ai-governance",
                "https://news.mit.edu/2026/agentic-ai-workflows",
                "https://www.oecd.org/artificial-intelligence/ai-principles/",
            ]
        )
    if "www.bing.com/search" in url:
        return _html_results(
            [
                "https://www.brookings.edu/articles/ai-governance-operating-models/",
                "https://www.iso.org/artificial-intelligence/management-systems",
                "https://www.example.org/ai-automation-controls",
            ]
        )
    if "www.bing.com/news/search" in url:
        return _rss_results(
            [
                "https://news.example.com/enterprise-ai-agent-controls",
                "https://tech.example.com/ai-workflow-risk",
            ]
        )
    if "news.google.com/rss/search" in url:
        return _rss_results(
            [
                "https://www.weforum.org/stories/2026/05/ai-agents-enterprise-governance/",
                "https://www.pewresearch.org/internet/2026/05/01/public-trust-ai-agents/",
            ]
        )
    if "export.arxiv.org" in url:
        return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://arxiv.org/abs/2605.12345</id>
    <title>Agentic AI Governance for Enterprise Workflows</title>
    <summary>This paper studies AI agent controls, source evidence, and human review gates.</summary>
    <published>2026-05-20T00:00:00Z</published>
  </entry>
</feed>"""
    if "semanticscholar.org" in url:
        return json.dumps(
            {
                "data": [
                    {
                        "title": "AI Agents and Decision Accountability",
                        "abstract": "A study of AI agents, accountability, and enterprise review.",
                        "year": 2026,
                        "venue": "Conference on AI Governance",
                        "externalIds": {"DOI": "10.5555/agentic-ai"},
                    }
                ]
            }
        )
    if "crossref.org" in url:
        return json.dumps(
            {
                "message": {
                    "items": [
                        {
                            "title": ["Enterprise AI Workflow Governance"],
                            "abstract": "<jats:p>Research on AI workflow governance.</jats:p>",
                            "DOI": "10.5555/workflow-governance",
                            "publisher": "Example University Press",
                            "container-title": ["Journal of AI Operations"],
                            "issued": {"date-parts": [[2026, 5, 1]]},
                            "type": "journal-article",
                        }
                    ]
                }
            }
        )
    if "gdeltproject.org" in url:
        return json.dumps(
            {
                "articles": [
                    {
                        "title": "Companies rethink AI automation controls",
                        "url": "https://example.org/ai-automation-controls",
                        "domain": "example.org",
                        "seendate": "20260520T120000Z",
                    },
                    {
                        "title": "Social result should be filtered",
                        "url": "https://www.linkedin.com/posts/not-allowed",
                        "domain": "linkedin.com",
                    },
                ]
            }
        )
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        title = parsed.path.strip("/").replace("-", " ").title() or parsed.netloc
        return f"""
<html>
  <head>
    <title>{title}</title>
    <meta name="description" content="A public article about AI governance controls, agentic workflow risk, and enterprise adoption.">
  </head>
</html>
"""
    raise AssertionError(f"Unexpected URL: {url}")


def test_search_public_ai_sources_returns_real_url_bearing_results():
    report = search_public_ai_sources(
        "agentic AI workflow governance",
        limit=16,
        fetcher=_fixture_fetcher,
    )

    assert report.query == "agentic AI workflow governance"
    assert len(report.searched_urls) == 9
    assert len(report.results) >= 10
    assert report.results[0].url.startswith("https://")
    assert "linkedin.com" not in {result.url for result in report.results}
    assert {result.provider for result in report.results} >= {
        "DuckDuckGo Web",
        "DuckDuckGo HTML",
        "Bing Web",
        "Bing News",
        "Google News",
        "arXiv",
        "Semantic Scholar",
        "Crossref",
    }
    assert {result.trust_tier for result in report.results} >= {"primary", "high_trust"}
    assert any(
        "A public article about AI governance controls" in result.summary
        for result in report.results
    )


def test_search_public_ai_sources_reports_provider_errors_without_hallucinating():
    report = search_public_ai_sources(
        "nonexistent query",
        fetcher=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    assert report.results == []
    assert len(report.provider_errors) == 9
