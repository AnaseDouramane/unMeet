"""A record of every ingestion pass, so the app can show what happened without a terminal."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database.models import IngestionRunModel
from app.database.session import SessionLocal
from app.services.pipeline import PipelineRunStats


@dataclass(frozen=True)
class IngestionRun:
    source: str
    started_at: datetime
    finished_at: datetime
    status: str  # "ok" | "error"
    acquired: int = 0
    skipped: int = 0
    gated_out: int = 0
    llm_requests: int = 0
    problems: int = 0
    matched: int = 0
    errors: int = 0
    error: str | None = None
    id: int = 0
    workspace_id: int | None = None

    @classmethod
    def from_stats(
        cls,
        source: str,
        started_at: datetime,
        finished_at: datetime,
        stats: PipelineRunStats | None,
        error: str | None = None,
        workspace_id: int | None = None,
    ) -> IngestionRun:
        if stats is None:
            return cls(
                source,
                started_at,
                finished_at,
                "error",
                error=(error or "no statistics")[:500],
                workspace_id=workspace_id,
            )
        return cls(
            source,
            started_at,
            finished_at,
            "error" if error else "ok",
            acquired=stats.acquired_count,
            skipped=stats.skipped_count,
            gated_out=stats.gated_out_count,
            llm_requests=stats.llm_call_count,
            problems=stats.problem_count,
            matched=stats.matched_count,
            errors=stats.classification_error_count,
            error=error[:500] if error else None,
            workspace_id=workspace_id,
        )


class RunRecorder(Protocol):
    def record(self, run: IngestionRun) -> IngestionRun: ...


class RunReader(Protocol):
    def latest(
        self, limit: int = 10, workspace_id: int | None = None
    ) -> tuple[IngestionRun, ...]: ...


class IngestionRunRepository:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def record(self, run: IngestionRun) -> IngestionRun:
        with self._session_factory() as session:
            model = IngestionRunModel(
                source=run.source,
                started_at=run.started_at,
                finished_at=run.finished_at,
                status=run.status,
                acquired=run.acquired,
                skipped=run.skipped,
                gated_out=run.gated_out,
                llm_requests=run.llm_requests,
                problems=run.problems,
                matched=run.matched,
                errors=run.errors,
                error=run.error,
                workspace_id=run.workspace_id,
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            return _to_run(model)

    def latest(self, limit: int = 10, workspace_id: int | None = None) -> tuple[IngestionRun, ...]:
        """Newest runs; with a workspace, only its own runs and the shared ones."""
        query = select(IngestionRunModel)
        if workspace_id is not None:
            query = query.where(
                or_(
                    IngestionRunModel.workspace_id == workspace_id,
                    IngestionRunModel.workspace_id.is_(None),
                )
            )
        with self._session_factory() as session:
            models = session.scalars(
                query.order_by(
                    IngestionRunModel.started_at.desc(), IngestionRunModel.id.desc()
                ).limit(limit)
            )
            return tuple(_to_run(m) for m in models)


class InMemoryRunStore:
    def __init__(self) -> None:
        self.runs: list[IngestionRun] = []

    def record(self, run: IngestionRun) -> IngestionRun:
        from dataclasses import replace

        stored = replace(run, id=len(self.runs) + 1)
        self.runs.append(stored)
        return stored

    def latest(self, limit: int = 10, workspace_id: int | None = None) -> tuple[IngestionRun, ...]:
        runs = [
            r for r in self.runs if workspace_id is None or r.workspace_id in (None, workspace_id)
        ]
        return tuple(sorted(runs, key=lambda r: (r.started_at, r.id), reverse=True)[:limit])


def _to_run(model: IngestionRunModel) -> IngestionRun:
    return IngestionRun(
        id=model.id,
        workspace_id=model.workspace_id,
        source=model.source,
        started_at=model.started_at,
        finished_at=model.finished_at,
        status=model.status,
        acquired=model.acquired,
        skipped=model.skipped,
        gated_out=model.gated_out,
        llm_requests=model.llm_requests,
        problems=model.problems,
        matched=model.matched,
        errors=model.errors,
        error=model.error,
    )
