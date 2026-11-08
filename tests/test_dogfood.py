from app.dogfood import DOGFOOD_TOPICS, WORKSPACE_NAME, seed_dogfood
from app.tenancy.schemas import Role
from app.tenancy.store import InMemoryTenancyStore
from app.topics.store import InMemoryTopicStore


def test_seeding_creates_a_team_workspace_owned_by_the_given_email_with_every_topic() -> None:
    tenancy, topics = InMemoryTenancyStore(), InMemoryTopicStore()

    result = seed_dogfood(tenancy, topics, "Founder@UnMeet.test")

    assert result.workspace.name == WORKSPACE_NAME and result.workspace.plan == "team"
    (member,) = tenancy.list_members(result.workspace.id)
    assert (member.email, member.role) == ("founder@unmeet.test", Role.OWNER)
    assert len(result.created_topics) == len(DOGFOOD_TOPICS) and result.existing_topics == ()
    assert {t.name for t in topics.list(result.workspace.id)} == {d.name for d in DOGFOOD_TOPICS}


def test_seeding_twice_changes_nothing_and_reports_what_exists() -> None:
    tenancy, topics = InMemoryTenancyStore(), InMemoryTopicStore()
    first = seed_dogfood(tenancy, topics, "founder@unmeet.test")
    second = seed_dogfood(tenancy, topics, "founder@unmeet.test")

    assert second.workspace.id == first.workspace.id
    assert second.created_topics == () and len(second.existing_topics) == len(DOGFOOD_TOPICS)
    assert topics.count(first.workspace.id) == len(DOGFOOD_TOPICS)


def test_a_downgraded_dogfood_workspace_is_put_back_on_the_team_plan() -> None:
    tenancy, topics = InMemoryTenancyStore(), InMemoryTopicStore()
    workspace = seed_dogfood(tenancy, topics, "founder@unmeet.test").workspace
    tenancy.set_plan(workspace.id, "free")
    assert seed_dogfood(tenancy, topics, "founder@unmeet.test").workspace.plan == "team"


def test_topics_are_valid_and_describe_the_buyer_in_plain_language() -> None:
    names = [d.name for d in DOGFOOD_TOPICS]
    assert len(set(names)) == len(names)
    assert all(d.description and d.intents for d in DOGFOOD_TOPICS)  # validated by TopicDefinition
    assert any("solution_search" in d.intents for d in DOGFOOD_TOPICS)
    assert any(d.products for d in DOGFOOD_TOPICS)
