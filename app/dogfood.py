"""unMeet tracking itself: the first customers should come from the product.

These topics describe the people unMeet is for (founders and GTM teams who look for buyers in
public conversations by hand, or who are unhappy with keyword alert tools).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.tenancy.schemas import Workspace
from app.tenancy.store import TenancyStore
from app.topics.repository import DuplicateTopicError
from app.topics.schemas import TopicDefinition
from app.topics.store import TopicStore

WORKSPACE_NAME = "unMeet (dogfood)"

DOGFOOD_TOPICS: tuple[TopicDefinition, ...] = (
    TopicDefinition(
        name="Looking for a lead monitoring tool",
        description=(
            "people asking for a tool that finds leads, buyers or prospects by monitoring Reddit, "
            "Hacker News or online communities"
        ),
        intents=("solution_search",),
        products=("F5Bot", "Syften", "Octolens", "Common Room"),
        keywords=(
            "looking for a tool to find leads",
            "find customers on reddit",
            "monitor reddit for",
        ),
    ),
    TopicDefinition(
        name="Unhappy with keyword alerts",
        description=(
            "complaints that keyword alert or social listening tools send noisy, irrelevant mentions "
            "or miss people who are actually looking for a solution"
        ),
        intents=("competitor_complaint", "pain_point"),
        products=("F5Bot", "Syften", "Brand24", "Mention", "Google Alerts"),
        keywords=("keyword alerts are noisy", "alternative to f5bot", "alternative to syften"),
    ),
    TopicDefinition(
        name="Searching Reddit by hand for customers",
        description=(
            "founders or sales teams manually searching Reddit, Hacker News or forums every day to find "
            "people who need their product"
        ),
        intents=("pain_point",),
        keywords=(
            "searching reddit manually",
            "find my first customers",
            "where do you find customers",
        ),
    ),
    TopicDefinition(
        name="Affordable intent data for small teams",
        description=(
            "small B2B teams looking for an affordable alternative to expensive intent-data or "
            "community-signal platforms"
        ),
        intents=("solution_search", "competitor_complaint"),
        products=("Common Room", "Bombora", "6sense"),
        keywords=(
            "intent data for startups",
            "affordable intent data",
            "alternative to common room",
        ),
    ),
)


@dataclass(frozen=True)
class SeedResult:
    workspace: Workspace
    created_topics: tuple[str, ...]
    existing_topics: tuple[str, ...]


def seed_dogfood(tenancy: TenancyStore, topics: TopicStore, owner_email: str) -> SeedResult:
    """Create (or reuse) the dogfood workspace on the team plan and add its topics. Idempotent."""
    owner = tenancy.get_or_create_user(owner_email)
    workspace = next(
        (w for w, _ in tenancy.workspaces_for_user(owner.id) if w.name == WORKSPACE_NAME), None
    )
    if workspace is None:
        workspace = tenancy.create_workspace(WORKSPACE_NAME, owner_email)
    if workspace.plan != "team":
        workspace = tenancy.set_plan(workspace.id, "team")
    created: list[str] = []
    existing: list[str] = []
    for definition in DOGFOOD_TOPICS:
        try:
            topics.create(definition, workspace.id)
            created.append(definition.name)
        except DuplicateTopicError:
            existing.append(definition.name)
    return SeedResult(workspace, tuple(created), tuple(existing))
