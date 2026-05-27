from ai_linkedin_automation.scoring.scoring import score_finding, load_scoring_config
from ai_linkedin_automation.scoring.scoring import build_scorecard
from ai_linkedin_automation.weekly.weekly import load_weekly_config

def test_load_scoring_config():
    config = load_scoring_config()
    assert 'scoring_rules' in config
    assert len(config['scoring_rules']) > 0

def test_score_finding():
    rules = [
        {'keywords': ['breakthrough'], 'score': 10, 'category': 'high_impact'},
        {'keywords': ['paper'], 'score': 8, 'category': 'academic'}
    ]
    
    score, category = score_finding("AI Breakthrough", "New paper", rules)
    assert score == 10
    assert category == 'high_impact'
    
    score, category = score_finding("Research Paper", "", rules)
    assert score == 8
    assert category == 'academic'
    
    score, category = score_finding("Regular news", "", rules)
    assert score == 0
    assert category == 'general'

def test_load_weekly_config():
    config = load_weekly_config()
    assert 'max_findings' in config
    assert 'min_score' in config
    assert 'categories' in config


def test_high_political_risk_rejected():
    scorecard = build_scorecard(
        "AI in election campaign strategy",
        "A partisan candidate story about culture war framing.",
        "primary",
    )
    assert scorecard.political_risk == "high"
    assert scorecard.recommendation == "reject"


def test_vendor_comparison_flagged():
    scorecard = build_scorecard(
        "OpenAI beats Anthropic in enterprise AI",
        "A vendor versus vendor comparison.",
        "primary",
    )
    assert scorecard.recommendation == "reject"
    assert scorecard.draft_readiness == 1


def test_social_signal_cannot_support_publishable_claim():
    scorecard = build_scorecard(
        "AI agent productivity idea",
        "A LinkedIn discussion claims a major breakthrough.",
        "social_signal_only",
    )
    assert scorecard.source_credibility == 1
    assert scorecard.recommendation in {"save_for_verification", "watch"}
    assert scorecard.draft_readiness <= 2
