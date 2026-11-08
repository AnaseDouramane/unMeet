from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.tenancy.repository import TenancyRepository
from app.topics.repository import DuplicateTopicError, TopicRepository
from app.topics.schemas import TopicDefinition
from app.topics.store import InMemoryTopicStore


def test_topics_round_trip_and_names_are_unique_per_workspace(
    session_factory: sessionmaker[Session], workspace_id: int
) -> None:
    repository = TopicRepository(session_factory)
    created = repository.create(
        TopicDefinition(
            name="CRM hygiene",
            description="duplicate or stale contacts in the CRM",
            intents=("competitor_complaint", "solution_search"),
            products=("HubSpot", "Salesforce"),
            min_severity=2,
            webhook_url="https://api.clay.com/v3/sources/webhook/abc",
        ),
        workspace_id,
    )

    assert created.id > 0 and created.workspace_id == workspace_id
    assert created.created_at is not None
    assert repository.get(created.id) == created
    assert repository.list() == (created,)
    with pytest.raises(DuplicateTopicError):
        repository.create(
            TopicDefinition(name="CRM hygiene", products=("Pipedrive",)), workspace_id
        )


def test_mark_delivered_and_delete(
    session_factory: sessionmaker[Session], workspace_id: int
) -> None:
    repository = TopicRepository(session_factory)
    topic = repository.create(
        TopicDefinition(name="Outbound", intents=("solution_search",)), workspace_id
    )
    moment = datetime(2026, 11, 7, 12, tzinfo=UTC)

    repository.mark_delivered(topic.id, moment)

    reloaded = repository.get(topic.id)
    assert reloaded is not None and reloaded.last_delivered_at == moment
    assert repository.delete(topic.id) is True
    assert repository.delete(topic.id) is False
    assert repository.get(topic.id) is None


@pytest.fixture(params=["memory", "sql"])
def topic_store(request, session_factory):
    if request.param == "memory":
        return InMemoryTopicStore()
    return TopicRepository(session_factory)


@pytest.fixture
def two_workspaces(session_factory: sessionmaker[Session]) -> tuple[int, int]:
    tenancy = TenancyRepository(session_factory)
    return (
        tenancy.create_workspace("Acme", "a@acme.test").id,
        tenancy.create_workspace("Beta", "b@beta.test").id,
    )


def test_topics_are_isolated_between_workspaces(topic_store, two_workspaces, request) -> None:
    acme, beta = two_workspaces
    if request.node.callspec.params["topic_store"] == "memory":
        acme, beta = 1, 2
    mine = topic_store.create(TopicDefinition(name="CRM", description="crm"), acme)
    theirs = topic_store.create(
        TopicDefinition(name="CRM", description="crm"), beta
    )  # same name ok

    assert topic_store.list(acme) == (mine,)
    assert topic_store.list(beta) == (theirs,)
    assert len(topic_store.list()) == 2  # internal jobs see every workspace
    assert topic_store.count(acme) == 1

    # Another workspace cannot read or delete a topic by id.
    assert topic_store.get(mine.id, beta) is None
    assert topic_store.delete(mine.id, beta) is False
    assert topic_store.get(mine.id, acme) == mine
    assert topic_store.delete(mine.id, acme) is True
    assert topic_store.list(beta) == (theirs,)


def test_deleting_a_workspace_deletes_its_topics(
    session_factory: sessionmaker[Session], two_workspaces: tuple[int, int]
) -> None:
    from sqlalchemy import delete

    from app.database.models import WorkspaceModel

    acme, beta = two_workspaces
    repository = TopicRepository(session_factory)
    repository.create(TopicDefinition(name="A", description="a"), acme)
    kept = repository.create(TopicDefinition(name="B", description="b"), beta)

    with session_factory() as session:
        session.execute(delete(WorkspaceModel).where(WorkspaceModel.id == acme))
        session.commit()

    assert repository.list() == (kept,)
