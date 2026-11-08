"""Plan checks shared by every way a topic can be created (API and onboarding)."""

from __future__ import annotations

from app.api.dependencies import ApiDependencies
from app.api.errors import ApiError
from app.billing.plans import plan_for


def ensure_topic_capacity(
    dependencies: ApiDependencies, workspace_id: int, with_webhook: bool = False
) -> None:
    workspace = dependencies.tenancy.get_workspace(workspace_id)
    plan = plan_for(workspace.plan if workspace else "free")
    if dependencies.topic_store.count(workspace_id) >= plan.max_topics:
        raise ApiError(
            402,
            "plan_limit_reached",
            f"the {plan.name} plan allows {plan.max_topics} topic(s); upgrade to add more",
            {"limit": "topics", "plan": plan.name, "max": plan.max_topics},
        )
    if with_webhook and not plan.webhooks:
        raise ApiError(
            402,
            "plan_limit_reached",
            f"webhooks are not included in the {plan.name} plan",
            {"limit": "webhooks", "plan": plan.name},
        )
