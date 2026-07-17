from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.database.models import SourceItemModel
from app.database.repository import SourceItemRepository
from app.ingestion.schemas import SourceItem
from app.preprocessing.schemas import PreparedDocument


class FakeScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, scalar_results: list[object | None], scalars_results: list[list[object]] | None = None) -> None:
        self.scalar_results = scalar_results
        self.scalars_results = scalars_results or []
        self.scalars_statements = []
        self.added = []
        self.committed = 0
        self.rolled_back = 0
        self.refreshed = []
        self.closed = 0

    def scalar(self, statement):
        if not self.scalar_results:
            raise AssertionError(f"Unexpected scalar call: {statement}")
        return self.scalar_results.pop(0)

    def scalars(self, statement):
        self.scalars_statements.append(statement)
        if not self.scalars_results:
            raise AssertionError(f"Unexpected scalars call: {statement}")
        return FakeScalarResult(self.scalars_results.pop(0))

    def add(self, model):
        self.added.append(model)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def refresh(self, model):
        if getattr(model, "id", None) is None:
            model.id = 1
        self.refreshed.append(model)

    def close(self):
        self.closed += 1


class FakeSessionFactory:
    def __init__(self, sessions: list[FakeSession]) -> None:
        self.sessions = sessions

    def __call__(self) -> FakeSession:
        if not self.sessions:
            raise AssertionError("Unexpected session request")
        return self.sessions.pop(0)


class FailingSessionFactory:
    def __call__(self):
        raise AssertionError("Session should not be opened for invalid input")


def _build_source_item(external_id: str = "123") -> SourceItem:
    return SourceItem(
        external_id=external_id,
        source="hackernews",
        title="Hello <b>HN</b>",
        body="<p>Body <i>content</i></p>",
        url="https://example.com/article",
        author="alice",
        published_at=datetime.fromtimestamp(1_700_000_000, tz=timezone.utc),
        engagement_score=42,
        raw_payload={"id": 123, "type": "story"},
    )


def _build_prepared_document(source_item: SourceItem, dedup_hash: str = "abc123") -> PreparedDocument:
    return PreparedDocument(
        source_item=source_item,
        title="Hello HN",
        body="Body content",
        document_text="Hello HN\n\nBody content",
        dedup_hash=dedup_hash,
    )


def _build_embedding(value: float = 0.1) -> list[float]:
    return [value] * 384


def test_repository_saves_source_item_and_prepared_document_into_one_record() -> None:
    session = FakeSession([None])
    repository = SourceItemRepository(session_factory=FakeSessionFactory([session]))
    source_item = _build_source_item()
    prepared_document = _build_prepared_document(source_item)
    embedding = _build_embedding()

    saved = repository.save(source_item, prepared_document, embedding=embedding)

    assert saved.id == 1
    assert session.committed == 1
    assert session.closed == 1
    assert session.added == [saved]
    assert saved.external_id == source_item.external_id
    assert saved.source == source_item.source
    assert saved.raw_payload == source_item.raw_payload
    assert saved.title == source_item.title
    assert saved.clean_title == prepared_document.title
    assert saved.body == source_item.body
    assert saved.clean_body == prepared_document.body
    assert saved.document_text == prepared_document.document_text
    assert saved.embedding == embedding
    assert saved.dedup_hash == prepared_document.dedup_hash
    assert saved.url == source_item.url
    assert saved.author == source_item.author
    assert saved.published_at == source_item.published_at
    assert saved.engagement_score == source_item.engagement_score
    assert saved.processed_at is not None


def test_repository_updates_existing_record_by_source_and_external_id() -> None:
    existing = SourceItemModel()
    existing.id = 7
    session = FakeSession([existing])
    repository = SourceItemRepository(session_factory=FakeSessionFactory([session]))
    source_item = _build_source_item()
    prepared_document = _build_prepared_document(source_item)
    embedding = _build_embedding(0.2)

    saved = repository.save(source_item, prepared_document, embedding=embedding)

    assert saved is existing
    assert session.committed == 1
    assert session.closed == 1
    assert session.added == []
    assert existing.clean_title == prepared_document.title
    assert existing.clean_body == prepared_document.body
    assert existing.dedup_hash == prepared_document.dedup_hash
    assert existing.embedding == embedding


@pytest.mark.parametrize("invalid_embedding", [_build_embedding()[:383], _build_embedding() + [0.1]])
def test_repository_rejects_embeddings_with_invalid_length(invalid_embedding: list[float]) -> None:
    session = FakeSession([None])
    repository = SourceItemRepository(session_factory=FakeSessionFactory([session]))
    source_item = _build_source_item()
    prepared_document = _build_prepared_document(source_item)

    with pytest.raises(ValueError, match="exactly 384 values"):
        repository.save(source_item, prepared_document, embedding=invalid_embedding)

    assert session.rolled_back == 1
    assert session.closed == 1


@pytest.mark.parametrize("invalid_limit", [0, -1])
def test_find_similar_rejects_non_positive_limit(invalid_limit: int) -> None:
    repository = SourceItemRepository(session_factory=FailingSessionFactory())

    with pytest.raises(ValueError, match="limit must be positive"):
        repository.find_similar(_build_embedding(), limit=invalid_limit)


@pytest.mark.parametrize("invalid_embedding", [_build_embedding()[:383], _build_embedding() + [0.1]])
def test_find_similar_rejects_invalid_embedding_length(invalid_embedding: list[float]) -> None:
    repository = SourceItemRepository(session_factory=FailingSessionFactory())

    with pytest.raises(ValueError, match="exactly 384 values"):
        repository.find_similar(invalid_embedding)


def test_find_similar_orders_by_cosine_distance_and_excludes_null_embeddings() -> None:
    rows = [SourceItemModel(), SourceItemModel()]
    session = FakeSession([], scalars_results=[rows])
    repository = SourceItemRepository(session_factory=FakeSessionFactory([session]))
    embedding = _build_embedding(0.5)

    found = repository.find_similar(embedding, limit=5)

    assert found == rows
    assert session.closed == 1
    assert len(session.scalars_statements) == 1
    statement = session.scalars_statements[0]
    compiled_sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "source_items.embedding IS NOT NULL" in compiled_sql
    assert "source_items.embedding <=>" in compiled_sql
    assert statement._limit_clause.value == 5


def test_find_similar_returns_source_item_models_in_order() -> None:
    first = SourceItemModel()
    second = SourceItemModel()
    session = FakeSession([], scalars_results=[[second, first]])
    repository = SourceItemRepository(session_factory=FakeSessionFactory([session]))

    found = repository.find_similar(_build_embedding())

    assert found == [second, first]


def test_repository_keeps_distinct_records_for_same_dedup_hash() -> None:
    first_session = FakeSession([None])
    second_session = FakeSession([None])
    repository = SourceItemRepository(session_factory=FakeSessionFactory([first_session, second_session]))

    first_source_item = _build_source_item(external_id="123")
    first_prepared_document = _build_prepared_document(first_source_item, dedup_hash="shared-hash")
    second_source_item = _build_source_item(external_id="456")
    second_source_item.source = "stackexchange"
    second_prepared_document = _build_prepared_document(second_source_item, dedup_hash="shared-hash")

    first_saved = repository.save(first_source_item, first_prepared_document)
    second_saved = repository.save(second_source_item, second_prepared_document)

    assert first_saved is first_session.added[0]
    assert second_saved is second_session.added[0]
    assert first_saved is not second_saved
    assert first_saved.dedup_hash == "shared-hash"
    assert second_saved.dedup_hash == "shared-hash"
    assert first_session.committed == 1
    assert second_session.committed == 1
    assert first_session.closed == 1
    assert second_session.closed == 1


def test_repository_existence_checks_use_the_expected_lookup_paths() -> None:
    source_session = FakeSession([SourceItemModel()])
    hash_session = FakeSession([None])
    repository = SourceItemRepository(session_factory=FakeSessionFactory([source_session, hash_session]))

    assert repository.exists_by_source_and_external_id("hackernews", "123") is True
    assert repository.exists_by_dedup_hash("abc123") is False
    assert source_session.closed == 1
    assert hash_session.closed == 1
