from ai_linkedin_automation.scoring.scoring import SOURCE_CREDIBILITY


def score_source_trust(tier: str) -> int:
    return SOURCE_CREDIBILITY.get(tier, 1)
