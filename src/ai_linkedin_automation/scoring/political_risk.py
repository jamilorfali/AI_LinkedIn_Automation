from ai_linkedin_automation.scoring.scoring import _political_risk


def classify_political_risk(text: str) -> str:
    return _political_risk(text.lower())
