from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import SourceItemModel
from app.database.session import SessionLocal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "problem_detection_input.jsonl"


def export_unclassified_documents(
    output_path: Path = DEFAULT_OUTPUT_PATH,
    session_factory: Callable[[], Session] = SessionLocal,
) -> int:
    """Export unclassified documents in a Colab-safe JSONL format."""
    statement = (
        select(
            SourceItemModel.source,
            SourceItemModel.external_id,
            SourceItemModel.document_text,
        )
        .where(SourceItemModel.is_problem.is_(None))
        .order_by(SourceItemModel.source, SourceItemModel.external_id)
    )
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for record in records:
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(records)


def main() -> int:
    count = export_unclassified_documents()
    print(f"Esportati: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
