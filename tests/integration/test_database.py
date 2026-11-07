from datetime import UTC, datetime

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.database.models  # noqa: F401
from app.database.base import Base
from app.database.repository import SourceItemRepository
from app.ingestion.schemas import SourceItem
from app.problem_detection.schemas import ProblemDetectionResult
from app.services.preprocessing import PreprocessingService

MODEL = "test-embedding-model"


def _item(external_id: str, title: str) -> SourceItem:
    return SourceItem(
        external_id=external_id,
        source="hackernews",
        title=title,
        body="",
        url=f"https://news.ycombinator.com/item?id={external_id}",
        author="alice",
        published_at=datetime(2026, 11, 1, tzinfo=UTC),
        engagement_score=3,
        raw_payload={"id": external_id},
    )


def _problem() -> ProblemDetectionResult:
    return ProblemDetectionResult(
        is_problem=True,
        confidence=0.9,
        reason="explicit pain point",
        classifier_name="test-classifier",
    )


def _unit(axis: int) -> list[float]:
    vector = [0.0] * 384
    vector[axis] = 1.0
    return vector


def test_migrations_match_the_orm_models(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert diff == []


def test_save_is_an_upsert_and_round_trips_embeddings(
    session_factory: sessionmaker[Session],
) -> None:
    repository = SourceItemRepository(session_factory)
    preprocessing = PreprocessingService()
    item = _item("1", "Invoices take hours to reconcile")

    repository.save(item, preprocessing.prepare(item), _unit(0), MODEL, _problem())
    edited = _item("1", "Invoices take a full day to reconcile")
    saved = repository.save(edited, preprocessing.prepare(edited), _unit(0), MODEL, _problem())

    assert saved.title == "Invoices take a full day to reconcile"
    assert saved.embedding is not None
    assert saved.embedding[0] == 1.0
    assert len(repository.find_all_with_embeddings(MODEL)) == 1


def test_find_similar_orders_by_cosine_distance_within_one_model(
    session_factory: sessionmaker[Session],
) -> None:
    repository = SourceItemRepository(session_factory)
    preprocessing = PreprocessingService()
    for external_id, axis in (("near", 0), ("far", 1)):
        item = _item(external_id, f"Problem {external_id}")
        repository.save(item, preprocessing.prepare(item), _unit(axis), MODEL, _problem())
    other = _item("other-model", "Problem in another vector space")
    repository.save(other, preprocessing.prepare(other), _unit(0), "another-model", _problem())

    results = repository.find_similar(_unit(0), MODEL, limit=5)

    assert [result.external_id for result in results] == ["near", "far"]


def test_signal_fields_are_persisted(session_factory: sessionmaker[Session]) -> None:
    repository = SourceItemRepository(session_factory)
    item = _item("signal", "HubSpot sequences keep landing in spam")
    result = ProblemDetectionResult(
        is_problem=True,
        confidence=0.95,
        reason="complaint about a named tool",
        classifier_name="test-classifier",
        intent="competitor_complaint",
        pain_quote="keep landing in spam",
        products_mentioned=("HubSpot",),
        severity=3,
    )

    saved = repository.save(item, PreprocessingService().prepare(item), _unit(2), MODEL, result)

    assert saved.signal_intent == "competitor_complaint"
    assert saved.pain_quote == "keep landing in spam"
    assert saved.products_mentioned == ("HubSpot",)
    assert saved.signal_severity == 3


def _save_signal(
    repository: SourceItemRepository,
    external_id: str,
    *,
    axis: int,
    intent: str = "pain_point",
    products: tuple[str, ...] = (),
    severity: int = 2,
    day: int = 1,
    source: str = "hackernews",
) -> None:
    item = SourceItem(
        external_id=external_id,
        source=source,
        title=f"Signal {external_id}",
        body="",
        url=f"https://example.test/{external_id}",
        author="carol",
        published_at=datetime(2026, 11, day, tzinfo=UTC),
        engagement_score=None,
        raw_payload=None,
    )
    result = ProblemDetectionResult(
        is_problem=True,
        confidence=0.8,
        reason="test",
        classifier_name="test-classifier",
        intent=intent,  # type: ignore[arg-type]
        pain_quote=f"quote {external_id}",
        products_mentioned=products,
        severity=severity,
    )
    repository.save(item, PreprocessingService().prepare(item), _unit(axis), MODEL, result)


def test_find_signals_filters_by_intent_product_severity_and_date(
    session_factory: sessionmaker[Session],
) -> None:
    from app.signals.schemas import SignalQuery

    repository = SourceItemRepository(session_factory)
    _save_signal(repository, "a", axis=0, intent="competitor_complaint", products=("HubSpot",), day=3)
    _save_signal(repository, "b", axis=0, intent="pain_point", products=("Salesforce",), day=4)
    _save_signal(repository, "c", axis=0, intent="competitor_complaint", products=("hubspot",), severity=1, day=5)
    _save_signal(repository, "d", axis=0, intent="solution_search", day=6, source="reddit")

    def ids(**filters) -> list[str]:
        return [s.external_id for s in repository.find_signals(SignalQuery(**filters))]

    assert ids() == ["d", "c", "b", "a"]
    assert ids(intents=("competitor_complaint",)) == ["c", "a"]
    assert ids(products=("HUBSPOT",)) == ["c", "a"]
    assert ids(products=("HubSpot",), min_severity=2) == ["a"]
    assert ids(sources=("reddit",)) == ["d"]
    assert ids(published_since=datetime(2026, 11, 5, tzinfo=UTC)) == ["d", "c"]
    assert ids(limit=2, offset=1) == ["c", "b"]


def test_find_signals_by_topic_embedding_orders_by_similarity_with_threshold(
    session_factory: sessionmaker[Session],
) -> None:
    from app.signals.schemas import SignalQuery

    repository = SourceItemRepository(session_factory)
    _save_signal(repository, "exact", axis=0)
    _save_signal(repository, "orthogonal", axis=1)
    near = [0.0] * 384
    near[0], near[1] = 0.8, 0.6

    signals = repository.find_signals(
        SignalQuery(query_embedding=near, embedding_model=MODEL, max_distance=0.5)
    )

    assert [s.external_id for s in signals] == ["exact", "orthogonal"]
    assert signals[0].similarity == 0.8
    assert signals[0].pain_quote == "quote exact"
    strict = repository.find_signals(
        SignalQuery(query_embedding=near, embedding_model=MODEL, max_distance=0.3)
    )
    assert [s.external_id for s in strict] == ["exact"]


def test_product_filter_tolerates_legacy_json_null_rows(
    session_factory: sessionmaker[Session],
) -> None:
    from sqlalchemy import text

    from app.signals.schemas import SignalQuery

    repository = SourceItemRepository(session_factory)
    _save_signal(repository, "legacy", axis=0)
    _save_signal(repository, "tagged", axis=0, products=("Notion",))
    with session_factory() as session:
        session.execute(
            text("UPDATE source_items SET products_mentioned = 'null'::jsonb WHERE external_id = 'legacy'")
        )
        session.commit()

    signals = repository.find_signals(SignalQuery(products=("notion",)))

    assert [s.external_id for s in signals] == ["tagged"]
