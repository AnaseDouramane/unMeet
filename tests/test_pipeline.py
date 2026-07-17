from datetime import datetime, timezone

from app.ingestion.schemas import SourceItem
from app.services.pipeline import Pipeline


class FakeHackerNewsConnector:
    def __init__(self, limit: int = 10) -> None:
        self.limit = limit
        self.fetch_calls = 0

    def fetch(self):
        self.fetch_calls += 1
        for index in range(10):
            yield SourceItem(
                external_id=str(index),
                source="hackernews",
                title=f"<h1>Title {index}</h1>",
                body=f"<p>Body {index}</p>",
                url=f"https://example.com/{index}",
                author="alice",
                published_at=datetime.fromtimestamp(1_700_000_000 + index, tz=timezone.utc),
                engagement_score=index,
                raw_payload={"id": index, "type": "story"},
            )


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def encode(self, document_text: str) -> list[float]:
        self.calls.append(document_text)
        embedding_value = float(len(self.calls))
        return [embedding_value] * 384


class FakeRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[SourceItem, object, list[float] | None]] = []

    def save(self, source_item, prepared_document, embedding=None):
        self.saved.append((source_item, prepared_document, embedding))
        return prepared_document


def test_pipeline_returns_prepared_documents_and_passes_embeddings(monkeypatch) -> None:
    monkeypatch.setattr("app.services.pipeline.HackerNewsConnector", FakeHackerNewsConnector)

    repository = FakeRepository()
    embedding_service = FakeEmbeddingService()
    pipeline = Pipeline(
        settings=type("SettingsStub", (), {"environment": "test"})(),
        repository=repository,
        embedding_service=embedding_service,
    )
    prepared_documents = pipeline.run()

    assert len(prepared_documents) == 10
    assert len(repository.saved) == 10
    assert embedding_service.calls == [document.document_text for document in prepared_documents]
    assert [document.source_item.external_id for document in prepared_documents] == [
        str(index) for index in range(10)
    ]
    assert [saved[0].external_id for saved in repository.saved] == [str(index) for index in range(10)]
    assert [saved[1].document_text for saved in repository.saved] == embedding_service.calls
    assert [saved[2] for saved in repository.saved] == [
        [float(index + 1)] * 384 for index in range(10)
    ]
    assert prepared_documents[0].title == "Title 0"
    assert prepared_documents[0].body == "Body 0"
    assert prepared_documents[0].document_text == "Title 0\n\nBody 0"
    assert prepared_documents[0].source_item.title == "<h1>Title 0</h1>"
    assert prepared_documents[0].source_item.body == "<p>Body 0</p>"
    assert repository.saved[0][0].external_id == "0"
    assert repository.saved[0][1].dedup_hash == prepared_documents[0].dedup_hash
