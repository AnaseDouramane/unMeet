from dataclasses import replace
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import ApiDependencies, EmptyAnalyticsReadFacade
from app.config import settings as base_settings


class NoSearch:
    def search(self, query: str, limit: int):
        return ()


class Freshness:
    def __init__(self, rows):
        self.rows = tuple(rows)

    def latest_by_source(self):
        return self.rows


def _client(rows, stale_after=3600):
    app = create_app(
        ApiDependencies(
            analytics_reader=EmptyAnalyticsReadFacade(),
            semantic_search=NoSearch(),
            freshness_reader=Freshness(rows),
        ),
        settings=replace(base_settings, ingestion_stale_after_seconds=stale_after),
    )
    return TestClient(app)


def _ago(seconds):
    return datetime.now(UTC) - timedelta(seconds=seconds)


def test_ok_when_every_source_is_fresh() -> None:
    response = _client([("hackernews", _ago(60), 10), ("reddit", _ago(600), 5)]).get(
        "/health/ingestion"
    )
    body = response.json()
    assert response.status_code == 200 and body["status"] == "ok"
    assert [s["source"] for s in body["sources"]] == ["hackernews", "reddit"]
    assert not any(s["stale"] for s in body["sources"])


def test_503_and_the_stale_source_is_named_when_one_goes_quiet() -> None:
    response = _client([("hackernews", _ago(60), 10), ("reddit", _ago(7200), 5)]).get(
        "/health/ingestion"
    )
    body = response.json()
    assert response.status_code == 503 and body["status"] == "stale"
    stale = {s["source"]: s["stale"] for s in body["sources"]}
    assert stale == {"hackernews": False, "reddit": True}
    assert body["stale_after_seconds"] == 3600


def test_no_data_yet_is_not_a_stall() -> None:
    response = _client([]).get("/health/ingestion")
    assert response.status_code == 200 and response.json()["sources"] == []


def test_plain_health_still_works_and_is_not_rate_limited() -> None:
    client = _client([])
    assert all(client.get("/health").status_code == 200 for _ in range(300))
