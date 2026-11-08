"""Print LLM tokens and estimated cost per purpose (classification, cluster_labeling, ...)."""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, time

from app.usage.llm_usage import LlmUsageRepository


def main(argv: list[str]) -> int:
    since = None
    if argv:
        try:
            since = datetime.combine(date.fromisoformat(argv[0]), time.min, tzinfo=UTC)
        except ValueError:
            print("usage: python -m scripts.llm_cost_report [YYYY-MM-DD]", file=sys.stderr)
            return 2
    totals = LlmUsageRepository().totals(since)
    if not totals:
        print("No LLM usage recorded.")
        return 0
    for item in totals:
        cost = (
            "unknown (set LLM_*_USD_PER_MTOK)" if item.cost_usd is None else f"${item.cost_usd:.4f}"
        )
        print(
            f"{item.purpose}: {item.calls} calls, {item.prompt_tokens} prompt + "
            f"{item.completion_tokens} completion tokens, cost {cost}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
