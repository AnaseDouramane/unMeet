import csv
import io
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import ApiDependencies, EmptyAnalyticsReadFacade
from app.signals.schemas import Signal, SignalQuery
from app.signals.service import RepositorySignalReader, signals_to_csv


def _signal(**overrides) -> Signal:
    values = {
        "id": 7,
        "source": "hackernews",
        "external_id": "123",
        "title": "Re: Ask HN: How do you clean CRM data?",
        "url": "https://news.ycombinator.com/item?id=123",
        "author": "dana",
        "published_at": datetime(2026, 11, 2, 9, 30, tzinfo=UTC),
        "intent": "competitor_complaint",
        "pain_quote": "HubSpot dedupe misses half our duplicates",
        "products_mentioned": ("HubSpot",),
        "severity": 2,
        "confidence": 0.91,
        "similarity": 0.83,
    }
    values.update(overrides)
    return Signal(**values)


class RecordingReader:
    def __init__(self, signals=()) -> None:
        self.signals = tuple(signals) or (_signal(),)
        self.calls: list[tuple[SignalQuery, str | None]] = []

    def find(self, query: SignalQuery, topic: str | None = None):
        self.calls.append((query, topic))
        return self.signals


class NoSearch:
    def search(self, query: str, limit: int):
        return ()


def _client(reader: RecordingReader) -> TestClient:
    return TestClient(
        create_app(
            ApiDependencies(
                analytics_reader=EmptyAnalyticsReadFacade(),
                semantic_search=NoSearch(),
                signal_reader=reader,
            )
        )
    )


def test_signals_endpoint_maps_filters_and_returns_items() -> None:
    reader = RecordingReader()

    response = _client(reader).get(
        "/api/v1/signals",
        params=[
            ("intent", "competitor_complaint"),
            ("intent", "solution_search"),
            ("product", " HubSpot "),
            ("source", "HackerNews"),
            ("min_severity", "2"),
            ("since", "2026-11-01"),
            ("topic", "duplicate contacts in the CRM"),
            ("limit", "20"),
            ("offset", "40"),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 20 and body["offset"] == 40
    assert body["items"][0]["pain_quote"] == "HubSpot dedupe misses half our duplicates"
    assert body["items"][0]["products_mentioned"] == ["HubSpot"]
    query, topic = reader.calls[0]
    assert query.intents == ("competitor_complaint", "solution_search")
    assert query.products == ("HubSpot",)
    assert query.sources == ("hackernews",)
    assert query.min_severity == 2
    assert query.published_since == datetime(2026, 11, 1, tzinfo=UTC)
    assert topic == "duplicate contacts in the CRM"


def test_signals_endpoint_rejects_invalid_parameters() -> None:
    client = _client(RecordingReader())

    assert client.get("/api/v1/signals", params={"intent": "rant"}).status_code == 422
    assert client.get("/api/v1/signals", params={"min_severity": 4}).status_code == 422
    assert client.get("/api/v1/signals", params={"limit": 501}).status_code == 422


def test_csv_export_has_header_rows_and_attachment_disposition() -> None:
    response = _client(RecordingReader()).get("/api/v1/signals.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows[0]["pain_quote"] == "HubSpot dedupe misses half our duplicates"
    assert rows[0]["similarity"] == "0.830"


def test_csv_neutralises_formula_injection() -> None:
    text = signals_to_csv([_signal(pain_quote="=HYPERLINK(\"http://evil\")", author="+cmd")])

    row = next(csv.DictReader(io.StringIO(text)))
    assert row["pain_quote"].startswith("'=")
    assert row["author"] == "'+cmd"


def test_reader_turns_topic_text_into_a_semantic_filter() -> None:
    class Encoder:
        model_name = "mini"

        def encode(self, document_text: str) -> list[float]:
            assert document_text == "crm duplicates"
            return [0.1] * 384

    class Repository:
        def __init__(self) -> None:
            self.queries: list[SignalQuery] = []

        def find_signals(self, query: SignalQuery):
            self.queries.append(query)
            return ()

    repository = Repository()
    RepositorySignalReader(Encoder(), repository).find(SignalQuery(limit=5), "  crm duplicates ")
    RepositorySignalReader(Encoder(), repository).find(SignalQuery(limit=5), "   ")

    assert repository.queries[0].embedding_model == "mini"
    assert repository.queries[0].query_embedding == [0.1] * 384
    assert repository.queries[1].query_embedding is None
