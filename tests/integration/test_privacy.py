from dataclasses import replace
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import SignalTopicMatchModel, SourceItemModel
from app.database.repository import SourceItemRepository
from app.ingestion.schemas import SourceItem
from app.privacy.service import ErasureFilter, PrivacyRepository, author_key
from app.problem_detection.schemas import ProblemDetectionResult, TopicMatch
from app.services.preprocessing import PreprocessingService
from app.topics.repository import TopicRepository
from app.topics.schemas import TopicDefinition
from tests.integration.test_database import MODEL, _problem, _unit


def _save(repository, external_id, author, *, source="reddit", problem=True, matches=()):
    item = SourceItem(
        external_id=external_id,
        source=source,
        title=f"T{external_id}",
        body="body",
        url=f"https://example.test/{external_id}",
        author=author,
        published_at=datetime(2026, 11, 1, tzinfo=UTC),
        engagement_score=None,
        raw_payload={},
    )
    result = (
        replace(_problem(), topic_matches=tuple(matches))
        if problem
        else ProblemDetectionResult(False, 0.9, "no", "c")
    )
    return repository.save(
        item,
        PreprocessingService().prepare(item),
        _unit(1) if problem else None,
        MODEL if problem else None,
        result,
    )


def _ids(session_factory) -> set[str]:
    with session_factory() as session:
        return set(session.scalars(select(SourceItemModel.external_id)))


def test_erasing_an_author_deletes_their_items_everywhere_and_suppresses_them(
    session_factory: sessionmaker[Session],
) -> None:
    topic = TopicRepository(session_factory).create(TopicDefinition(name="CRM", description="crm"))
    items = SourceItemRepository(session_factory)
    _save(items, "1", "Alice", matches=[TopicMatch(topic.id, "why")])
    _save(items, "2", "alice", problem=False)  # case-insensitive
    _save(items, "3", "bob")
    _save(items, "4", "alice", source="hackernews")  # other source is untouched
    privacy = PrivacyRepository(session_factory)

    assert privacy.erase_author("Reddit", " ALICE ") == 2

    assert _ids(session_factory) == {"3", "4"}
    with session_factory() as session:
        assert session.scalars(select(SignalTopicMatchModel)).all() == []  # cascaded
    assert privacy.suppressed_authors("reddit") == frozenset({author_key("alice")})
    assert privacy.suppressed_authors("hackernews") == frozenset()
    assert privacy.erase_author("reddit", "alice") == 0  # idempotent


def test_erasure_filter_checks_the_hash_not_the_name(
    session_factory: sessionmaker[Session],
) -> None:
    privacy = PrivacyRepository(session_factory)
    privacy.erase_author("reddit", "Alice")
    filtering = ErasureFilter(privacy)

    assert filtering.is_suppressed("reddit", "alice")
    assert not filtering.is_suppressed("reddit", "bob")
    assert not filtering.is_suppressed("hackernews", "alice")
    assert not filtering.is_suppressed("reddit", None)
    from app.database.models import ErasureRequestModel

    with session_factory() as session:
        stored = session.scalars(select(ErasureRequestModel.author_key)).all()
    assert stored == [author_key("alice")] and "alice" not in stored[0]


def test_retention_deletes_non_signals_before_signals(
    session_factory: sessionmaker[Session],
) -> None:
    items = SourceItemRepository(session_factory)
    _save(items, "old-signal", "a")
    _save(items, "old-other", "b", problem=False)
    _save(items, "fresh-other", "c", problem=False)
    _save(items, "very-old-signal", "d")
    now = datetime(2026, 12, 1, tzinfo=UTC)
    ages = {"old-signal": 100, "old-other": 40, "fresh-other": 5, "very-old-signal": 400}
    with session_factory() as session:
        for external_id, days in ages.items():
            session.execute(
                update(SourceItemModel)
                .where(SourceItemModel.external_id == external_id)
                .values(processed_at=now - timedelta(days=days))
            )
        session.commit()

    result = PrivacyRepository(session_factory).enforce_retention(30, 365, now=now)

    assert (result.non_signals_deleted, result.signals_deleted) == (1, 1)
    assert _ids(session_factory) == {"old-signal", "fresh-other"}
