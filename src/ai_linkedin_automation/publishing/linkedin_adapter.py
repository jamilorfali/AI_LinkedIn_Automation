from dataclasses import dataclass

from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.publishing.safety_gate import evaluate_live_publish_gate


@dataclass
class PublishResult:
    allowed: bool
    status: str
    reason: str


def publish_to_linkedin(draft_id: str) -> PublishResult:
    """Future LinkedIn adapter entry point. v0 never posts live."""
    config = load_config()
    gate = evaluate_live_publish_gate(config, draft_id)
    if not gate.allowed:
        return PublishResult(False, "blocked", gate.reason)
    raise NotImplementedError("LinkedIn publishing adapter is scaffolded but disabled in v0.")
