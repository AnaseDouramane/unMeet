import threading
from typing import Any

import pytest

from app.ingestion.cursors import InMemoryCursorStore
from app.ingestion.reddit import RedditConnector
from app.services.pipeline import PipelineRunStats
from app.services.polling import PollingWorker


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakePipeline:
    def __init__(self, behaviours: dict[str, list[Any]] | None = None) -> None:
        self.behaviours = behaviours or {}
        self.last_run_stats: PipelineRunStats | None = None
        self.runs: list[str] = []

    def run(self, connector=None):
        source = connector.source
        self.runs.append(source)
        queue = self.behaviours.get(source)
        outcome = queue.pop(0) if queue else None
        if isinstance(outcome, Exception):
            raise outcome
        # Consume the connector like the real pipeline does.
        list(connector.fetch())
        self.last_run_stats = PipelineRunStats(3, 1, 2, 1, 0, skipped_count=1, gated_out_count=1)


class Source:
    """Plain connector without cursors."""

    def __init__(self, source: str) -> None:
        self.source = source

    def fetch(self):
        return iter(())


def _worker(connectors, pipeline=None, clock=None, **kwargs) -> tuple[PollingWorker, FakePipeline]:
    pipeline = pipeline or FakePipeline()
    worker = PollingWorker(
        pipeline,
        connectors,
        InMemoryCursorStore(),
        interval_seconds=100,
        max_backoff_seconds=1000,
        stall_after_seconds=500,
        clock=clock or Clock(),
        jitter=lambda interval: interval,
        **kwargs,
    )
    return worker, pipeline


def test_poll_once_runs_every_source_and_reports_stats() -> None:
    worker, pipeline = _worker([Source("hackernews"), Source("reddit")])

    results = worker.poll_once()

    assert [(r.source, r.status) for r in results] == [("hackernews", "ok"), ("reddit", "ok")]
    assert pipeline.runs == ["hackernews", "reddit"]
    assert results[0].stats is not None and results[0].stats.gated_out_count == 1


def test_a_failing_source_does_not_block_the_others_and_backs_off() -> None:
    clock = Clock()
    pipeline = FakePipeline({"reddit": [RuntimeError("429"), RuntimeError("429"), None]})
    worker, _ = _worker([Source("reddit"), Source("hackernews")], pipeline, clock)

    first = worker.poll_once()
    assert [(r.source, r.status) for r in first] == [("reddit", "error"), ("hackernews", "ok")]
    assert first[0].error == "429"

    clock.now += 50  # inside the 200s backoff (interval * 2**1)
    second = worker.poll_once()
    assert [(r.source, r.status) for r in second] == [("reddit", "backoff"), ("hackernews", "ok")]
    assert pipeline.runs.count("reddit") == 1

    clock.now += 200  # backoff over: second failure doubles the delay to 400s
    assert worker.poll_once()[0].status == "error"
    clock.now += 399
    assert worker.poll_once()[0].status == "backoff"
    clock.now += 2
    assert worker.poll_once()[0].status == "ok"
    assert worker.health["reddit"].consecutive_failures == 0


def test_backoff_is_capped() -> None:
    clock = Clock()
    pipeline = FakePipeline({"reddit": [RuntimeError("x")] * 20})
    worker, _ = _worker([Source("reddit")], pipeline, clock)
    for _ in range(8):
        worker.poll_once()
        clock.now = worker.health["reddit"].next_attempt_at
    delay = worker.health["reddit"].next_attempt_at - clock.now
    assert delay == 0
    worker.poll_once()
    assert worker.health["reddit"].next_attempt_at - clock.now == 1000


def test_stalled_sources_are_reported_after_the_threshold() -> None:
    clock = Clock()
    pipeline = FakePipeline({"reddit": [RuntimeError("down")] * 10})
    worker, _ = _worker([Source("reddit"), Source("hackernews")], pipeline, clock)
    worker.poll_once()
    assert worker.stalled_sources() == []
    clock.now += 600
    worker.health["hackernews"].last_success_at = clock.now  # hackernews keeps succeeding
    assert worker.stalled_sources() == ["reddit"]


def test_run_stops_when_the_stop_event_is_set_and_waits_between_cycles() -> None:
    stop = threading.Event()
    waits: list[float] = []

    def wait(seconds: float) -> bool:
        waits.append(seconds)
        if len(waits) == 3:
            stop.set()
        return stop.is_set()

    worker, pipeline = _worker([Source("hackernews")])
    cycles = worker.run(stop, wait=wait)

    assert cycles == 3
    assert waits == [100, 100, 100]
    assert pipeline.runs == ["hackernews"] * 3


def test_run_honours_max_cycles_and_a_preset_stop() -> None:
    worker, pipeline = _worker([Source("hackernews")])
    assert worker.run(threading.Event(), wait=lambda _: False, max_cycles=2) == 2
    stop = threading.Event()
    stop.set()
    assert worker.run(stop) == 0
    assert pipeline.runs == ["hackernews"] * 2


def test_requires_connectors_and_positive_intervals() -> None:
    with pytest.raises(ValueError):
        PollingWorker(FakePipeline(), [], InMemoryCursorStore())
    with pytest.raises(ValueError):
        PollingWorker(FakePipeline(), [Source("x")], InMemoryCursorStore(), interval_seconds=0)


# --- cursors with the Reddit connector ------------------------------------------------------


def _post(post_id: str, created: float) -> dict[str, Any]:
    return {
        "id": post_id,
        "title": f"Post {post_id}",
        "selftext": "body",
        "author": "u",
        "created_utc": created,
        "permalink": f"/r/sales/comments/{post_id}/",
        "score": 1,
    }


class FakeRedditClient:
    def __init__(self, posts: dict[str, list[dict[str, Any]]]) -> None:
        self.posts = posts
        self.calls: list[tuple[str, int]] = []

    def fetch_posts(self, subreddit: str, sort: str, limit: int):
        self.calls.append((subreddit, limit))
        return self.posts[subreddit][:limit]


def _reddit(client: FakeRedditClient, limit: int = 100, subs=("sales",)) -> RedditConnector:
    return RedditConnector(list(subs), limit=limit, client=client)


def test_reddit_skips_posts_already_seen_and_commits_cursor_only_via_worker() -> None:
    client = FakeRedditClient({"sales": [_post("c", 300), _post("b", 200), _post("a", 100)]})
    store = InMemoryCursorStore()
    connector = _reddit(client)

    connector.load_cursors(store)
    assert [i.external_id for i in connector.fetch()] == ["c", "b", "a"]
    assert connector.pending_cursors() == {"reddit:sales": "300.0"}
    assert store.get("reddit:sales") is None  # not committed by the connector

    store.set_many(connector.pending_cursors())
    client.posts["sales"] = [_post("e", 500), _post("d", 400), _post("c", 300), _post("b", 200)]
    connector.load_cursors(store)
    assert [i.external_id for i in connector.fetch()] == ["e", "d"]
    assert connector.pending_cursors() == {"reddit:sales": "500.0"}


def test_reddit_cursor_does_not_advance_when_nothing_is_new() -> None:
    client = FakeRedditClient({"sales": [_post("a", 100)]})
    connector = _reddit(client)
    connector.load_cursors(InMemoryCursorStore({"reddit:sales": "100.0"}))
    assert list(connector.fetch()) == []
    assert connector.pending_cursors() == {}


def test_reddit_warns_when_the_whole_window_is_newer_than_the_cursor(caplog) -> None:
    # A backlog bigger than the page: older unread posts may exist beyond what the API returned.
    client = FakeRedditClient({"sales": [_post("c", 300), _post("b", 200)]})
    connector = _reddit(client, limit=2)
    connector.load_cursors(InMemoryCursorStore({"reddit:sales": "50.0"}))

    with caplog.at_level("WARNING"):
        assert [i.external_id for i in connector.fetch()] == ["c", "b"]

    assert "may have been missed" in caplog.text
    assert connector.pending_cursors() == {"reddit:sales": "300.0"}


def test_reddit_does_not_advance_the_cursor_when_the_budget_cuts_the_listing() -> None:
    class IgnoresLimit(FakeRedditClient):
        def fetch_posts(self, subreddit, sort, limit):
            return self.posts[subreddit]  # returns more than requested

    client = IgnoresLimit({"sales": [_post("c", 300), _post("b", 200), _post("a", 100)]})
    connector = _reddit(client, limit=2)
    connector.load_cursors(InMemoryCursorStore({"reddit:sales": "50.0"}))

    assert [i.external_id for i in connector.fetch()] == ["c", "b"]
    # Post "a" was cut by the budget: moving the cursor to 300 would lose it forever.
    assert connector.pending_cursors() == {}


def test_reddit_budget_is_shared_across_subreddits() -> None:
    client = FakeRedditClient(
        {"one": [_post("x2", 900), _post("x1", 800)], "two": [_post("y2", 700), _post("y1", 600)]}
    )
    connector = _reddit(client, limit=3, subs=("one", "two"))
    connector.load_cursors(InMemoryCursorStore({"reddit:two": "10.0"}))

    assert [i.external_id for i in connector.fetch()] == ["x2", "x1", "y2"]
    assert client.calls == [("one", 3), ("two", 1)]


def test_worker_commits_cursors_after_success_and_not_after_failure() -> None:
    client = FakeRedditClient({"sales": [_post("b", 200), _post("a", 100)]})
    connector = _reddit(client)
    store = InMemoryCursorStore()

    class Pipeline(FakePipeline):
        fail = True

        def run(self, connector=None):
            list(connector.fetch())
            if self.fail:
                raise RuntimeError("database down")
            self.last_run_stats = PipelineRunStats(2, 2, 0, 2, 0)

    pipeline = Pipeline()
    worker = PollingWorker(
        pipeline, [connector], store, interval_seconds=10, clock=Clock(), jitter=lambda i: i
    )
    assert worker.poll_once()[0].status == "error"
    assert store.get("reddit:sales") is None  # nothing lost: the next poll re-fetches

    worker.health["reddit"].next_attempt_at = 0
    pipeline.fail = False
    assert worker.poll_once()[0].status == "ok"
    assert store.get("reddit:sales") == "200.0"


def test_every_poll_is_recorded_with_its_numbers_or_its_error() -> None:
    from datetime import UTC, datetime

    from app.ingestion.runs import InMemoryRunStore

    store = InMemoryRunStore()
    pipeline = FakePipeline({"reddit": [RuntimeError("429 Too Many Requests")]})
    worker = PollingWorker(
        pipeline,
        [Source("hackernews"), Source("reddit")],
        InMemoryCursorStore(),
        interval_seconds=100,
        clock=Clock(),
        jitter=lambda i: i,
        recorder=store,
        now=lambda: datetime(2026, 11, 11, 9, 0, tzinfo=UTC),
    )
    worker.poll_once()

    ok, failed = sorted(store.latest(), key=lambda r: r.source)
    assert (ok.source, ok.status, ok.acquired, ok.gated_out, ok.problems) == (
        "hackernews",
        "ok",
        3,
        1,
        1,
    )
    assert (failed.source, failed.status, failed.error) == (
        "reddit",
        "error",
        "429 Too Many Requests",
    )


def test_a_broken_recorder_never_stops_polling(caplog) -> None:
    class Broken:
        def record(self, run):
            raise RuntimeError("database down")

    worker = PollingWorker(
        FakePipeline(),
        [Source("hackernews")],
        InMemoryCursorStore(),
        clock=Clock(),
        recorder=Broken(),
    )
    assert worker.poll_once()[0].status == "ok"
    assert "could not record" in caplog.text
