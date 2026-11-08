from typing import Any

import pytest
import requests

from app.config import Settings
from app.ingestion.cursors import InMemoryCursorStore
from app.ingestion.factory import build_configured_connectors
from app.ingestion.stackexchange import API_URL, StackExchangeConnector, StackExchangeError

NOW = 1_762_560_000


def _question(question_id: int, created: int, **overrides: Any) -> dict[str, Any]:
    question = {
        "question_id": question_id,
        "title": f"Is there a tool for {question_id}?",
        "body": "<p>We do this by hand every week.</p>",
        "creation_date": created,
        "link": f"https://softwarerecs.stackexchange.com/q/{question_id}",
        "owner": {"display_name": "Dana"},
        "score": 3,
    }
    question.update(overrides)
    return question


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
        self.calls.append({"url": url, "params": dict(params)})
        page = self.pages.pop(0)
        return page if isinstance(page, Response) else Response(page)


def _connector(session: Session, **kwargs: Any) -> StackExchangeConnector:
    kwargs.setdefault("sleep", lambda _: None)
    return StackExchangeConnector(
        "SoftwareRecs", session=session, clock_seconds=lambda: NOW, **kwargs
    )


def test_maps_a_question_and_prefixes_the_site() -> None:
    session = Session({"items": [_question(7, NOW - 10)], "has_more": False})
    (item,) = list(_connector(session).fetch())

    assert (item.source, item.external_id) == ("stackexchange", "softwarerecs:7")
    assert item.title == "Is there a tool for 7?"
    assert item.body == "<p>We do this by hand every week.</p>"
    assert item.url == "https://softwarerecs.stackexchange.com/q/7"
    assert item.author == "Dana" and item.engagement_score == 3


def test_request_params_and_first_run_lookback() -> None:
    session = Session({"items": [], "has_more": False})
    list(_connector(session, queries=["duplicate contacts"], lookback_seconds=600, key="k").fetch())

    call = session.calls[0]
    assert call["url"] == API_URL
    assert call["params"] | {} == {
        "site": "softwarerecs",
        "order": "desc",
        "sort": "creation",
        "fromdate": NOW - 600 + 1,
        "pagesize": 100,
        "page": 1,
        "filter": "withbody",
        "q": "duplicate contacts",
        "key": "k",
    }


def test_cursor_is_used_as_fromdate_and_advances() -> None:
    session = Session({"items": [_question(9, 2000), _question(8, 1500)], "has_more": False})
    connector = _connector(session)
    connector.load_cursors(InMemoryCursorStore({"stackexchange:softwarerecs:*": "1000"}))

    assert [i.external_id for i in connector.fetch()] == ["softwarerecs:9", "softwarerecs:8"]
    assert session.calls[0]["params"]["fromdate"] == 1001
    assert connector.pending_cursors() == {"stackexchange:softwarerecs:*": "2000"}


def test_paginates_while_has_more() -> None:
    session = Session(
        {"items": [_question(3, 30)], "has_more": True},
        {"items": [_question(2, 20)], "has_more": False},
    )
    assert len(list(_connector(session).fetch())) == 2
    assert [c["params"]["page"] for c in session.calls] == [1, 2]


def test_budget_cut_does_not_advance_the_cursor() -> None:
    session = Session({"items": [_question(3, 30), _question(2, 20)], "has_more": False})
    connector = _connector(session, limit=1)
    connector.load_cursors(InMemoryCursorStore({"stackexchange:softwarerecs:*": "5"}))
    assert len(list(connector.fetch())) == 1
    assert connector.pending_cursors() == {}


def test_honours_a_short_backoff_and_refuses_a_long_one() -> None:
    sleeps: list[float] = []
    session = Session({"items": [], "has_more": False, "backoff": 5})
    list(_connector(session, sleep=sleeps.append).fetch())
    assert sleeps == [5.0]

    with pytest.raises(StackExchangeError, match="back off"):
        list(_connector(Session({"items": [], "backoff": 600})).fetch())


@pytest.mark.parametrize(
    "response",
    [
        Response({"nope": 1}),
        Response({"items": "x"}),
        Response(ValueError("bad json")),
        Response(None, requests.HTTPError("502")),
    ],
)
def test_bad_responses_raise_a_clear_error(response: Response) -> None:
    with pytest.raises(StackExchangeError):
        list(_connector(Session(response)).fetch())


def test_skips_incomplete_questions() -> None:
    items = [_question(1, 10, title=""), _question(2, 20, link=""), _question(3, 30)]
    session = Session({"items": items, "has_more": False})
    assert [i.external_id for i in _connector(session).fetch()] == ["softwarerecs:3"]


def test_validates_configuration_and_factory_builds_it() -> None:
    with pytest.raises(ValueError):
        StackExchangeConnector(" ")
    with pytest.raises(ValueError):
        StackExchangeConnector("x", queries=["  "])
    with pytest.raises(ValueError):
        StackExchangeConnector("x", limit=0)

    settings = Settings(
        enabled_sources=("stackexchange",),
        stackexchange_site="softwarerecs",
        stackexchange_queries=("crm", "lead gen"),
        stackexchange_limit=50,
    )
    (connector,) = build_configured_connectors(settings)
    assert isinstance(connector, StackExchangeConnector)
    assert connector.queries == ("crm", "lead gen") and connector.limit == 50
    assert connector.name == "stackexchange:softwarerecs"
