from app.config import Settings
from app.ingestion.cursors import InMemoryCursorStore
from app.ingestion.factory import build_configured_connectors
from app.ingestion.topic_search import MAX_PHRASES, TopicSearchConnector, phrases_for, searches_for
from app.topics.schemas import Topic

NOW = 1_762_560_000


def topic(topic_id: int, **kwargs) -> Topic:
    return Topic(name=f"t{topic_id}", id=topic_id, description="d", **kwargs)


class Response:
    def __init__(self, hits) -> None:
        self._payload = {"hits": hits, "nbPages": 1}

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return self._payload


class Session:
    def __init__(self, hits_by_query=None) -> None:
        self.hits_by_query = hits_by_query or {}
        self.calls: list[dict] = []

    def get(self, url, params, timeout):
        self.calls.append(dict(params))
        return Response(self.hits_by_query.get(params.get("query"), []))


def hit(object_id, created, text):
    return {
        "objectID": str(object_id),
        "created_at_i": created,
        "_tags": ["comment"],
        "author": "u",
        "comment_text": text,
        "story_title": "A story",
    }


def test_phrases_come_from_keywords_first_then_products_without_duplicates() -> None:
    topics = [
        topic(1, keywords=("Looking for a tool", "alternative to x"), products=("HubSpot", "X")),
        topic(2, keywords=("looking for a tool",), products=("hubspot", "Pipedrive")),
    ]
    assert phrases_for(topics) == (
        "Looking for a tool",
        "alternative to x",
        "HubSpot",
        "X",
        "Pipedrive",
    )


def test_phrases_are_capped_and_blank_ones_never_searched() -> None:
    many = [
        topic(
            1,
            keywords=tuple(f"phrase number {i}" for i in range(10)),
            products=tuple(f"P{i}" for i in range(50)),
        )
    ]
    assert len(phrases_for(many)) == MAX_PHRASES
    assert searches_for([topic(1, products=(" ",))]) == ()


def test_searches_use_exact_quoted_phrases_over_stories_and_comments() -> None:
    (spec,) = searches_for([topic(1, keywords=("find leads",))])
    assert (spec.tag, spec.query) == ("any", '"find leads"')


def test_the_connector_follows_the_topics_and_sends_the_exact_query() -> None:
    topics = [topic(1, keywords=("find leads",))]
    session = Session({'"find leads"': [hit(5, NOW - 10, "I need a way to find leads on reddit")]})
    connector = TopicSearchConnector(lambda: topics, session=session, clock_seconds=lambda: NOW)

    items = list(connector.fetch())

    assert [i.external_id for i in items] == ["5"] and items[0].source == "hackernews"
    call = session.calls[0]
    assert call["tags"] == "(story,comment)" and call["query"] == '"find leads"'
    assert call["advancedSyntax"] == "true" and call["typoTolerance"] == "false"
    assert connector.name == "hackernews_topics"

    # A topic added later is searched on the next poll, with no restart or configuration.
    topics.append(topic(2, keywords=("monitor reddit",)))
    session.calls.clear()
    list(connector.fetch())
    assert [c["query"] for c in session.calls] == ['"find leads"', '"monitor reddit"']


def test_cursors_are_kept_per_phrase_so_new_phrases_start_from_the_lookback() -> None:
    topics = [topic(1, keywords=("find leads",))]
    session = Session({'"find leads"': [hit(5, NOW - 10, "x" * 30)]})
    connector = TopicSearchConnector(
        lambda: topics, session=session, clock_seconds=lambda: NOW, lookback_seconds=600
    )
    store = InMemoryCursorStore()

    connector.load_cursors(store)
    list(connector.fetch())
    store.set_many(connector.pending_cursors())
    assert store.get('hackernews_search:any:"find leads"') == str(NOW - 10)

    topics.append(topic(2, keywords=("new phrase",)))
    connector.load_cursors(store)
    session.calls.clear()
    list(connector.fetch())
    by_query = {c["query"]: c["numericFilters"] for c in session.calls}
    assert by_query['"find leads"'] == f"created_at_i>{NOW - 10}"
    assert by_query['"new phrase"'] == f"created_at_i>{NOW - 600}"


def test_without_phrases_nothing_is_requested() -> None:
    session = Session()
    connector = TopicSearchConnector(lambda: [topic(1)], session=session)
    assert list(connector.fetch()) == [] and session.calls == []


def test_the_factory_builds_it_from_the_topic_repository(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.topics.repository.TopicRepository.list",
        lambda self, workspace_id=None: (),
        raising=True,
    )
    (connector,) = build_configured_connectors(Settings(enabled_sources=("hackernews_topics",)))
    assert isinstance(connector, TopicSearchConnector) and connector.searches == ()
