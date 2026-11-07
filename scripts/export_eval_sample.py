"""Export a stratified random sample of stored items for human labeling.

Each line has ``id``, ``text`` and ``category`` (the source). Annotators add
``expected_is_problem`` (true/false) to every line; the file then works with
``scripts/evaluate_problem_classifier.py --dataset``. See docs/EVALUATION.md.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

from app.database.models import SourceItemModel
from app.database.session import SessionLocal


def sample_records(
    rows: list[tuple[str, str, str]], per_source: int, seed: int
) -> list[dict[str, str]]:
    by_source: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for row in rows:
        by_source[row[0]].append(row)
    rng = random.Random(seed)
    records: list[dict[str, str]] = []
    for source in sorted(by_source):
        candidates = sorted(by_source[source], key=lambda row: row[1])
        for source_name, external_id, text in rng.sample(
            candidates, min(per_source, len(candidates))
        ):
            records.append(
                {"id": f"{source_name}:{external_id}", "text": text, "category": source_name}
            )
    rng.shuffle(records)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-source", type=int, default=100)
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()

    with SessionLocal() as session:
        rows = [
            (source, external_id, text)
            for source, external_id, text in session.execute(
                select(
                    SourceItemModel.source,
                    SourceItemModel.external_id,
                    SourceItemModel.document_text,
                ).where(SourceItemModel.document_text.is_not(None))
            )
            if text and text.strip()
        ]
    records = sample_records(rows, args.per_source, args.seed)
    args.output.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    print(f"Wrote {len(records)} records to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
