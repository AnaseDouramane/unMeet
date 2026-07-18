from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import SourceItemModel
from app.database.session import SessionLocal
from app.ingestion.schemas import SourceItem
from app.preprocessing.schemas import PreparedDocument


class SourceItemRepository:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def _open_session(self) -> Session:
        return self._session_factory()

    def _close_session(self, session: Session) -> None:
        session.close()

    def _get_by_source_and_external_id(
        self,
        session: Session,
        source: str,
        external_id: str,
    ) -> SourceItemModel | None:
        statement = select(SourceItemModel).where(
            SourceItemModel.source == source,
            SourceItemModel.external_id == external_id,
        )
        return session.scalar(statement)

    def get_by_source_and_external_id(
        self,
        source: str,
        external_id: str,
    ) -> SourceItemModel | None:
        session = self._open_session()
        try:
            return self._get_by_source_and_external_id(session, source, external_id)
        finally:
            self._close_session(session)

    def get_by_dedup_hash(self, dedup_hash: str) -> SourceItemModel | None:
        session = self._open_session()
        try:
            statement = select(SourceItemModel).where(SourceItemModel.dedup_hash == dedup_hash)
            return session.scalar(statement)
        finally:
            self._close_session(session)

    def find_similar(self, embedding: Sequence[float], limit: int = 10) -> list[SourceItemModel]:
        normalized_embedding = self._normalize_embedding(embedding)
        normalized_limit = self._normalize_limit(limit)

        session = self._open_session()
        try:
            statement = (
                select(SourceItemModel)
                .where(SourceItemModel.embedding.is_not(None))
                .order_by(SourceItemModel.embedding.cosine_distance(normalized_embedding))
                .limit(normalized_limit)
            )
            return list(session.scalars(statement).all())
        finally:
            self._close_session(session)

    def find_all_with_embeddings(self) -> list[SourceItemModel]:
        session = self._open_session()
        try:
            statement = select(SourceItemModel).where(SourceItemModel.embedding.is_not(None))
            return list(session.scalars(statement).all())
        finally:
            self._close_session(session)

    def exists_by_source_and_external_id(self, source: str, external_id: str) -> bool:
        return self.get_by_source_and_external_id(source, external_id) is not None

    def exists_by_dedup_hash(self, dedup_hash: str) -> bool:
        return self.get_by_dedup_hash(dedup_hash) is not None

    def save(
        self,
        source_item: SourceItem,
        prepared_document: PreparedDocument,
        embedding: Sequence[float] | None = None,
    ) -> SourceItemModel:
        session = self._open_session()
        try:
            normalized_embedding = self._normalize_embedding(embedding)
            existing = self._get_by_source_and_external_id(
                session,
                source_item.source,
                source_item.external_id,
            )
            if existing is not None:
                self._apply_source_item(existing, source_item)
                self._apply_prepared_document(existing, prepared_document)
                if normalized_embedding is not None:
                    existing.embedding = normalized_embedding
                existing.processed_at = datetime.now(timezone.utc)
                session.commit()
                session.refresh(existing)
                return existing

            model = SourceItemModel()
            self._apply_source_item(model, source_item)
            self._apply_prepared_document(model, prepared_document)
            model.embedding = normalized_embedding
            model.processed_at = datetime.now(timezone.utc)
            session.add(model)
            session.commit()
            session.refresh(model)
            return model
        except Exception:
            session.rollback()
            raise
        finally:
            self._close_session(session)

    def _apply_source_item(self, model: SourceItemModel, source_item: SourceItem) -> None:
        model.external_id = source_item.external_id
        model.source = source_item.source
        model.raw_payload = source_item.raw_payload
        model.title = source_item.title
        model.body = source_item.body
        model.url = source_item.url
        model.author = source_item.author
        model.published_at = source_item.published_at
        model.engagement_score = source_item.engagement_score

    def _apply_prepared_document(
        self,
        model: SourceItemModel,
        prepared_document: PreparedDocument,
    ) -> None:
        model.clean_title = prepared_document.title
        model.clean_body = prepared_document.body
        model.document_text = prepared_document.document_text
        model.dedup_hash = prepared_document.dedup_hash

    @staticmethod
    def _normalize_embedding(embedding: Sequence[float] | None) -> list[float] | None:
        if embedding is None:
            return None
        if isinstance(embedding, (str, bytes)):
            raise TypeError("embedding must be a sequence of 384 floats")

        normalized = [float(value) for value in embedding]
        if len(normalized) != 384:
            raise ValueError("embedding must contain exactly 384 values")
        return normalized

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        if not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if limit <= 0:
            raise ValueError("limit must be positive")
        return limit
