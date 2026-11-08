"""Monthly LLM budget of a workspace, from the usage recorded for it."""

from __future__ import annotations

from datetime import UTC, datetime

from app.billing.plans import Plan
from app.usage.llm_usage import UsageTotals


def month_start(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(UTC)
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def spent_usd(totals: tuple[UsageTotals, ...]) -> float | None:
    """Money spent this month, or None when some usage has no price to count."""
    costs = [item.cost_usd for item in totals]
    if any(cost is None for cost in costs):
        return None
    return round(sum(c for c in costs if c is not None), 6)


def is_over_budget(plan: Plan, totals: tuple[UsageTotals, ...]) -> bool:
    """True when the known spend reached the plan's budget.

    With no prices configured the spend is unknown and nothing is blocked: configure
    LLM_INPUT_USD_PER_MTOK / LLM_OUTPUT_USD_PER_MTOK to enforce budgets.
    """
    spent = spent_usd(totals)
    return spent is not None and spent >= plan.llm_budget_usd
