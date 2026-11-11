from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.inbox.repository import InboxRepository
from app.ingestion.runs import IngestionRun, IngestionRunRepository
from app.tenancy.repository import TenancyRepository
from app.topics.repository import TopicRepository
from app.topics.schemas import TopicDefinition
from tests.integration.test_inbox import save

T0 = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)


def test_runs_round_trip_newest_first(session_factory: sessionmaker[Session]) -> None:
    runs = IngestionRunRepository(session_factory)
    runs.record(IngestionRun("hn", T0 - timedelta(hours=1), T0, "ok", acquired=10, matched=1))
    runs.record(IngestionRun("hn", T0, T0 + timedelta(minutes=2), "error", error="429"))

    latest = runs.latest()
    assert [r.status for r in latest] == ["error", "ok"]
    assert latest[1].acquired == 10 and latest[1].matched == 1 and latest[0].error == "429"
    assert len(runs.latest(limit=1)) == 1


def test_a_workspace_sees_its_own_runs_and_the_shared_ones(
    session_factory: sessionmaker[Session],
) -> None:
    runs = IngestionRunRepository(session_factory)
    runs.record(IngestionRun("hn", T0, T0, "ok", acquired=1, workspace_id=1))
    runs.record(IngestionRun("hn", T0, T0, "ok", acquired=2, workspace_id=2))
    runs.record(IngestionRun("hn", T0, T0, "ok", acquired=3))

    assert sorted(r.acquired for r in runs.latest(workspace_id=1)) == [1, 3]
    assert runs.latest(workspace_id=1)[0].workspace_id in (1, None)
    assert sorted(r.acquired for r in runs.latest()) == [1, 2, 3]


def test_topic_counts_count_matched_problems_and_the_new_ones(
    session_factory: sessionmaker[Session],
) -> None:
    tenancy, topics = TenancyRepository(session_factory), TopicRepository(session_factory)
    acme = tenancy.create_workspace("Acme", "a@a.test").id
    crm = topics.create(TopicDefinition(name="CRM", description="crm"), acme).id
    empty = topics.create(TopicDefinition(name="Empty", description="e"), acme).id
    world = {
        "items": __import__(
            "app.database.repository", fromlist=["SourceItemRepository"]
        ).SourceItemRepository(session_factory)
    }
    first = save(world, "a", [(crm, "r")])
    save(world, "b", [(crm, "r")])
    inbox = InboxRepository(session_factory)
    inbox.set_state(acme, [first], "relevant")

    assert inbox.topic_counts(acme) == {crm: (2, 1), empty: (0, 0)}
    other = tenancy.create_workspace("Other", "o@o.test").id
    assert inbox.topic_counts(other) == {}
