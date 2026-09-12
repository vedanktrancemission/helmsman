"""Token and cost accounting for a single run."""
from __future__ import annotations

from dataclasses import dataclass, field

# USD per 1K tokens, (prompt, completion). Models absent here — including every
# OpenRouter ":free" id — are billed at zero.
PRICING: dict[str, tuple[float, float]] = {
    "fake": (0.0, 0.0),
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "claude-opus-5": (0.005, 0.025),
    "claude-sonnet-5": (0.002, 0.01),
    "claude-haiku-4-5": (0.001, 0.005),
}


def cost_for(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p, c = PRICING.get(model, (0.0, 0.0))
    return round((prompt_tokens / 1000) * p + (completion_tokens / 1000) * c, 6)


@dataclass
class UsageRecord:
    agent: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


@dataclass
class CostTracker:
    """Accumulates token usage and enforces the per-run token ceiling."""

    token_ceiling: int = 200_000
    records: list[UsageRecord] = field(default_factory=list)
    total_tokens: int = 0
    total_cost: float = 0.0

    def add(self, agent: str, model: str, prompt_tokens: int, completion_tokens: int) -> UsageRecord:
        rec = UsageRecord(
            agent=agent,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_for(model, prompt_tokens, completion_tokens),
        )
        self.records.append(rec)
        self.total_tokens += prompt_tokens + completion_tokens
        self.total_cost = round(self.total_cost + rec.cost_usd, 6)
        return rec

    def exceeded(self) -> bool:
        return self.total_tokens >= self.token_ceiling
