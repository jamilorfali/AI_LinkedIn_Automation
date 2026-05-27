from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ai_linkedin_automation.config import CONFIG_DIR, load_yaml_file


BLOCKED_IN_HARD_ZERO = {
    "openai_api",
    "anthropic_api",
    "claude_api",
    "gemini_api",
    "google_sheets_api",
    "linkedin_api",
    "linkedin_api_publish",
    "media_generation_api",
    "microsoft_graph",
    "outlook_graph",
    "x_api",
    "paid_search_api",
    "github_actions_hosted",
}

ALLOWED_IN_HARD_ZERO = {
    "local_file",
    "public_rss",
    "public_web_fetch",
    "manual_link",
    "apps_script_webapp",
}


@dataclass
class CostDecision:
    allowed: bool
    reason: str
    provider: str
    action: str
    estimated_cost_usd: float = 0.0


def load_cost_guard_config(path: Optional[Path] = None) -> Dict[str, Any]:
    return load_yaml_file(path or CONFIG_DIR / "cost_guard.yaml")


def check_cost_allowed(
    provider: str,
    action: str,
    estimated_cost_usd: float = 0.0,
    cost_config: Optional[Dict[str, Any]] = None,
) -> CostDecision:
    """Decide whether a paid-capable operation is allowed."""
    config = cost_config or load_cost_guard_config()
    run_mode = config.get("run_mode", "hard_zero")

    if estimated_cost_usd > 0 and config.get("monthly_spend_cap_usd", 0) <= 0:
        return CostDecision(
            False,
            "Non-zero estimated cost is blocked while the monthly spend cap is $0.",
            provider,
            action,
            estimated_cost_usd,
        )

    if run_mode == "hard_zero":
        if provider in BLOCKED_IN_HARD_ZERO:
            return CostDecision(
                False,
                f"{provider} is blocked in Hard Zero Mode.",
                provider,
                action,
                estimated_cost_usd,
            )
        if provider not in ALLOWED_IN_HARD_ZERO:
            return CostDecision(
                False,
                f"{provider} is not on the Hard Zero Mode allowlist.",
                provider,
                action,
                estimated_cost_usd,
            )
        return CostDecision(True, "Allowed in Hard Zero Mode.", provider, action, estimated_cost_usd)

    if run_mode == "free_tier_plus_guardrails":
        free_tier = config.get("free_tier_plus_guardrails", {})
        if not free_tier.get("enabled", False):
            return CostDecision(False, "Free Tier Plus mode is not enabled.", provider, action)
        if estimated_cost_usd > free_tier.get("monthly_spend_cap_usd", 0):
            return CostDecision(False, "Estimated cost exceeds configured free-tier cap.", provider, action)
        return CostDecision(True, "Allowed by Free Tier Plus guardrails.", provider, action)

    if run_mode == "future_paid_mode":
        paid = config.get("future_paid_mode", {})
        if not paid.get("enabled", False):
            return CostDecision(False, "Future Paid Mode is not enabled.", provider, action)
        if paid.get("require_approval_before_first_paid_call", True):
            return CostDecision(False, "Paid provider use requires explicit human unlock.", provider, action)

    return CostDecision(False, f"Unsupported run mode: {run_mode}", provider, action, estimated_cost_usd)


def require_cost_allowed(provider: str, action: str, estimated_cost_usd: float = 0.0) -> None:
    decision = check_cost_allowed(provider, action, estimated_cost_usd)
    if not decision.allowed:
        raise RuntimeError(f"Cost Guard blocked {provider}:{action}. {decision.reason}")
