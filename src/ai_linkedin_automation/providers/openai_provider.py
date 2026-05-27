from ai_linkedin_automation.cost_guard import require_cost_allowed
from ai_linkedin_automation.providers.base import LLMProvider, ProviderResult


class OpenAIProvider(LLMProvider):
    """Future adapter. Disabled until the user explicitly unlocks paid-capable providers."""

    provider_category = "openai_api"

    def _blocked(self, action: str) -> ProviderResult:
        require_cost_allowed(self.provider_category, action, 0.0)
        raise NotImplementedError("OpenAI provider is scaffolded but disabled in v0.")

    def summarize(self, prompt: str) -> ProviderResult:
        return self._blocked("summarize")

    def score_topic(self, prompt: str) -> ProviderResult:
        return self._blocked("score_topic")

    def draft_post(self, prompt: str) -> ProviderResult:
        return self._blocked("draft_post")

    def revise_post(self, prompt: str) -> ProviderResult:
        return self._blocked("revise_post")
