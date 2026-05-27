from datetime import datetime

from ai_linkedin_automation.config import resolve_project_path
from ai_linkedin_automation.providers.base import LLMProvider, ProviderResult


class NoApiProvider(LLMProvider):
    """Hard Zero provider that writes prompt packets locally instead of calling a model."""

    def __init__(self, output_dir: str = "data/review_packets/current"):
        self.output_dir = resolve_project_path(output_dir)

    def _write_prompt(self, prompt: str, action: str) -> ProviderResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"{action}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        path.write_text(prompt)
        return ProviderResult(
            text=f"No API mode. Prompt packet written to {path}",
            provider="no_api",
            model=None,
            cost_estimate_usd=0.0,
            metadata={"prompt_path": str(path)},
        )

    def summarize(self, prompt: str) -> ProviderResult:
        return self._write_prompt(prompt, "summarize")

    def score_topic(self, prompt: str) -> ProviderResult:
        return self._write_prompt(prompt, "score_topic")

    def draft_post(self, prompt: str) -> ProviderResult:
        return self._write_prompt(prompt, "draft_post")

    def revise_post(self, prompt: str) -> ProviderResult:
        return self._write_prompt(prompt, "revise_post")
