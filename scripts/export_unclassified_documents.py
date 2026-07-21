from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import SourceItemModel
from app.database.session import SessionLocal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "problem_detection_input.jsonl"


class ExportError(ValueError):
    """A filesystem error that can be presented safely by the CLI."""


def export_unclassified_documents(
    output_path: Path = DEFAULT_OUTPUT_PATH,
    limit: int | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
) -> int:
    """Export unclassified documents in a Colab-safe JSONL format."""
    _validate_output_path(output_path)
    statement = (
        select(
            SourceItemModel.source,
            SourceItemModel.external_id,
            SourceItemModel.document_text,
        )
        .where(SourceItemModel.is_problem.is_(None))
        .order_by(SourceItemModel.source, SourceItemModel.external_id)
    )
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0):
        raise ValueError("limit must be a positive integer")
    if limit is not None:
        statement = statement.limit(limit)
    session = session_factory()
    try:
        rows = session.execute(statement)
        records = [
            {
                "source": source,
                "external_id": external_id,
                "document_text": document_text,
            }
            for source, external_id, document_text in rows
        ]
    finally:
        session.close()

    _write_jsonl_atomically(output_path, records)
    return len(records)


def _validate_output_path(output_path: Path) -> None:
    try:
        if output_path.exists() and output_path.is_dir():
            raise ExportError(f"Il percorso di output è una directory: '{output_path}'")
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except ExportError:
        raise
    except OSError as error:
        raise ExportError(
            f"Impossibile creare la directory padre dell'output '{output_path.parent}': {error}"
        ) from error


def _write_jsonl_atomically(output_path: Path, records: list[dict[str, object]]) -> None:
    temporary_path: Path | None = None
    descriptor: int | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output_file:
            descriptor = None
            for record in records:
                output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temporary_path, output_path)
    except OSError as error:
        raise ExportError(f"Impossibile scrivere l'export '{output_path}': {error}") from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Esporta documenti non classificati in JSONL.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    try:
        count = export_unclassified_documents(args.output, limit=args.limit)
    except (ExportError, ValueError) as error:
        print(f"Errore export: {error}", file=sys.stderr)
        return 1
    print(f"Esportati: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
