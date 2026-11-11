from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.ingestion.schemas import SourceItem
from app.problem_detection.schemas import (
    MalformedClassifierOutputError,
    ProblemDetectionResult,
    TopicContext,
    TopicMatch,
)
from app.problem_detection.service import ProblemDetectionService
from app.services.pipeline import Pipeline
from app.services.preprocessing import PreprocessingService
from app.topics.gate import TopicGate
from app.topics.schemas import Topic


class AxisEmbedder:
    model_name = "axis"

    def encode(self, text: str) -> list[float]:
        lowered = text.lower()
        if "crm" in lowered:
            return [1.0, 0.0, 0.0]
        if "invoice" in lowered:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    def encode_batch(self, texts):
        return [self.encode(text) for text in texts]


class TopicAwareClassifier:
    """Matches every offered topic and records what it was shown."""

    classifier_name = "topic-aware"
    supports_topic_matching = True

    def __init__(self) -> None:
        self.single_calls: list[tuple[str, tuple[TopicContext, ...]]] = []
        self.batch_calls: list[list[tuple[TopicContext, ...]]] = []
        self.request_count = 0

    def _result(self, topics) -> ProblemDetectionResult:
        return ProblemDetectionResult(
            True,
            0.9,
            "r",
            self.classifier_name,
            intent="pain_point",
            topic_matches=tuple(TopicMatch(t.id, f"fits {t.name}") for t in topics),
        )

    def classify(self, text: str, topics=()) -> ProblemDetectionResult:
        self.request_count += 1
        self.single_calls.append((text, tuple(topics)))
        return self._result(topics)

    def classify_batch(self, texts, topics_per_text=None):
        self.request_count += 1
        topic_lists = [tuple(t) for t in (topics_per_text or [()] * len(texts))]
        self.batch_calls.append(topic_lists)
        return [self._result(topics) for topics in topic_lists]


class PlainClassifier:
    classifier_name = "plain"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def classify(self, text: str) -> ProblemDetectionResult:
        self.calls.append(text)
        return ProblemDetectionResult(True, 0.9, "r", self.classifier_name)


class Connector:
    def __init__(self, bodies: list[str]) -> None:
        self.bodies = bodies

    def fetch(self):
        for index, body in enumerate(self.bodies):
            yield SourceItem(
                external_id=str(index),
                source="hackernews",
                title=f"T{index}",
                body=body,
                url="https://example.com",
                author="a",
                published_at=datetime(2026, 1, 1, tzinfo=UTC),
                raw_payload={},
                engagement_score=1,
            )


class Repo:
    def __init__(self) -> None:
        self.results: dict[str, ProblemDetectionResult] = {}

    def save(
        self,
        source_item,
        prepared_document,
        embedding=None,
        embedding_model=None,
        problem_detection_result=None,
    ):
        self.results[source_item.external_id] = problem_detection_result


TOPICS = [
    Topic(name="CRM hygiene", id=1, description="CRM data", max_distance=0.3),
    Topic(name="Billing", id=2, description="invoice failures", max_distance=0.3),
]
BODIES = ["our crm is a mess", "invoice export keeps failing", "pasta tonight", "crm again"]


def _run(classifier, *, batch_size: int = 1, workers: int = 1):
    embedder = AxisEmbedder()
    gate = TopicGate(lambda: TOPICS, embedder)
    repo = Repo()
    pipeline = Pipeline(
        settings=type("S", (), {"environment": "test"})(),
        connector=Connector(BODIES),
        preprocessing_service=PreprocessingService(),
        repository=repo,
        embedding_service=embedder,
        problem_detection_service=ProblemDetectionService(classifier),
        classification_workers=workers,
        topic_gate=gate,
        classification_batch_size=batch_size,
    )
    pipeline.run()
    return pipeline, repo


def test_each_item_is_classified_with_its_own_candidate_topics() -> None:
    classifier = TopicAwareClassifier()
    pipeline, repo = _run(classifier)

    assert len(classifier.single_calls) == 3  # "pasta tonight" was gated out
    by_topic = {tuple(t.id for t in topics) for _, topics in classifier.single_calls}
    assert by_topic == {(1,), (2,)}
    assert [m.topic_id for m in repo.results["0"].topic_matches] == [1]
    assert [m.topic_id for m in repo.results["1"].topic_matches] == [2]
    assert repo.results["1"].topic_matches[0].reason == "fits Billing"
    assert repo.results["2"].classifier_name == "topic_gate"
    assert pipeline.last_run_stats is not None
    assert pipeline.last_run_stats.gated_out_count == 1


@pytest.mark.parametrize("workers", [1, 3])
def test_batches_carry_per_item_topics_and_keep_order(workers: int) -> None:
    classifier = TopicAwareClassifier()
    pipeline, repo = _run(classifier, batch_size=2, workers=workers)

    # Three classifiable items with batch size 2: one batch of two and one lone single call.
    assert [len(call) for call in classifier.batch_calls] == [2]
    assert len(classifier.single_calls) == 1
    assert [m.topic_id for m in repo.results["0"].topic_matches] == [1]
    assert [m.topic_id for m in repo.results["1"].topic_matches] == [2]
    assert [m.topic_id for m in repo.results["3"].topic_matches] == [1]
    assert pipeline.last_run_stats is not None
    assert pipeline.last_run_stats.llm_call_count == 2  # 3 items in 2 requests


def test_classifier_without_topic_support_still_works_and_has_no_matches() -> None:
    classifier = PlainClassifier()
    _, repo = _run(classifier)
    assert len(classifier.calls) == 3
    assert all(r.topic_matches == () for r in repo.results.values())


def test_malformed_batch_entry_retry_keeps_topics() -> None:
    class Flaky(TopicAwareClassifier):
        def classify_batch(self, texts, topics_per_text=None):
            results = super().classify_batch(texts, topics_per_text)
            return [MalformedClassifierOutputError("bad"), *results[1:]]

    classifier = Flaky()
    _, repo = _run(classifier, batch_size=2)
    retried = [topics for _, topics in classifier.single_calls]
    assert retried and all(topics for topics in retried)
    assert all(r.topic_matches for k, r in repo.results.items() if k != "2")


def test_result_dataclass_is_replaceable_with_matches() -> None:
    base = ProblemDetectionResult(True, 0.5, "r", "c")
    assert replace(base, topic_matches=(TopicMatch(1, "x"),)).topic_matches[0].reason == "x"


def test_pipeline_skips_authors_who_asked_to_be_forgotten() -> None:
    from app.privacy.service import ErasureFilter

    class Privacy:
        def suppressed_authors(self, source):
            from app.privacy.service import author_key

            return frozenset({author_key("a")}) if source == "hackernews" else frozenset()

    classifier = TopicAwareClassifier()
    embedder = AxisEmbedder()
    repo = Repo()
    pipeline = Pipeline(
        settings=type("S", (), {"environment": "test"})(),
        connector=Connector(["crm one", "crm two"]),
        preprocessing_service=PreprocessingService(),
        repository=repo,
        embedding_service=embedder,
        problem_detection_service=ProblemDetectionService(classifier),
        erasure_filter=ErasureFilter(Privacy()),
    )
    pipeline.run()

    assert repo.results == {}  # every item is by author "a"
    assert classifier.single_calls == []
    stats = pipeline.last_run_stats
    assert stats is not None and stats.suppressed_count == 2 and stats.acquired_count == 2


def test_stats_count_how_many_items_matched_a_topic() -> None:
    pipeline, _ = _run(TopicAwareClassifier())
    stats = pipeline.last_run_stats
    assert stats is not None and stats.matched_count == 3 and stats.problem_count == 3

    pipeline, _ = _run(PlainClassifier())
    assert pipeline.last_run_stats is not None and pipeline.last_run_stats.matched_count == 0
