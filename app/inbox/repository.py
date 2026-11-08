"""The signal inbox of a workspace: matched signals, their state and the feedback loop.

A signal is in a workspace's inbox when the model matched it to one of the workspace's topics
(``signal_topic_matches``). Only those signals can be read or have their state changed by that
workspace, so state endpoints cannot be used to probe the rest of the corpus.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models import (
    SignalStateModel,
    SignalTopicMatchModel,
    SourceItemModel,
    TrackedTopicModel,
)
from app.database.session import SessionLocal
from app.inbox.schemas import (
    ALL_STATES,
    MAX_BULK,
    SETTABLE_STATES,
    FeedbackExample,
    InboxItem,
    InboxState,
)


class InboxStore(Protocol):
    def list_items(
        self,
        workspace_id: int,
        topic_id: int | None = None,
        state: str = "new",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[InboxItem, ...]: ...

    def counts(self, workspace_id: int) -> dict[str, int]: ...

    def get_item(self, workspace_id: int, signal_id: int) -> InboxItem | None: ...

    def set_state(
        self,
        workspace_id: int,
        signal_ids: Sequence[int],
        state: str,
        note: str | None = None,
        topic_id: int | None = None,
        user_id: int | None = None,
    ) -> int: ...

    def feedback_examples(
        self, workspace_id: int, topic_id: int, per_label: int = 3
    ) -> tuple[FeedbackExample, ...]: ...


class InboxRepository:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    # The inbox row: one per (signal, topic of this workspace) match; a signal matching several
    # topics is shown once, for the topic with the lowest id.
    def _base(self, workspace_id: int):
        first_match = (
            select(
                SignalTopicMatchModel.source_item_id.label("item_id"),
                func.min(SignalTopicMatchModel.topic_id).label("topic_id"),
            )
            .join(TrackedTopicModel, TrackedTopicModel.id == SignalTopicMatchModel.topic_id)
            .where(TrackedTopicModel.workspace_id == workspace_id)
            .group_by(SignalTopicMatchModel.source_item_id)
            .subquery()
        )
        return (
            select(
                SourceItemModel,
                TrackedTopicModel.id,
                TrackedTopicModel.name,
                SignalTopicMatchModel.reason,
                SignalStateModel.state,
                SignalStateModel.note,
                SignalStateModel.updated_at,
            )
            .select_from(first_match)
            .join(SourceItemModel, SourceItemModel.id == first_match.c.item_id)
            .join(TrackedTopicModel, TrackedTopicModel.id == first_match.c.topic_id)
            .join(
                SignalTopicMatchModel,
                and_(
                    SignalTopicMatchModel.source_item_id == first_match.c.item_id,
                    SignalTopicMatchModel.topic_id == first_match.c.topic_id,
                ),
            )
            .outerjoin(
                SignalStateModel,
                and_(
                    SignalStateModel.source_item_id == SourceItemModel.id,
                    SignalStateModel.workspace_id == workspace_id,
                ),
            )
            .where(SourceItemModel.is_problem.is_(True))
        )

    def list_items(
        self,
        workspace_id: int,
        topic_id: int | None = None,
        state: str = "new",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[InboxItem, ...]:
        if state != "all" and state not in ALL_STATES:
            raise ValueError(f"state must be one of {sorted(ALL_STATES | {'all'})}")
        statement = self._base(workspace_id)
        if topic_id is not None:
            statement = statement.where(TrackedTopicModel.id == topic_id)
        if state == "new":
            statement = statement.where(SignalStateModel.state.is_(None))
        elif state != "all":
            statement = statement.where(SignalStateModel.state == state)
        statement = (
            statement.order_by(SourceItemModel.published_at.desc(), SourceItemModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        with self._session_factory() as session:
            return tuple(_to_item(row) for row in session.execute(statement))

    def get_item(self, workspace_id: int, signal_id: int) -> InboxItem | None:
        statement = self._base(workspace_id).where(SourceItemModel.id == signal_id)
        with self._session_factory() as session:
            row = session.execute(statement).first()
            return None if row is None else _to_item(row)

    def counts(self, workspace_id: int) -> dict[str, int]:
        subquery = self._base(workspace_id).subquery()
        statement = select(subquery.c.state, func.count()).group_by(subquery.c.state)
        with self._session_factory() as session:
            found = {
                (state or "new"): int(count) for state, count in session.execute(statement)
            }
        return {state: found.get(state, 0) for state in sorted(ALL_STATES)}

    def set_state(
        self,
        workspace_id: int,
        signal_ids: Sequence[int],
        state: str,
        note: str | None = None,
        topic_id: int | None = None,
        user_id: int | None = None,
    ) -> int:
        """Set the state of signals in the inbox; return how many were updated.

        Signals that are not in this workspace's inbox are skipped, never created. ``new``
        clears the decision.
        """
        if state not in ALL_STATES:
            raise ValueError(f"state must be one of {sorted(ALL_STATES)}")
        ids = list(dict.fromkeys(signal_ids))
        if not ids or len(ids) > MAX_BULK:
            raise ValueError(f"send between 1 and {MAX_BULK} signal ids")
        with self._session_factory() as session:
            visible = {
                item.id: tid
                for item, tid, *_ in session.execute(
                    self._base(workspace_id).where(SourceItemModel.id.in_(ids))
                )
            }
            if not visible:
                return 0
            if state == "new":
                from sqlalchemy import delete

                session.execute(
                    delete(SignalStateModel).where(
                        SignalStateModel.workspace_id == workspace_id,
                        SignalStateModel.source_item_id.in_(list(visible)),
                    )
                )
            else:
                assert state in SETTABLE_STATES
                rows = [
                    {
                        "workspace_id": workspace_id,
                        "source_item_id": item_id,
                        "state": state,
                        "note": note.strip() if note and note.strip() else None,
                        "topic_id": topic_id if topic_id is not None else matched_topic,
                        "updated_by_user_id": user_id,
                        "updated_at": datetime.now(UTC),
                    }
                    for item_id, matched_topic in visible.items()
                ]
                statement = insert(SignalStateModel).values(rows)
                session.execute(
                    statement.on_conflict_do_update(
                        index_elements=["workspace_id", "source_item_id"],
                        set_={
                            "state": statement.excluded.state,
                            "note": statement.excluded.note,
                            "topic_id": statement.excluded.topic_id,
                            "updated_by_user_id": statement.excluded.updated_by_user_id,
                            "updated_at": statement.excluded.updated_at,
                        },
                    )
                )
            session.commit()
            return len(visible)

    def feedback_examples(
        self, workspace_id: int, topic_id: int, per_label: int = 3
    ) -> tuple[FeedbackExample, ...]:
        """The latest decisions of the workspace for a topic, as few-shot examples.

        ``replied`` counts as relevant: nobody replies to something they judged irrelevant.
        """
        examples: list[FeedbackExample] = []
        with self._session_factory() as session:
            for relevant, states in ((True, ("relevant", "replied")), (False, ("not_relevant",))):
                statement = (
                    select(SourceItemModel.pain_quote, SourceItemModel.title)
                    .join(SignalStateModel, SignalStateModel.source_item_id == SourceItemModel.id)
                    .where(
                        SignalStateModel.workspace_id == workspace_id,
                        SignalStateModel.topic_id == topic_id,
                        SignalStateModel.state.in_(states),
                    )
                    .order_by(SignalStateModel.updated_at.desc())
                    .limit(per_label)
                )
                for quote, title in session.execute(statement):
                    text = (quote or title or "").strip()
                    if text:
                        examples.append(FeedbackExample(text[:240], relevant))
        return tuple(examples)


def _to_item(row) -> InboxItem:
    model, topic_id, topic_name, reason, state, note, updated_at = row
    resolved: InboxState = state if state in SETTABLE_STATES else "new"  # type: ignore[assignment]
    return InboxItem(
        signal_id=model.id,
        source=model.source,
        title=model.clean_title or model.title,
        url=model.url,
        author=model.author,
        published_at=model.published_at,
        intent=model.signal_intent,
        pain_quote=model.pain_quote,
        products_mentioned=tuple(model.products_mentioned or ()),
        severity=model.signal_severity,
        topic_id=topic_id,
        topic_name=topic_name,
        relevance_reason=reason,
        state=resolved,
        note=note,
        updated_at=updated_at,
    )
