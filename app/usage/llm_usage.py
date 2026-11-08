"""Persisted LLM usage: tokens and estimated cost per call purpose.

Prices come from configuration (USD per million tokens) because they differ per provider and
change; with no prices configured the cost is recorded as unknown (``NULL``), never as zero.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import LlmUsageModel
from app.database.session import SessionLocal
from app.llm.client import LLMUsage


@dataclass(frozen=True)
class UsageTotals:
    purpose: str
    calls: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None


class LlmUsageRepository:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        input_usd_per_mtok: float | None = None,
        output_usd_per_mtok: float | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._input = input_usd_per_mtok
        self._output = output_usd_per_mtok

    def estimate_cost(self, usage: LLMUsage) -> float | None:
        if self._input is None or self._output is None:
            return None
        return usage.cost_usd(self._input, self._output)

    def record(self, usage: LLMUsage) -> None:
        """Usage sink for :class:`ChatCompletionsClient`."""
        with self._session_factory() as session:
            session.add(
                LlmUsageModel(
                    model=usage.model,
                    purpose=usage.purpose,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    cost_usd=self.estimate_cost(usage),
                    workspace_id=usage.workspace_id,
                )
            )
            session.commit()

    def totals(
        self, since: datetime | None = None, workspace_id: int | None = None
    ) -> tuple[UsageTotals, ...]:
        statement = select(
            LlmUsageModel.purpose,
            func.count(),
            func.coalesce(func.sum(LlmUsageModel.prompt_tokens), 0),
            func.coalesce(func.sum(LlmUsageModel.completion_tokens), 0),
            func.sum(LlmUsageModel.cost_usd),
            func.count(LlmUsageModel.cost_usd),
        ).group_by(LlmUsageModel.purpose)
        if since is not None:
            statement = statement.where(LlmUsageModel.created_at >= since)
        if workspace_id is not None:
            statement = statement.where(LlmUsageModel.workspace_id == workspace_id)
        with self._session_factory() as session:
            rows = session.execute(statement.order_by(LlmUsageModel.purpose)).all()
        return tuple(
            UsageTotals(
                purpose=purpose,
                calls=int(calls),
                prompt_tokens=int(prompt),
                completion_tokens=int(completion),
                # A purpose with any unpriced call has an incomplete (None) total.
                cost_usd=float(cost) if cost is not None and priced == calls else None,
            )
            for purpose, calls, prompt, completion, cost, priced in rows
        )
