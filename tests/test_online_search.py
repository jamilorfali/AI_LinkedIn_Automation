import json

from ai_linkedin_automation.online_search import search_public_ai_sources


def _fixture_fetcher(url: str) -> str:
    if "lite.duckduckgo.com" in url:
        return """
<html>
  <body>
    <a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.example.com%2Fagentic-ai-enterprise-governance">Agentic AI governance is changing enterprise workflows</a>
    <a rel="nofollow" href="https://www.nist.gov/itl/ai-risk-management-framework">NIST AI Risk Management Framework</a>
    <a rel="nofollow" href="https://www.linkedin.com/posts/not-allowed">LinkedIn result should be filtered</a>
  </body>
</html>
"""
    if "www.example.com" in url:
        return """
<html>
  <head>
    <title>Agentic AI governance is changing enterprise workflows</title>
    <meta name="description" content="A public article about AI governance controls, agentic workflow risk, and enterprise adoption.">
  </head>
</html>
"""
    if "nist.gov" in url:
        return """
<html>
  <head>
    <title>NIST AI Risk Management Framework</title>
    <meta property="og:description" content="NIST guidance for mapping, measuring, managing, and governing AI risk.">
  </head>
</html>
"""
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
    raise AssertionError(f"Unexpected URL: {url}")


def test_search_public_ai_sources_returns_real_url_bearing_results():
    report = search_public_ai_sources(
        "agentic AI workflow governance",
        limit=8,
        fetcher=_fixture_fetcher,
    )

    assert report.query == "agentic AI workflow governance"
    assert len(report.searched_urls) == 5
    assert len(report.results) == 6
    assert report.results[0].url.startswith("https://")
    assert "linkedin.com" not in {result.url for result in report.results}
    assert {result.provider for result in report.results} >= {
        "General Web Search",
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
    assert len(report.provider_errors) == 5
