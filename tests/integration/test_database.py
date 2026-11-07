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
