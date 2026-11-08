from __future__ import annotations

from app.api.dependencies import ApiDependencies
from app.api.errors import ApiError
from app.billing.budget import is_over_budget, month_start, spent_usd
from app.billing.plans import plan_for


def ensure_llm_budget(dependencies: ApiDependencies, workspace_id: int) -> None:
    """Refuse an LLM-backed action once the workspace used its monthly budget."""
    workspace = dependencies.tenancy.get_workspace(workspace_id)
    plan = plan_for(workspace.plan if workspace else "free")
    totals = dependencies.usage_reader.totals(month_start(), workspace_id)
    if is_over_budget(plan, totals):
        raise ApiError(
            402,
            "llm_budget_exceeded",
            f"the {plan.name} plan's monthly AI budget is used up; upgrade or wait for next month",
            {"limit": "llm_budget_usd", "plan": plan.name, "spent_usd": spent_usd(totals)},
        )
