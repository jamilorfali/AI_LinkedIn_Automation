from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ProviderResult:
    text: str
    provider: str
    model: Optional[str] = None
    cost_estimate_usd: float = 0.0
    metadata: Optional[dict] = None


class LLMProvider(ABC):
    @abstractmethod
    def summarize(self, prompt: str) -> ProviderResult:
        raise NotImplementedError

    @abstractmethod
    def score_topic(self, prompt: str) -> ProviderResult:
        raise NotImplementedError

    @abstractmethod
    def draft_post(self, prompt: str) -> ProviderResult:
        raise NotImplementedError

    @abstractmethod
    def revise_post(self, prompt: str) -> ProviderResult:
        raise NotImplementedError
