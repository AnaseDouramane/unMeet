from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import SourceItemModel
from app.database.session import SessionLocal


@dataclass(frozen=True)
class ProblemClassification:
    source: str
    external_id: str
    is_problem: bool
    confidence: float
    reason: str
    classifier: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.external_id)


@dataclass(frozen=True)
class ImportReport:
    imported: int = 0
    skipped: int = 0
    missing: int = 0
    errors: int = 0


def load_classifications(path: Path) -> list[ProblemClassification]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"Impossibile leggere il file '{path}': {error}") from error

    if not lines:
        raise ValueError("Il file JSONL è vuoto")

    classifications: list[ProblemClassification] = []
    seen: dict[tuple[str, str], ProblemClassification] = {}
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise ValueError(f"Record non valido alla riga {line_number}: riga vuota")
        try:
            record = json.loads(line, object_pairs_hook=_reject_duplicate_json_keys)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"JSON non valido alla riga {line_number}: {error.msg}"
            ) from error
        classification = _parse_classification(record, line_number)
        previous = seen.get(classification.key)
        if previous is not None:
            if previous != classification:
                raise ValueError(
                    "Duplicato contraddittorio alla riga "
                    f"{line_number}: source='{classification.source}', "
                    f"external_id='{classification.external_id}'"
                )
            continue
        seen[classification.key] = classification
        classifications.append(classification)
    return classifications


def import_classifications(
    classifications: list[ProblemClassification],
    *,
    overwrite: bool = False,
    dry_run: bool = False,
    session_factory: Callable[[], Session] = SessionLocal,
) -> ImportReport:
    session = session_factory()
    imported = skipped = missing = 0
    try:
        for classification in classifications:
            model = session.scalar(
                select(SourceItemModel).where(
                    SourceItemModel.source == classification.source,
                    SourceItemModel.external_id == classification.external_id,
                )
            )
            if model is None:
                missing += 1
                continue
            if model.is_problem is not None and not overwrite:
                skipped += 1
                continue

            model.is_problem = classification.is_problem
            model.problem_confidence = classification.confidence
            model.problem_reason = classification.reason
            model.problem_classifier = classification.classifier
            model.classified_at = datetime.now(timezone.utc)
            if not classification.is_problem:
                model.embedding = None
                model.embedding_model = None
            imported += 1

        if dry_run:
            session.rollback()
        else:
            session.commit()
        return ImportReport(imported=imported, skipped=skipped, missing=missing)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def format_report(report: ImportReport) -> str:
    return (
        f"Importati: {report.imported}\n"
        f"Saltati: {report.skipped}\n"
        f"Mancanti: {report.missing}\n"
        f"Errori: {report.errors}"
    )


def _parse_classification(record: object, line_number: int) -> ProblemClassification:
    if not isinstance(record, dict):
        raise ValueError(f"Record non valido alla riga {line_number}: atteso un oggetto JSON")
    required_fields = {"source", "external_id", "is_problem", "confidence", "reason", "classifier"}
    if set(record) != required_fields:
        raise ValueError(
            f"Record non valido alla riga {line_number}: campi richiesti esattamente "
            "source, external_id, is_problem, confidence, reason, classifier"
        )

    source = _required_text(record["source"], "source", line_number)
    external_id = _required_text(record["external_id"], "external_id", line_number)
    reason = _required_text(record["reason"], "reason", line_number)
    classifier = _required_text(record["classifier"], "classifier", line_number)
    is_problem = record["is_problem"]
    if not isinstance(is_problem, bool):
        raise ValueError(f"Record non valido alla riga {line_number}: is_problem deve essere booleano")
    confidence = record["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError(f"Record non valido alla riga {line_number}: confidence deve essere un numero")
    normalized_confidence = float(confidence)
    if not math.isfinite(normalized_confidence) or not 0 <= normalized_confidence <= 1:
        raise ValueError(
            f"Record non valido alla riga {line_number}: confidence deve essere finito e tra 0 e 1"
        )
    return ProblemClassification(
        source=source,
        external_id=external_id,
        is_problem=is_problem,
        confidence=normalized_confidence,
        reason=reason,
        classifier=classifier,
    )


def _required_text(value: object, field_name: str, line_number: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Record non valido alla riga {line_number}: {field_name} deve essere una stringa non vuota"
        )
    return value.strip()


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    record: dict[str, object] = {}
    for key, value in pairs:
        if key in record:
            raise ValueError(f"Chiave JSON duplicata: '{key}'")
        record[key] = value
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importa classificazioni offline del problem detector da JSONL."
    )
    parser.add_argument("input_path", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        classifications = load_classifications(args.input_path)
        report = import_classifications(
            classifications,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
    except ValueError as error:
        print(format_report(ImportReport(errors=1)))
        print(f"Errore: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(format_report(ImportReport(errors=1)))
        print(f"Errore: {error}", file=sys.stderr)
        return 1

    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
