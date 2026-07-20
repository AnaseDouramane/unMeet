from app.services.multi_source_ingestion import MultiSourceIngestionService
from app.services.pipeline import PipelineRunStats


class FakeConnector:
    def __init__(self, source: str) -> None:
        self.source = source


class FakePipeline:
    def __init__(self, outcomes: dict[str, PipelineRunStats | Exception]) -> None:
        self.outcomes = outcomes
        self.last_run_stats: PipelineRunStats | None = None
        self.sources: list[str] = []

    def run(self, connector=None) -> None:
        self.last_run_stats = None
        self.sources.append(connector.source)
        outcome = self.outcomes[connector.source]
        if isinstance(outcome, Exception):
            raise outcome
        self.last_run_stats = outcome


def _stats(acquired: int, problems: int, non_problems: int, embeddings: int) -> PipelineRunStats:
    return PipelineRunStats(acquired, problems, non_problems, embeddings)


def test_multi_source_ingestion_aggregates_two_successful_sources() -> None:
    pipeline = FakePipeline(
        {
            "hackernews": _stats(4, 2, 2, 2),
            "reddit": _stats(3, 1, 2, 1),
        }
    )

    result = MultiSourceIngestionService(
        pipeline,
        [FakeConnector("hackernews"), FakeConnector("reddit")],
    ).run()

    assert pipeline.sources == ["hackernews", "reddit"]
    assert (result.acquired_count, result.problem_count) == (7, 3)
    assert (result.non_problem_count, result.embedding_count) == (4, 3)
    assert [item.source for item in result.source_stats] == ["hackernews", "reddit"]
    assert result.errors == ()
    assert result.successful_source_count == 2
    assert result.failed_source_count == 0
    assert result.is_success is True


def test_multi_source_ingestion_stops_on_first_error_when_fail_fast() -> None:
    pipeline = FakePipeline(
        {
            "hackernews": _stats(1, 1, 0, 1),
            "reddit": RuntimeError("reddit unavailable"),
            "later": _stats(2, 1, 1, 1),
        }
    )

    result = MultiSourceIngestionService(
        pipeline,
        [FakeConnector("hackernews"), FakeConnector("reddit"), FakeConnector("later")],
        fail_fast=True,
    ).run()

    assert pipeline.sources == ["hackernews", "reddit"]
    assert [item.source for item in result.source_stats] == ["hackernews"]
    assert result.errors[0].source == "reddit"
    assert result.failed_source_count == 1
    assert result.is_success is False


def test_multi_source_ingestion_continues_after_error_when_fail_fast_is_disabled() -> None:
    pipeline = FakePipeline(
        {
            "hackernews": _stats(1, 1, 0, 1),
            "reddit": RuntimeError("reddit unavailable"),
            "later": _stats(2, 0, 2, 0),
        }
    )

    result = MultiSourceIngestionService(
        pipeline,
        [FakeConnector("hackernews"), FakeConnector("reddit"), FakeConnector("later")],
        fail_fast=False,
    ).run()

    assert pipeline.sources == ["hackernews", "reddit", "later"]
    assert result.acquired_count == 3
    assert [item.source for item in result.source_stats] == ["hackernews", "later"]
    assert [error.source for error in result.errors] == ["reddit"]
    assert result.successful_source_count == 2
    assert result.failed_source_count == 1
    assert result.is_success is False


def test_multi_source_ingestion_reports_failure_when_all_sources_fail() -> None:
    pipeline = FakePipeline(
        {"hackernews": RuntimeError("hn unavailable"), "reddit": RuntimeError("reddit unavailable")}
    )

    result = MultiSourceIngestionService(
        pipeline,
        [FakeConnector("hackernews"), FakeConnector("reddit")],
        fail_fast=False,
    ).run()

    assert result.acquired_count == 0
    assert result.source_stats == ()
    assert result.successful_source_count == 0
    assert result.failed_source_count == 2
    assert result.is_success is False
