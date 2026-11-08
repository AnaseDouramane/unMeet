from datetime import UTC, datetime

from app.ingestion.schemas import SourceItem
from app.problem_detection.schemas import ProblemDetectionResult
from app.services.pipeline import Pipeline
from app.services.preprocessing import PreprocessingService
from app.topics.gate import GATE_CLASSIFIER_NAME, TopicGate
from app.topics.schemas import Topic


class AxisEmbedder:
    """Embeds text on one of three orthogonal axes: crm, devops or other."""

    model_name = "axis-test-model"

    def __init__(self) -> None:
        self.encode_calls = 0

    def encode(self, document_text: str) -> list[float]:
        self.encode_calls += 1
        lowered = document_text.lower()
        if "crm" in lowered or "hubspot" in lowered:
            return [1.0, 0.0, 0.0]
        if "deploy" in lowered:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    def encode_batch(self, document_texts):
        return [self.encode(text) for text in document_texts]


def _topic(topic_id: int, **kwargs) -> Topic:
    values = {"name": f"t{topic_id}", "id": topic_id, "max_distance": 0.3}
    values.update(kwargs)
    return Topic(**values)


def _gate(topics: list[Topic]) -> TopicGate:
    gate = TopicGate(lambda: topics, AxisEmbedder())
    gate.begin_run()
    return gate


def test_no_topics_lets_everything_through() -> None:
    decision = _gate([]).evaluate("anything at all")
    assert decision.passed
    assert decision.reason == "no_active_topics"


def test_semantic_match_passes_and_unrelated_is_gated() -> None:
    gate = _gate([_topic(1, description="CRM data quality")])
    assert gate.evaluate("our crm is a mess").matched_topic_ids == (1,)
    blocked = gate.evaluate("lovely weather today")
    assert not blocked.passed
    assert blocked.reason == "no_topic_match"


def test_product_mention_passes_even_when_semantically_far() -> None:
    gate = _gate([_topic(1, description="CRM data quality", products=("Zapier",))])
    assert gate.evaluate("zapier broke again").passed
    assert not gate.evaluate("zapierlike words").passed  # word boundary respected


def test_products_only_topic_requires_the_product() -> None:
    gate = _gate([_topic(1, products=("Salesforce",))])
    assert gate.evaluate("Salesforce is slow").passed
    assert not gate.evaluate("hubspot is slow").passed


def test_intent_only_topic_cannot_be_prefiltered() -> None:
    gate = _gate([_topic(1, intents=("pain_point",))])
    assert gate.evaluate("lovely weather today").passed


def test_matches_any_of_several_topics() -> None:
    gate = _gate([_topic(1, description="CRM"), _topic(2, description="deploy pipeline")])
    assert gate.evaluate("deploy keeps failing").matched_topic_ids == (2,)


def test_topic_description_is_embedded_once_across_runs() -> None:
    embedder = AxisEmbedder()
    topics = [_topic(1, description="CRM data quality")]
    gate = TopicGate(lambda: topics, embedder)
    gate.begin_run()
    gate.begin_run()
    assert embedder.encode_calls == 1
    topics[:] = [_topic(1, description="CRM data quality, edited")]
    gate.begin_run()
    assert embedder.encode_calls == 2


# --- pipeline integration -------------------------------------------------------------------


def _item(index: int, text: str) -> SourceItem:
    return SourceItem(
        external_id=str(index),
        source="hackernews",
        title=f"Title {index}",
        body=text,
        url=f"https://example.com/{index}",
        author="author",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        raw_payload={},
        engagement_score=1,
    )


class ListConnector:
    def __init__(self, items: list[SourceItem]) -> None:
        self.items = items

    def fetch(self):
        yield from self.items


class RecordingRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[str, bool | None, str | None, bool]] = []

    def save(
        self,
        source_item,
        prepared_document,
        embedding=None,
        embedding_model=None,
        problem_detection_result=None,
    ):
        self.saved.append(
            (
                source_item.external_id,
                problem_detection_result.is_problem if problem_detection_result else None,
                problem_detection_result.classifier_name if problem_detection_result else None,
                embedding is not None,
            )
        )


class CountingDetection:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def detect(self, prepared_document):
        self.calls.append(prepared_document.document_text)
        return ProblemDetectionResult(True, 0.9, "ok", "llm-test")


def _pipeline(items, gate, repository, detection) -> Pipeline:
    return Pipeline(
        settings=type("S", (), {"environment": "test"})(),
        connector=ListConnector(items),
        preprocessing_service=PreprocessingService(),
        repository=repository,
        embedding_service=AxisEmbedder(),
        problem_detection_service=detection,
        topic_gate=gate,
    )


def test_pipeline_sends_only_matching_items_to_the_llm() -> None:
    items = [
        _item(0, "our crm duplicates contacts"),
        _item(1, "pasta recipe for tonight"),
        _item(2, "hubspot sync is broken again"),
        _item(3, "holiday photos from the trip"),
    ]
    repository, detection = RecordingRepository(), CountingDetection()
    pipeline = _pipeline(items, _gate([_topic(1, description="CRM data")]), repository, detection)

    documents = pipeline.run()

    assert len(detection.calls) == 2
    assert [d.source_item.external_id for d in documents] == ["0", "2"]
    assert repository.saved == [
        ("0", True, "llm-test", True),
        ("1", False, GATE_CLASSIFIER_NAME, False),
        ("2", True, "llm-test", True),
        ("3", False, GATE_CLASSIFIER_NAME, False),
    ]
    stats = pipeline.last_run_stats
    assert stats is not None
    assert (stats.acquired_count, stats.gated_out_count, stats.llm_call_count) == (4, 2, 2)
    assert stats.problem_count == 2
    assert stats.non_problem_count == 2


def test_pipeline_without_gate_classifies_everything() -> None:
    items = [_item(0, "a"), _item(1, "b")]
    detection = CountingDetection()
    pipeline = _pipeline(items, None, RecordingRepository(), detection)
    pipeline.run()
    stats = pipeline.last_run_stats
    assert stats is not None
    assert (stats.gated_out_count, stats.llm_call_count) == (0, 2)


def test_gated_items_are_rechecked_when_topics_change() -> None:
    item = _item(0, "pasta recipe for tonight")
    stored = type(
        "P",
        (),
        {"is_problem": False, "dedup_hash": None, "problem_classifier": GATE_CLASSIFIER_NAME},
    )()
    prepared = PreprocessingService().prepare(item)
    stored.dedup_hash = prepared.dedup_hash

    class Repo(RecordingRepository):
        def get_by_source_and_external_id(self, source, external_id):
            return stored

    detection = CountingDetection()
    pipeline = _pipeline([item], _gate([_topic(1, description="pasta")]), Repo(), detection)
    pipeline.run()
    assert pipeline.last_run_stats is not None
    assert pipeline.last_run_stats.skipped_count == 0


def test_gate_loads_each_topics_feedback_once_per_run() -> None:
    calls: list[int] = []

    def examples(topic: Topic):
        calls.append(topic.id)
        return [(f"example for {topic.id}", True)]

    topics = [_topic(1, description="CRM data"), _topic(2, description="deploy pipeline")]
    gate = TopicGate(lambda: topics, AxisEmbedder(), examples=examples)
    gate.begin_run()
    for _ in range(5):
        gate.evaluate("our crm is a mess")

    assert calls == [1, 2]
    (context,) = gate.topic_contexts([2])
    assert context.examples == (("example for 2", True),)
    assert TopicGate(lambda: topics, AxisEmbedder()).topic_contexts([1]) == ()  # before begin_run
