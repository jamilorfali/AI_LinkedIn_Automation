from dataclasses import dataclass


@dataclass
class TopicScorecard:
    executive_relevance: int
    hidden_gem_value: int
    technical_signal: int
    source_credibility: int
    oracle_safe_fit: int
    draft_readiness: int
    political_risk: str
    recommendation: str
