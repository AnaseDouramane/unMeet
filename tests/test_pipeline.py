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


def test_pipeline_returns_prepared_documents(monkeypatch) -> None:
    monkeypatch.setattr("app.services.pipeline.HackerNewsConnector", FakeHackerNewsConnector)

    pipeline = Pipeline(settings=type("SettingsStub", (), {"environment": "test"})())
    prepared_documents = pipeline.run()

    assert len(prepared_documents) == 10
    assert [document.source_item.external_id for document in prepared_documents] == [
        str(index) for index in range(10)
    ]
    assert prepared_documents[0].title == "Title 0"
    assert prepared_documents[0].body == "Body 0"
    assert prepared_documents[0].document_text == "Title 0\n\nBody 0"
    assert prepared_documents[0].source_item.title == "<h1>Title 0</h1>"
    assert prepared_documents[0].source_item.body == "<p>Body 0</p>"
