from ai_linkedin_automation.scoring.scoring import _has_vendor_comparison


def has_vendor_scorekeeping(text: str) -> bool:
    return _has_vendor_comparison(text.lower())
