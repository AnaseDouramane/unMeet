"""Plans and their limits. Prices follow docs/NEXT_STEPS.md and are still to be tested."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    name: str
    monthly_price_eur: int
    max_topics: int
    max_seats: int
    llm_budget_usd: float  # monthly LLM spend we are willing to carry for the workspace
    webhooks: bool
    daily_digest: bool


PLANS: dict[str, Plan] = {
    "free": Plan(
        "free", 0, max_topics=1, max_seats=1, llm_budget_usd=1.0, webhooks=False, daily_digest=False
    ),
    "starter": Plan(
        "starter",
        49,
        max_topics=5,
        max_seats=3,
        llm_budget_usd=9.0,
        webhooks=False,
        daily_digest=True,
    ),
    "team": Plan(
        "team",
        149,
        max_topics=25,
        max_seats=10,
        llm_budget_usd=29.0,
        webhooks=True,
        daily_digest=True,
    ),
}


class PlanLimitError(Exception):
    """An action would exceed what the workspace's plan allows."""

    def __init__(self, limit: str, plan: str, message: str) -> None:
        super().__init__(message)
        self.limit = limit
        self.plan = plan
        self.message = message


def plan_for(name: str) -> Plan:
    try:
        return PLANS[name]
    except KeyError as error:
        raise ValueError(f"unknown plan {name!r}") from error
