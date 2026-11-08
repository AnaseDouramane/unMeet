from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import SignalTopicMatchModel
from app.database.repository import SourceItemRepository
from app.problem_detection.schemas import ProblemDetectionResult, TopicMatch
from app.services.preprocessing import PreprocessingService
from app.signals.schemas import SignalQuery
from app.topics.repository import TopicRepository
from app.topics.schemas import TopicDefinition
from tests.integration.test_database import MODEL, _item, _problem, _unit


def _matches(session_factory: sessionmaker[Session]) -> dict[tuple[int, int], str]:
    with session_factory() as session:
        rows = session.scalars(select(SignalTopicMatchModel)).all()
        return {(row.source_item_id, row.topic_id): row.reason for row in rows}


def _topics(session_factory: sessionmaker[Session]) -> tuple[int, int]:
    from app.tenancy.repository import TenancyRepository

    workspace = TenancyRepository(session_factory).create_workspace("T", "t@t.example").id
    repository = TopicRepository(session_factory)
    first = repository.create(
        TopicDefinition(name="CRM hygiene", description="duplicate contacts"), workspace
    )
    second = repository.create(
        TopicDefinition(name="Billing", description="failed invoices"), workspace
    )
    return first.id, second.id


def _save(repository: SourceItemRepository, result: ProblemDetectionResult):
    item = _item("m1", "Duplicate contacts again")
    return repository.save(item, PreprocessingService().prepare(item), _unit(1), MODEL, result)


def test_matches_are_saved_and_replaced_on_reclassification(
    session_factory: sessionmaker[Session],
) -> None:
    crm, billing = _topics(session_factory)
    repository = SourceItemRepository(session_factory)

    saved = _save(
        repository,
        replace(
            _problem(),
            topic_matches=(TopicMatch(crm, "Cleans duplicates."), TopicMatch(billing, "Invoices.")),
        ),
    )
    assert _matches(session_factory) == {
        (saved.id, crm): "Cleans duplicates.",
        (saved.id, billing): "Invoices.",
    }

    _save(repository, replace(_problem(), topic_matches=(TopicMatch(crm, "Better reason."),)))
    assert _matches(session_factory) == {(saved.id, crm): "Better reason."}

    _save(repository, _problem())
    assert _matches(session_factory) == {}


def test_match_for_a_deleted_topic_is_skipped_not_fatal(
    session_factory: sessionmaker[Session],
) -> None:
    crm, _ = _topics(session_factory)
    saved = _save(
        SourceItemRepository(session_factory),
        replace(_problem(), topic_matches=(TopicMatch(crm, "ok"), TopicMatch(9999, "gone"))),
    )
    assert _matches(session_factory) == {(saved.id, crm): "ok"}


def test_deleting_a_topic_removes_its_matches(session_factory: sessionmaker[Session]) -> None:
    crm, billing = _topics(session_factory)
    saved = _save(
        SourceItemRepository(session_factory),
        replace(_problem(), topic_matches=(TopicMatch(crm, "a"), TopicMatch(billing, "b"))),
    )
    TopicRepository(session_factory).delete(crm)
    assert _matches(session_factory) == {(saved.id, billing): "b"}


def test_topic_feed_is_annotated_with_the_reason_for_that_topic_only(
    session_factory: sessionmaker[Session],
) -> None:
    crm, billing = _topics(session_factory)
    repository = SourceItemRepository(session_factory)
    _save(
        repository,
        replace(
            _problem(),
            topic_matches=(TopicMatch(crm, "Cleans duplicates."), TopicMatch(billing, "Invoices.")),
        ),
    )
    other = _item("m2", "Unrelated pain")
    repository.save(other, PreprocessingService().prepare(other), _unit(2), MODEL, _problem())

    plain = {s.external_id: s.relevance_reason for s in repository.find_signals(SignalQuery())}
    for_crm = {
        s.external_id: s.relevance_reason
        for s in repository.find_signals(SignalQuery(topic_id=crm))
    }
    for_billing = {
        s.external_id: s.relevance_reason
        for s in repository.find_signals(SignalQuery(topic_id=billing))
    }

    assert plain == {"m1": None, "m2": None}
    assert for_crm == {"m1": "Cleans duplicates.", "m2": None}
    assert for_billing == {"m1": "Invoices.", "m2": None}
    # Annotating must not duplicate or drop rows.
    assert len(repository.find_signals(SignalQuery(topic_id=crm))) == 2
