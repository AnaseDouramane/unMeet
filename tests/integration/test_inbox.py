from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import SignalStateModel, TrackedTopicModel
from app.database.repository import SourceItemRepository
from app.inbox.repository import InboxRepository
from app.ingestion.schemas import SourceItem
from app.problem_detection.schemas import TopicMatch
from app.services.preprocessing import PreprocessingService
from app.tenancy.repository import TenancyRepository
from app.topics.repository import TopicRepository
from app.topics.schemas import TopicDefinition
from tests.integration.test_database import MODEL, _problem, _unit

BASE = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.fixture
def world(session_factory: sessionmaker[Session]):
    tenancy, topics = TenancyRepository(session_factory), TopicRepository(session_factory)
    acme, beta = (
        tenancy.create_workspace("Acme", "a@a.test").id,
        tenancy.create_workspace("Beta", "b@b.test").id,
    )
    crm = topics.create(TopicDefinition(name="CRM", description="crm"), acme)
    billing = topics.create(TopicDefinition(name="Billing", description="invoices"), acme)
    beta_topic = topics.create(TopicDefinition(name="CRM", description="crm"), beta)
    return {
        "acme": acme,
        "beta": beta,
        "crm": crm.id,
        "billing": billing.id,
        "beta_topic": beta_topic.id,
        "items": SourceItemRepository(session_factory),
        "inbox": InboxRepository(session_factory),
    }


def save(
    world,
    external_id: str,
    matches: list[tuple[int, str]],
    *,
    day: int = 1,
    quote=None,
    problem=True,
):
    item = SourceItem(
        external_id=external_id,
        source="reddit",
        title=f"Title {external_id}",
        body="body",
        url=f"https://example.test/{external_id}",
        author="u",
        published_at=BASE + timedelta(days=day),
        engagement_score=None,
        raw_payload={},
    )
    result = replace(
        _problem(),
        pain_quote=quote,
        topic_matches=tuple(TopicMatch(topic, reason) for topic, reason in matches),
    )
    saved = world["items"].save(item, PreprocessingService().prepare(item), _unit(1), MODEL, result)
    return saved.id


def test_inbox_only_shows_signals_matched_to_the_workspaces_topics(world) -> None:
    mine = save(world, "mine", [(world["crm"], "dupes")], day=2)
    save(world, "theirs", [(world["beta_topic"], "other tenant")], day=3)
    save(world, "unmatched", [], day=4)

    acme = world["inbox"].list_items(world["acme"])
    beta = world["inbox"].list_items(world["beta"])

    assert [i.signal_id for i in acme] == [mine]
    assert (acme[0].topic_name, acme[0].relevance_reason, acme[0].state) == ("CRM", "dupes", "new")
    assert [i.relevance_reason for i in beta] == ["other tenant"]
    assert world["inbox"].get_item(world["acme"], mine) is not None
    assert world["inbox"].get_item(world["beta"], mine) is None


def test_ordering_topic_filter_pagination_and_single_row_per_signal(world) -> None:
    old = save(world, "old", [(world["crm"], "a")], day=1)
    both = save(world, "both", [(world["billing"], "b"), (world["crm"], "c")], day=3)
    new = save(world, "new", [(world["billing"], "d")], day=5)
    inbox, acme = world["inbox"], world["acme"]

    assert [i.signal_id for i in inbox.list_items(acme)] == [new, both, old]
    assert [i.topic_name for i in inbox.list_items(acme)] == [
        "Billing",
        "CRM",
        "CRM",
    ]  # lowest topic id
    assert [i.signal_id for i in inbox.list_items(acme, topic_id=world["crm"])] == [both, old]
    assert [i.signal_id for i in inbox.list_items(acme, limit=1, offset=1)] == [both]
    with pytest.raises(ValueError):
        inbox.list_items(acme, state="bogus")


def test_non_problems_are_never_listed(world) -> None:
    save(world, "p", [(world["crm"], "x")])
    # A later reclassification as non-problem removes the item from the inbox.
    item = SourceItem(
        "p", "reddit", "Title p", "body", "https://example.test/p", "u", BASE, None, {}
    )
    from app.problem_detection.schemas import ProblemDetectionResult

    world["items"].save(
        item,
        PreprocessingService().prepare(item),
        problem_detection_result=ProblemDetectionResult(False, 0.9, "no", "c"),
    )
    assert world["inbox"].list_items(world["acme"]) == ()


def test_states_filter_counts_and_bulk_updates(world) -> None:
    a, b, c = (save(world, x, [(world["crm"], x)], day=i) for i, x in enumerate("abc", 1))
    inbox, acme = world["inbox"], world["acme"]
    assert inbox.counts(acme) == {"new": 3, "not_relevant": 0, "relevant": 0, "replied": 0}

    assert inbox.set_state(acme, [a, b], "relevant", note="  call them  ", user_id=None) == 2
    assert inbox.set_state(acme, [c], "not_relevant") == 1

    assert inbox.counts(acme) == {"new": 0, "not_relevant": 1, "relevant": 2, "replied": 0}
    assert [i.signal_id for i in inbox.list_items(acme, state="relevant")] == [b, a]
    assert inbox.list_items(acme, state="relevant")[0].note == "call them"
    assert len(inbox.list_items(acme, state="all")) == 3
    assert inbox.list_items(acme) == ()  # nothing is new any more

    assert inbox.set_state(acme, [a], "replied") == 1
    assert inbox.get_item(acme, a).state == "replied"
    assert inbox.set_state(acme, [a, b], "new") == 2  # clears the decision
    assert inbox.counts(acme)["new"] == 2


def test_signals_outside_the_inbox_are_skipped_and_never_created(world, session_factory) -> None:
    foreign = save(world, "foreign", [(world["beta_topic"], "x")])
    unmatched = save(world, "unmatched", [])

    assert world["inbox"].set_state(world["acme"], [foreign, unmatched, 999], "relevant") == 0
    with session_factory() as session:
        assert session.scalars(select(SignalStateModel)).all() == []


def test_state_validation(world) -> None:
    inbox, acme = world["inbox"], world["acme"]
    with pytest.raises(ValueError):
        inbox.set_state(acme, [1], "maybe")
    with pytest.raises(ValueError):
        inbox.set_state(acme, [], "relevant")
    with pytest.raises(ValueError):
        inbox.set_state(acme, list(range(1, 202)), "relevant")


def test_states_are_per_workspace(world) -> None:
    shared = save(world, "shared", [(world["crm"], "a"), (world["beta_topic"], "b")])
    world["inbox"].set_state(world["acme"], [shared], "not_relevant")

    assert world["inbox"].get_item(world["acme"], shared).state == "not_relevant"
    assert world["inbox"].get_item(world["beta"], shared).state == "new"


def test_feedback_becomes_examples_for_that_topic_only(world) -> None:
    inbox, acme = world["inbox"], world["acme"]
    good = [
        save(world, f"g{i}", [(world["crm"], "r")], day=i, quote=f"good quote {i}")
        for i in range(1, 5)
    ]
    bad = save(world, "bad", [(world["crm"], "r")], day=9, quote="noise quote")
    billing = save(world, "bill", [(world["billing"], "r")], day=9, quote="invoice quote")
    foreign = save(world, "foreign", [(world["beta_topic"], "r")], quote="other tenant quote")
    inbox.set_state(acme, good[:3], "relevant")
    inbox.set_state(acme, [good[3]], "replied")
    inbox.set_state(acme, [bad], "not_relevant")
    inbox.set_state(acme, [billing], "relevant")
    inbox.set_state(world["beta"], [foreign], "relevant")

    examples = inbox.feedback_examples(acme, world["crm"], per_label=3)

    positives = [e.text for e in examples if e.relevant]
    assert len(positives) == 3 and "good quote 4" in positives  # replied counts, newest first
    assert [e.text for e in examples if not e.relevant] == ["noise quote"]
    assert not any("invoice" in e.text or "other tenant" in e.text for e in examples)


def test_deleting_a_topic_removes_its_signals_from_the_inbox_and_keeps_the_state_row(
    world, session_factory
) -> None:
    sid = save(world, "s", [(world["crm"], "x")])
    world["inbox"].set_state(world["acme"], [sid], "relevant")

    with session_factory() as session:
        session.execute(delete(TrackedTopicModel).where(TrackedTopicModel.id == world["crm"]))
        session.commit()

    assert world["inbox"].list_items(world["acme"]) == ()
    with session_factory() as session:
        (row,) = session.scalars(select(SignalStateModel)).all()
        assert row.topic_id is None  # SET NULL, decision kept
