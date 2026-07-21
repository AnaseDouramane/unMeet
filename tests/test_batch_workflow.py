from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from app.database.schemas import PersistedSourceItem
from app.ingestion.schemas import SourceItem
from app.services.ingestion_only import IngestionOnlyService
from scripts.colab_classify_qwen import classify_file
from scripts.embed_classified_problems import embed_classified_problems


@dataclass
class FakeConnector:
    items: list[SourceItem]
    source: str = "reddit"

    def fetch(self):
        return iter(self.items)


class FakePreprocessor:
    def prepare(self, item):
        return object()


class FakeNewOnlyRepository:
    def __init__(self) -> None:
        self.seen = {("reddit", "already-classified")}
        self.saved = []

    def save_unclassified_if_new(self, item, prepared) -> bool:
        key = (item.source, item.external_id)
        if key in self.seen:
            return False
        self.seen.add(key)
        self.saved.append(key)
        return True


def _item(external_id: str) -> SourceItem:
    return SourceItem(
        source="reddit", external_id=external_id, title="title", body="body", url="https://x",
        author=None, published_at=datetime.now(timezone.utc), engagement_score=None, raw_payload=None,
    )


def test_ingestion_only_does_not_reclassify_existing_records() -> None:
    repository = FakeNewOnlyRepository()
    service = IngestionOnlyService(FakePreprocessor(), repository)

    stats = service.run(FakeConnector([_item("already-classified"), _item("new")]))

    assert stats.acquired_count == 2
    assert stats.new_count == 1
    assert stats.existing_count == 1
    assert repository.saved == [("reddit", "new")]


class FakeClassifier:
    classifier_name = "Qwen3ProblemClassifier:Qwen/Qwen3-0.6B"

    def classify(self, text):
        from app.problem_detection.schemas import ProblemDetectionResult

        return ProblemDetectionResult(True, 0.9, "pain", self.classifier_name)


def test_colab_classifier_resumes_using_source_and_external_id(tmp_path) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    input_path.write_text(
        '{"source":"reddit","external_id":"1","document_text":"first"}\n'
        '{"source":"reddit","external_id":"2","document_text":"second"}\n', encoding="utf-8"
    )
    output_path.write_text(
        '{"source":"reddit","external_id":"1","is_problem":false,"confidence":0.5,'
        '"reason":"done","classifier_name":"qwen"}\n', encoding="utf-8"
    )

    assert classify_file(input_path, output_path, FakeClassifier()) == 1
    assert len(output_path.read_text(encoding="utf-8").splitlines()) == 2


def _output_record(**overrides) -> dict[str, object]:
    record: dict[str, object] = {
        "source": "reddit",
        "external_id": "1",
        "is_problem": True,
        "confidence": 0.9,
        "reason": "pain",
        "classifier_name": "qwen",
    }
    record.update(overrides)
    return record


def _record_without_classifier_name() -> dict[str, object]:
    record = _output_record()
    del record["classifier_name"]
    return record


class CountingClassifier(FakeClassifier):
    def __init__(self) -> None:
        self.calls = 0

    def classify(self, text):
        self.calls += 1
        return super().classify(text)


@pytest.mark.parametrize(
    "lines, message",
    [
        (["not json"], "JSON non valido alla riga 1"),
        ([json.dumps(_record_without_classifier_name())], "classifier_name"),
        ([json.dumps(_output_record(extra="no"))], "campi richiesti"),
        ([json.dumps(_output_record(is_problem="true"))], "is_problem"),
        ([json.dumps(_output_record(confidence=2.0))], "confidence"),
        ([json.dumps(_output_record()), json.dumps(_output_record())], "Duplicate record"),
        ([json.dumps(_output_record()), json.dumps(_output_record(is_problem=False))], "Duplicate record"),
    ],
)
def test_colab_resume_rejects_invalid_or_duplicate_existing_output(
    tmp_path, lines, message
) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    input_path.write_text(
        '{"source":"reddit","external_id":"2","document_text":"new"}\n', encoding="utf-8"
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    classifier = CountingClassifier()

    with pytest.raises(ValueError, match=message):
        classify_file(input_path, output_path, classifier)

    assert classifier.calls == 0


class FakeEmbeddingRepository:
    def __init__(self) -> None:
        self.saved = []

    def find_classified_problems_without_embeddings(self):
        return [
            PersistedSourceItem(1, "1", "reddit", None, "", None, "", None, "", "text", True,
                                None, None, None, None, None, None, None, datetime.now(timezone.utc), None, None, None)
        ]

    def save_embedding(self, source_item_id, embedding, embedding_model):
        self.saved.append((source_item_id, embedding_model))


class FakeEmbeddingService:
    model_name = "test-model"

    def encode(self, text):
        return [0.1] * 384


def test_embedding_job_only_persists_selected_positive_documents() -> None:
    repository = FakeEmbeddingRepository()
    report = embed_classified_problems(repository, FakeEmbeddingService())

    assert report.selected == 1
    assert report.embedded == 1
    assert repository.saved == [(1, "test-model")]
