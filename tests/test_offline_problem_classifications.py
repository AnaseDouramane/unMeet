from __future__ import annotations

import json
import sys
from datetime import timezone
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from app.database.models import SourceItemModel
from scripts import export_unclassified_documents as export_module
from scripts.export_unclassified_documents import ExportError, export_unclassified_documents
from scripts.import_problem_classifications import (
    ProblemClassification,
    import_classifications,
    load_classifications,
)


class FakeExportSession:
    def __init__(self, rows: list[tuple[str, str, str | None]]) -> None:
        self.rows = rows
        self.statement = None
        self.closed = False

    def execute(self, statement):
        self.statement = statement
        return self.rows

    def close(self) -> None:
        self.closed = True


class FakeImportSession:
    def __init__(self, models: dict[tuple[str, str], SourceItemModel]) -> None:
        self.models = models
        self.committed = 0
        self.rolled_back = 0
        self.closed = False
        self.statements = []

    def scalar(self, statement):
        self.statements.append(statement)
        params = statement.compile().params
        return self.models.get((params["source_1"], params["external_id_1"]))

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1

    def close(self) -> None:
        self.closed = True


def test_export_writes_only_unclassified_documents_in_deterministic_order(tmp_path: Path) -> None:
    session = FakeExportSession(
        [("hackernews", "10", "second"), ("reddit", "2", "first")]
    )
    output_path = tmp_path / "data" / "problem_detection_input.jsonl"

    count = export_unclassified_documents(output_path, session_factory=lambda: session)

    assert count == 2
    assert [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()] == [
        {"source": "hackernews", "external_id": "10", "document_text": "second"},
        {"source": "reddit", "external_id": "2", "document_text": "first"},
    ]
    sql = str(session.statement.compile(dialect=postgresql.dialect())).lower()
    assert "source_items.is_problem is null" in sql
    assert "order by source_items.source, source_items.external_id" in sql
    assert "raw_payload" not in sql
    assert "embedding" not in sql
    assert session.closed is True


def test_load_classifications_rejects_contradictory_duplicates(tmp_path: Path) -> None:
    input_path = tmp_path / "results.jsonl"
    input_path.write_text(
        '{"source":"reddit","external_id":"1","is_problem":true,"confidence":0.9,'
        '"reason":"Pain","classifier_name":"qwen-colab"}\n'
        '{"source":"reddit","external_id":"1","is_problem":false,"confidence":0.9,'
        '"reason":"News","classifier_name":"qwen-colab"}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicato contraddittorio"):
        load_classifications(input_path)


def test_load_classifications_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    input_path = tmp_path / "results.jsonl"
    input_path.write_text(
        '{"source":"reddit","source":"hackernews","external_id":"1",'
        '"is_problem":true,"confidence":0.9,"reason":"Pain","classifier_name":"qwen-colab"}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Chiave JSON duplicata"):
        load_classifications(input_path)


@pytest.mark.parametrize(
    "record, message",
    [
        ({}, "campi richiesti"),
        (
            {
                "source": "reddit",
                "external_id": "1",
                "is_problem": "true",
                "confidence": 0.9,
                "reason": "Pain",
                "classifier_name": "qwen-colab",
            },
            "is_problem",
        ),
        (
            {
                "source": "reddit",
                "external_id": "1",
                "is_problem": True,
                "confidence": 1.1,
                "reason": "Pain",
                "classifier_name": "qwen-colab",
            },
            "confidence",
        ),
    ],
)
def test_load_classifications_validates_records(
    tmp_path: Path, record: dict[str, object], message: str
) -> None:
    input_path = tmp_path / "results.jsonl"
    input_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_classifications(input_path)


def test_import_updates_only_unclassified_records_without_embeddings() -> None:
    unclassified = SourceItemModel(source="reddit", external_id="1", is_problem=None)
    already_classified = SourceItemModel(source="reddit", external_id="2", is_problem=True)
    session = FakeImportSession(
        {("reddit", "1"): unclassified, ("reddit", "2"): already_classified}
    )
    classifications = [
        ProblemClassification("reddit", "1", True, 0.91, "Repeated manual work", "qwen-colab"),
        ProblemClassification("reddit", "2", False, 0.80, "News", "qwen-colab"),
        ProblemClassification("reddit", "3", False, 0.70, "Missing", "qwen-colab"),
    ]

    report = import_classifications(classifications, session_factory=lambda: session)

    assert report.imported == 1
    assert report.skipped == 1
    assert report.missing == 1
    assert report.errors == 0
    assert unclassified.is_problem is True
    assert unclassified.problem_confidence == 0.91
    assert unclassified.problem_reason == "Repeated manual work"
    assert unclassified.problem_classifier == "qwen-colab"
    assert unclassified.classified_at is not None
    assert unclassified.classified_at.tzinfo == timezone.utc
    assert unclassified.embedding is None
    assert unclassified.embedding_model is None
    assert already_classified.is_problem is True
    assert session.committed == 1
    assert session.closed is True


def test_import_supports_overwrite_and_dry_run() -> None:
    model = SourceItemModel(source="reddit", external_id="1", is_problem=True)
    model.embedding = [0.1] * 384
    model.embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
    session = FakeImportSession({("reddit", "1"): model})
    classification = ProblemClassification("reddit", "1", False, 0.8, "News", "qwen-colab")

    report = import_classifications(
        [classification], overwrite=True, dry_run=True, session_factory=lambda: session
    )

    assert report.imported == 1
    assert model.is_problem is False
    assert model.embedding is None
    assert model.embedding_model is None
    assert session.committed == 0
    assert session.rolled_back == 1


def test_export_writes_an_empty_jsonl_file(tmp_path: Path) -> None:
    output_path = tmp_path / "empty.jsonl"

    count = export_unclassified_documents(
        output_path, session_factory=lambda: FakeExportSession([])
    )

    assert count == 0
    assert output_path.read_text(encoding="utf-8") == ""


def test_export_rejects_a_directory_output(tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="directory"):
        export_unclassified_documents(tmp_path, session_factory=lambda: FakeExportSession([]))


def test_export_reports_parent_directory_creation_errors(tmp_path: Path, monkeypatch) -> None:
    output_path = tmp_path / "blocked" / "output.jsonl"

    def fail_mkdir(self, *args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    with pytest.raises(ExportError, match="directory padre"):
        export_unclassified_documents(output_path, session_factory=lambda: FakeExportSession([]))


def test_export_cleans_temporary_file_after_write_error(tmp_path: Path, monkeypatch) -> None:
    output_path = tmp_path / "output.jsonl"

    def fail_fsync(descriptor):
        raise OSError("disk error")

    monkeypatch.setattr(export_module.os, "fsync", fail_fsync)

    with pytest.raises(ExportError, match="Impossibile scrivere"):
        export_unclassified_documents(
            output_path, session_factory=lambda: FakeExportSession([("reddit", "1", "text")])
        )

    assert not output_path.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_export_main_reports_filesystem_errors_without_traceback(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "argv", ["export_unclassified_documents", "--output", str(tmp_path)])

    assert export_module.main() == 1

    captured = capsys.readouterr()
    assert "Errore export" in captured.err
    assert "Traceback" not in captured.err
