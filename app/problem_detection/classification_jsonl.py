"""Shared, strict JSONL contract for offline problem classifications."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass


CLASSIFICATION_FIELDS = frozenset(
    {"source", "external_id", "is_problem", "confidence", "reason", "classifier_name"}
)


class ClassificationJsonlError(ValueError):
    pass


@dataclass(frozen=True)
class ClassificationJsonlRecord:
    source: str
    external_id: str
    is_problem: bool
    confidence: float
    reason: str
    classifier_name: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.external_id)


def parse_classification_json_line(line: str, line_number: int) -> ClassificationJsonlRecord:
    if not line.strip():
        raise ClassificationJsonlError(f"Record non valido alla riga {line_number}: riga vuota")
    try:
        record = json.loads(line, object_pairs_hook=_reject_duplicate_json_keys)
    except ClassificationJsonlError:
        raise
    except json.JSONDecodeError as error:
        raise ClassificationJsonlError(
            f"JSON non valido alla riga {line_number}: {error.msg}"
        ) from error
    return parse_classification_record(record, line_number)


def parse_classification_record(record: object, line_number: int) -> ClassificationJsonlRecord:
    if not isinstance(record, dict):
        raise ClassificationJsonlError(
            f"Record non valido alla riga {line_number}: atteso un oggetto JSON"
        )
    key_context = _key_context(record)
    if set(record) != CLASSIFICATION_FIELDS:
        raise ClassificationJsonlError(
            f"Record non valido alla riga {line_number}{key_context}: campi richiesti esattamente "
            "source, external_id, is_problem, confidence, reason, classifier_name"
        )
    source = _required_text(record["source"], "source", line_number, key_context)
    external_id = _required_text(record["external_id"], "external_id", line_number, key_context)
    key_context = f" (source='{source}', external_id='{external_id}')"
    reason = _required_text(record["reason"], "reason", line_number, key_context)
    classifier_name = _required_text(
        record["classifier_name"], "classifier_name", line_number, key_context
    )
    is_problem = record["is_problem"]
    if not isinstance(is_problem, bool):
        raise ClassificationJsonlError(
            f"Record non valido alla riga {line_number}{key_context}: is_problem deve essere booleano"
        )
    confidence = record["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ClassificationJsonlError(
            f"Record non valido alla riga {line_number}{key_context}: confidence deve essere un numero"
        )
    normalized_confidence = float(confidence)
    if not math.isfinite(normalized_confidence) or not 0 <= normalized_confidence <= 1:
        raise ClassificationJsonlError(
            f"Record non valido alla riga {line_number}{key_context}: "
            "confidence deve essere finito e tra 0 e 1"
        )
    return ClassificationJsonlRecord(
        source=source,
        external_id=external_id,
        is_problem=is_problem,
        confidence=normalized_confidence,
        reason=reason,
        classifier_name=classifier_name,
    )


def _key_context(record: dict[object, object]) -> str:
    source, external_id = record.get("source"), record.get("external_id")
    if isinstance(source, str) and source.strip() and isinstance(external_id, str) and external_id.strip():
        return f" (source='{source.strip()}', external_id='{external_id.strip()}')"
    return ""


def _required_text(value: object, field_name: str, line_number: int, key_context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClassificationJsonlError(
            f"Record non valido alla riga {line_number}{key_context}: "
            f"{field_name} deve essere una stringa non vuota"
        )
    return value.strip()


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    record: dict[str, object] = {}
    for key, value in pairs:
        if key in record:
            raise ClassificationJsonlError(f"Chiave JSON duplicata: '{key}'")
        record[key] = value
    return record
