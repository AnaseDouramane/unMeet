from typing import Any

import pytest
import requests

from app.config import Settings
from app.ingestion.cursors import InMemoryCursorStore
from app.ingestion.factory import build_configured_connectors, parse_search_specs
from app.ingestion.hackernews import HackerNewsConnector
from app.ingestion.hackernews_search import (
    ALGOLIA_URL,
    HackerNewsSearchConnector,
    HackerNewsSearchError,
    SearchSpec,
)
from app.services.pipeline import PipelineRunStats
from app.services.polling import PollingWorker

NOW = 1_762_560_000


def _comment(object_id: int, created: int, **overrides: Any) -> dict[str, Any]:
    hit = {
        "objectID": str(object_id),
        "created_at_i": created,
        "_tags": ["comment", "author_dana", f"story_{object_id}"],
        "author": "dana",
        "comment_text": f"I spend hours on duplicates {object_id}",
        "story_title": "Ask HN: How do you clean CRM data?",
        "story_id": 1,
    }
    hit.update(overrides)
    return hit


def _story(object_id: int, created: int, **overrides: Any) -> dict[str, Any]:
    hit = {
        "objectID": str(object_id),
        "created_at_i": created,
        "_tags": ["story", "ask_hn"],
        "author": "erin",
        "title": "Ask HN: Best tool for lead monitoring?",
        "story_text": "We track mentions by hand.",
        "url": None,
        "points": 12,
    }
    hit.update(overrides)
    return hit


class Response:
    def __init__(self, payload: Any, error: Exception | None = None) -> None:
        self._payload, self._error = payload, error

    def raise_for_status(self) -> None:
        if self._error:
            raise self._error

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class Session:
    def __init__(self, *pages: Any) -> None:
        self.pages = list(pages)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any], timeout: float) -> Response:
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        page = self.pages.pop(0)
        return page if isinstance(page, Response) else Response(page)


def _page(hits: list[dict[str, Any]], pages: int = 1) -> dict[str, Any]:
    return {"hits": hits, "nbPages": pages, "page": 0}


def _connector(session: Session, *searches: SearchSpec, **kwargs: Any) -> HackerNewsSearchConnector:
    return HackerNewsSearchConnector(
        list(searches) or [SearchSpec("comment")],
        session=session,
        clock_seconds=lambda: NOW,
        **kwargs,
    )


def test_maps_comments_and_stories_like_the_firebase_connector() -> None:
    session = Session(_page([_comment(10, NOW - 5), _story(11, NOW - 4)]))
    comment, story = list(_connector(session, SearchSpec("comment")).fetch())

    assert (comment.source, comment.external_id) == ("hackernews", "10")
    assert comment.title == "Re: Ask HN: How do you clean CRM data?"
    assert comment.body == "I spend hours on duplicates 10"
    assert comment.url == "https://news.ycombinator.com/item?id=10"
    assert comment.engagement_score is None
    assert story.title == "Ask HN: Best tool for lead monitoring?"
    assert story.body == "We track mentions by hand."
    assert story.url == "https://news.ycombinator.com/item?id=11"
    assert story.engagement_score == 12


def test_first_run_looks_back_a_bounded_window_and_sends_the_query() -> None:
    session = Session(_page([]))
    list(
        _connector(
            session, SearchSpec("comment", "duplicate contacts"), lookback_seconds=600
        ).fetch()
    )

    call = session.calls[0]
    assert call["url"] == ALGOLIA_URL
    assert call["params"]["tags"] == "comment"
    assert call["params"]["query"] == "duplicate contacts"
    assert call["params"]["numericFilters"] == f"created_at_i>{NOW - 600}"


def test_cursor_filters_the_request_and_advances_to_the_newest_item() -> None:
    session = Session(_page([_comment(12, 2000), _comment(11, 1500)]))
    connector = _connector(session, SearchSpec("comment"))
    connector.load_cursors(InMemoryCursorStore({"hackernews_search:comment:*": "1000"}))

    assert [i.external_id for i in connector.fetch()] == ["12", "11"]
    assert session.calls[0]["params"]["numericFilters"] == "created_at_i>1000"
    assert connector.pending_cursors() == {"hackernews_search:comment:*": "2000"}


def test_paginates_until_the_last_page() -> None:
    session = Session(_page([_comment(3, 30)], pages=2), _page([_comment(2, 20)], pages=2))
    items = list(_connector(session).fetch())

    assert [i.external_id for i in items] == ["3", "2"]
    assert [c["params"]["page"] for c in session.calls] == [0, 1]


def test_budget_cut_does_not_advance_the_cursor(caplog) -> None:
    session = Session(_page([_comment(3, 30), _comment(2, 20), _comment(1, 10)]))
    connector = _connector(session, limit=2)
    connector.load_cursors(InMemoryCursorStore({"hackernews_search:comment:*": "5"}))

    with caplog.at_level("WARNING"):
        assert [i.external_id for i in connector.fetch()] == ["3", "2"]

    assert connector.pending_cursors() == {}
    assert "cursor not advanced" in caplog.text


def test_skips_dead_hits_and_nothing_new_leaves_the_cursor_alone() -> None:
    hits = [
        _comment(5, 50, comment_text=None),  # deleted comment
        _comment(6, 60, objectID="abc"),  # unexpected id
        _story(7, 70, title=""),
    ]
    connector = _connector(Session(_page(hits)))
    connector.load_cursors(InMemoryCursorStore({"hackernews_search:comment:*": "40"}))
    assert list(connector.fetch()) == []
    assert connector.pending_cursors() == {}


def test_searches_are_independent_and_share_the_budget() -> None:
    session = Session(_page([_comment(9, 90)]), _page([_story(8, 80)]))
    connector = _connector(session, SearchSpec("comment", "crm"), SearchSpec("ask_hn"), limit=5)
    assert [i.external_id for i in connector.fetch()] == ["9", "8"]
    assert connector.pending_cursors() == {
        "hackernews_search:comment:crm": "90",
        "hackernews_search:ask_hn:*": "80",
    }


@pytest.mark.parametrize(
    "response",
    [
        Response({"nope": 1}),
        Response({"hits": "x"}),
        Response(ValueError("bad json")),
        Response(None, requests.HTTPError("503")),
    ],
)
def test_bad_responses_raise_a_clear_error(response: Response) -> None:
    with pytest.raises(HackerNewsSearchError):
        list(_connector(Session(response)).fetch())


def test_validates_configuration() -> None:
    with pytest.raises(ValueError):
        SearchSpec("video")
    with pytest.raises(ValueError):
        SearchSpec("comment", "  ")
    with pytest.raises(ValueError):
        HackerNewsSearchConnector([])
    with pytest.raises(ValueError):
        HackerNewsSearchConnector([SearchSpec()], limit=0)


def test_factory_builds_the_connector_from_settings() -> None:
    settings = Settings(
        enabled_sources=("hackernews", "hackernews_search"),
        hackernews_searches=("ask_hn", "comment: duplicate contacts "),
    )
    first, second = build_configured_connectors(settings)

    assert isinstance(first, HackerNewsConnector)
    assert isinstance(second, HackerNewsSearchConnector)
    assert second.searches == (SearchSpec("ask_hn"), SearchSpec("comment", "duplicate contacts"))
    assert parse_search_specs(["Story"]) == (SearchSpec("story"),)


def test_worker_keeps_two_hackernews_connectors_apart_and_commits_cursors() -> None:
    store = InMemoryCursorStore()
    search = _connector(Session(_page([_comment(4, 400)])))

    class Plain:
        source = "hackernews"

        def fetch(self):
            return iter(())

    class Pipeline:
        last_run_stats = None

        def run(self, connector=None):
            list(connector.fetch())
            self.last_run_stats = PipelineRunStats(1, 1, 0, 1, 0)

    worker = PollingWorker(Pipeline(), [Plain(), search], store, interval_seconds=60)
    assert set(worker.health) == {"hackernews", "hackernews_search"}
    assert [r.status for r in worker.poll_once()] == ["ok", "ok"]
    assert store.get("hackernews_search:comment:*") == "400"
