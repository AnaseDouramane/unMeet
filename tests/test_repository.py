from datetime import datetime, timezone

from app.database.models import SourceItemModel
from app.database.repository import SourceItemRepository
from app.ingestion.schemas import SourceItem
from app.preprocessing.schemas import PreparedDocument


class FakeSession:
    def __init__(self, scalar_results: list[object | None]) -> None:
        self.scalar_results = scalar_results
        self.added = []
        self.committed = 0
        self.rolled_back = 0
        self.refreshed = []
        self.closed = 0

    def scalar(self, statement):
        if not self.scalar_results:
            raise AssertionError(f"Unexpected scalar call: {statement}")
        return self.scalar_results.pop(0)

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


def test_repository_saves_source_item_and_prepared_document_into_one_record() -> None:
    session = FakeSession([None])
    repository = SourceItemRepository(session_factory=FakeSessionFactory([session]))
    source_item = _build_source_item()
    prepared_document = _build_prepared_document(source_item)

    saved = repository.save(source_item, prepared_document)

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

    saved = repository.save(source_item, prepared_document)

    assert saved is existing
    assert session.committed == 1
    assert session.closed == 1
    assert session.added == []
    assert existing.clean_title == prepared_document.title
    assert existing.clean_body == prepared_document.body
    assert existing.dedup_hash == prepared_document.dedup_hash


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
