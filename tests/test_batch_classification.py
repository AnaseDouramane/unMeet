import json
from datetime import UTC, datetime
from typing import Any

import pytest

from app.ingestion.schemas import SourceItem
from app.problem_detection.llm import BATCH_JSON_SCHEMA, OpenAICompatibleSignalClassifier
from app.problem_detection.schemas import MalformedClassifierOutputError, ProblemDetectionResult
from app.problem_detection.service import ProblemDetectionService
from app.services.pipeline import Pipeline
from app.services.preprocessing import PreprocessingService

TEXTS = [
    "Every Monday I spend three hours cleaning duplicate contacts in HubSpot.",
    "Just launched our new dashboard, check it out!",
    "Is there a tool that syncs invoices to Xero automatically? Doing it by hand hurts.",
]


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self.status_code = 200
        self.headers: dict[str, str] = {}
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> Any:
        return self._payload


class FakeSession:
    def __init__(self, contents: list[Any]) -> None:
        self.contents = list(contents)
        self.requests: list[dict[str, Any]] = []

    def post(self, url, json, headers, timeout):
        self.requests.append(json)
        content = self.contents.pop(0)
        text = content if isinstance(content, str) else __import__("json").dumps(content)
        return FakeResponse({"choices": [{"message": {"content": text}}]})


def _entry(index: int, **overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "index": index,
        "is_problem": True,
        "confidence": 0.9,
        "intent": "pain_point",
        "pain_quote": None,
        "products_mentioned": [],
        "severity": 2,
        "reason": "r",
    }
    entry.update(overrides)
    return entry


def _classifier(session: FakeSession) -> OpenAICompatibleSignalClassifier:
    return OpenAICompatibleSignalClassifier(
        model="m",
        api_key="k",
        session=session,
        sleep=lambda _: None,  # type: ignore[arg-type]
    )


def test_batch_sends_one_request_and_maps_results_by_index() -> None:
    session = FakeSession(
        [
            {
                "results": [
                    _entry(2, pain_quote="Doing it by hand hurts", products_mentioned=["Xero"]),
                    _entry(0, pain_quote="spend three hours cleaning duplicate contacts"),
                    _entry(1, is_problem=False, intent="none", severity=None, reason="launch"),
                ]
            }
        ]
    )
    classifier = _classifier(session)

    results = classifier.classify_batch(TEXTS)

    assert len(session.requests) == 1
    assert classifier.request_count == 1
    prompt = session.requests[0]["messages"][1]["content"]
    assert "### Text 0" in prompt and "### Text 2" in prompt
    assert session.requests[0]["response_format"]["json_schema"]["schema"] == BATCH_JSON_SCHEMA
    assert [r.is_problem for r in results] == [True, False, True]  # type: ignore[union-attr]
    assert results[0].pain_quote == "spend three hours cleaning duplicate contacts"  # type: ignore[union-attr]
    assert results[2].products_mentioned == ("Xero",)  # type: ignore[union-attr]


def test_quote_must_come_from_its_own_text() -> None:
    # Text 1's quote is real, but belongs to text 0: it must be dropped for text 1.
    session = FakeSession(
        [{"results": [_entry(0), _entry(1, pain_quote="spend three hours cleaning duplicate")]}]
    )
    results = _classifier(session).classify_batch(TEXTS[:2])
    assert isinstance(results[1], ProblemDetectionResult)
    assert results[1].pain_quote is None


def test_missing_and_invalid_entries_are_reported_per_item() -> None:
    session = FakeSession([{"results": [_entry(0), _entry(2, confidence="high")]}])
    results = _classifier(session).classify_batch(TEXTS)
    assert isinstance(results[0], ProblemDetectionResult)
    assert isinstance(results[1], MalformedClassifierOutputError)  # skipped by the model
    assert isinstance(results[2], MalformedClassifierOutputError)  # invalid confidence


def test_non_json_batch_marks_every_item_malformed() -> None:
    results = _classifier(FakeSession(["not json"])).classify_batch(TEXTS)
    assert all(isinstance(r, MalformedClassifierOutputError) for r in results)


def test_batch_rejects_empty_text() -> None:
    with pytest.raises(ValueError):
        _classifier(FakeSession([])).classify_batch(["ok", "  "])


# --- service fallback -----------------------------------------------------------------------


def _doc(text: str, index: int = 0):
    item = SourceItem(
        external_id=str(index),
        source="hackernews",
        title=f"T{index}",
        body=text,
        url="https://example.com",
        author="a",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        raw_payload={},
        engagement_score=1,
    )
    return PreparedDocument_from(item)


def PreparedDocument_from(item: SourceItem):
    return PreprocessingService().prepare(item)


def test_service_retries_only_malformed_items_individually() -> None:
    session = FakeSession(
        [
            {"results": [_entry(0), _entry(2)]},  # text 1 skipped
            _entry(0, is_problem=False, intent="none", severity=None, reason="launch"),
        ]
    )
    classifier = _classifier(session)
    service = ProblemDetectionService(classifier)
    docs = [_doc(text, i) for i, text in enumerate(TEXTS)]

    results = service.detect_batch_with_status(docs)

    assert [r.is_problem for r, _ in results] == [True, False, True]
    assert [malformed for _, malformed in results] == [False, False, False]
    assert classifier.request_count == 2  # one batch + one single retry
    assert service.llm_request_count == 2


def test_service_without_batch_support_falls_back_to_single_calls() -> None:
    class Single:
        classifier_name = "single"

        def __init__(self) -> None:
            self.calls = 0

        def classify(self, text: str) -> ProblemDetectionResult:
            self.calls += 1
            return ProblemDetectionResult(True, 0.9, "r", "single")

    classifier = Single()
    service = ProblemDetectionService(classifier)
    assert not service.supports_batching
    assert service.llm_request_count is None
    service.detect_batch_with_status([_doc("a", 0), _doc("b", 1)])
    assert classifier.calls == 2


# --- pipeline -------------------------------------------------------------------------------


class ListConnector:
    def __init__(self, items: list[SourceItem]) -> None:
        self.items = items

    def fetch(self):
        yield from self.items


class Repo:
    def __init__(self) -> None:
        self.saved: list[tuple[str, bool | None]] = []

    def save(
        self,
        source_item,
        prepared_document,
        embedding=None,
        embedding_model=None,
        problem_detection_result=None,
    ):
        self.saved.append((source_item.external_id, problem_detection_result.is_problem))


class Embedder:
    model_name = "fake"

    def encode(self, text: str) -> list[float]:
        return [1.0] * 384


def _run(batch_size: int, workers: int, count: int):
    contents = [
        {"results": [_entry(i) for i in range(min(batch_size, count - start))]}
        for start in range(0, count, batch_size)
    ]
    session = FakeSession(contents)
    classifier = _classifier(session)
    items = [
        SourceItem(
            external_id=str(i),
            source="hackernews",
            title=f"T{i}",
            body=f"body number {i}",
            url="https://example.com",
            author="a",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            raw_payload={},
            engagement_score=1,
        )
        for i in range(count)
    ]
    repo = Repo()
    pipeline = Pipeline(
        settings=type("S", (), {"environment": "test"})(),
        connector=ListConnector(items),
        preprocessing_service=PreprocessingService(),
        repository=repo,
        embedding_service=Embedder(),
        problem_detection_service=ProblemDetectionService(classifier),
        classification_workers=workers,
        classification_batch_size=batch_size,
    )
    pipeline.run()
    return pipeline, repo, session


def test_pipeline_batches_cut_requests_and_keep_order() -> None:
    pipeline, repo, session = _run(batch_size=4, workers=1, count=10)
    assert [saved[0] for saved in repo.saved] == [str(i) for i in range(10)]
    assert len(session.requests) == 3
    stats = pipeline.last_run_stats
    assert stats is not None
    assert stats.llm_call_count == 3
    assert stats.problem_count == 10


def test_pipeline_batches_run_concurrently_in_order() -> None:
    pipeline, repo, _session = _run(batch_size=2, workers=3, count=6)
    # Concurrent requests may pop canned answers in any order, but all are valid here.
    assert [saved[0] for saved in repo.saved] == [str(i) for i in range(6)]
    assert pipeline.last_run_stats is not None
    assert pipeline.last_run_stats.llm_call_count == 3


def test_pipeline_rejects_invalid_batch_size() -> None:
    with pytest.raises(ValueError):
        Pipeline(
            settings=type("S", (), {"environment": "test"})(),
            connector=ListConnector([]),
            preprocessing_service=PreprocessingService(),
            repository=Repo(),
            embedding_service=Embedder(),
            problem_detection_service=ProblemDetectionService(_classifier(FakeSession([]))),
            classification_batch_size=0,
        )
