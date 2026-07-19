from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clustering.schemas import ClusterableDocument
from app.database.models import ClusterModel, ClusterRunModel, SourceItemModel
from app.database.schemas import PersistedCluster, PersistedClusterRun, PersistedSourceItem
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
    ) -> PersistedSourceItem | None:
        session = self._open_session()
        try:
            model = self._get_by_source_and_external_id(session, source, external_id)
            return None if model is None else self._to_persisted_source_item(model)
        finally:
            self._close_session(session)

    def get_by_dedup_hash(self, dedup_hash: str) -> PersistedSourceItem | None:
        session = self._open_session()
        try:
            statement = select(SourceItemModel).where(SourceItemModel.dedup_hash == dedup_hash)
            model = session.scalar(statement)
            return None if model is None else self._to_persisted_source_item(model)
        finally:
            self._close_session(session)

    def find_similar(
        self,
        embedding: Sequence[float],
        limit: int = 10,
    ) -> list[PersistedSourceItem]:
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
            models = list(session.scalars(statement).all())
            return [self._to_persisted_source_item(model) for model in models]
        finally:
            self._close_session(session)

    def find_all_with_embeddings(self) -> list[ClusterableDocument]:
        session = self._open_session()
        try:
            statement = select(SourceItemModel).where(SourceItemModel.embedding.is_not(None))
            models = list(session.scalars(statement).all())
            return [self._to_clusterable_document(model) for model in models]
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
    ) -> PersistedSourceItem:
        self._validate_published_at(source_item.published_at)
        normalized_embedding = self._normalize_embedding(embedding)
        session = self._open_session()
        try:
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
                return self._to_persisted_source_item(existing)

            model = SourceItemModel()
            self._apply_source_item(model, source_item)
            self._apply_prepared_document(model, prepared_document)
            model.embedding = normalized_embedding
            model.processed_at = datetime.now(timezone.utc)
            session.add(model)
            session.commit()
            session.refresh(model)
            return self._to_persisted_source_item(model)
        except Exception:
            session.rollback()
            raise
        finally:
            self._close_session(session)

    @staticmethod
    def _to_persisted_source_item(model: SourceItemModel) -> PersistedSourceItem:
        return PersistedSourceItem(
            id=model.id,
            external_id=model.external_id,
            source=model.source,
            raw_payload=_freeze_json(model.raw_payload),
            title=model.title,
            clean_title=model.clean_title,
            body=model.body,
            clean_body=model.clean_body,
            url=model.url,
            document_text=model.document_text,
            embedding=None
            if model.embedding is None
            else tuple(float(value) for value in model.embedding),
            dedup_hash=model.dedup_hash,
            author=model.author,
            published_at=model.published_at,
            processed_at=model.processed_at,
            engagement_score=model.engagement_score,
        )

    @staticmethod
    def _to_clusterable_document(model: SourceItemModel) -> ClusterableDocument:
        if model.embedding is None:
            raise ValueError("cannot map a source item without an embedding")
        return ClusterableDocument(
            id=model.id,
            source=model.source,
            external_id=model.external_id,
            document_text=model.document_text or "",
            embedding=tuple(float(value) for value in model.embedding),
        )

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
        if not np.isfinite(normalized).all():
            raise ValueError("embedding values must be finite")
        return normalized

    @staticmethod
    def _validate_published_at(published_at: datetime) -> None:
        if published_at.tzinfo is None or published_at.utcoffset() is None:
            raise ValueError("published_at must be timezone-aware")

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        if not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if limit <= 0:
            raise ValueError("limit must be positive")
        return limit


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


class ClusterRepository:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def create_run(self) -> int:
        session = self._session_factory()
        try:
            run = ClusterRunModel()
            session.add(run)
            session.flush()
            run_id = run.id
            session.commit()
            return run_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save(
        self,
        cluster: "DocumentCluster",
        topic_label: "TopicLabel",
        centroid: Sequence[float] | None = None,
    ) -> PersistedCluster:
        return self.save_run([(cluster, topic_label, centroid)]).clusters[0]

    def save_run(
        self,
        clusters: Sequence[tuple["DocumentCluster", "TopicLabel", Sequence[float] | None]],
    ) -> PersistedClusterRun:
        for cluster, topic_label, _ in clusters:
            self._validate_cluster(cluster, topic_label)
        session = self._session_factory()
        try:
            run = ClusterRunModel()
            session.add(run)
            session.flush()
            models = [
                self._save_cluster(session, run, cluster, topic_label, centroid, lookup_existing=False)
                for cluster, topic_label, centroid in clusters
            ]
            session.flush()
            result = PersistedClusterRun(
                id=run.id,
                clusters=tuple(self._to_persisted_cluster(model) for model in models),
            )
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save_to_run(
        self,
        run_id: int,
        cluster: "DocumentCluster",
        topic_label: "TopicLabel",
        centroid: Sequence[float] | None = None,
    ) -> PersistedCluster:
        self._validate_cluster(cluster, topic_label)
        session = self._session_factory()
        try:
            run = session.get(ClusterRunModel, run_id)
            if run is None:
                raise ValueError(f"cluster run {run_id} does not exist")
            model = self._save_cluster(session, run, cluster, topic_label, centroid, lookup_existing=True)
            session.flush()
            result = self._to_persisted_cluster(model)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _save_cluster(
        self,
        session: Session,
        run: ClusterRunModel,
        cluster: "DocumentCluster",
        topic_label: "TopicLabel",
        centroid: Sequence[float] | None,
        lookup_existing: bool,
    ) -> ClusterModel:
        normalized_centroid = self._normalize_centroid(
            centroid if centroid is not None else self._calculate_centroid(cluster)
        )
        model = None
        if lookup_existing:
            statement = select(ClusterModel).where(
                ClusterModel.run_id == run.id,
                ClusterModel.local_cluster_id == cluster.cluster_id,
            )
            model = session.scalar(statement)
        if model is None:
            model = ClusterModel(run_id=run.id, local_cluster_id=cluster.cluster_id)
            session.add(model)
        model.label = topic_label.label
        model.keywords = list(topic_label.keywords)
        model.centroid = normalized_centroid
        model.document_count = len(cluster.documents)
        model.source_items = self._source_items_for_documents(session, cluster.documents)
        return model

    @staticmethod
    def _source_items_for_documents(
        session: Session,
        documents: tuple[ClusterableDocument, ...],
    ) -> list[SourceItemModel]:
        document_ids = [document.id for document in documents]
        statement = select(SourceItemModel).where(SourceItemModel.id.in_(document_ids))
        models_by_id = {model.id: model for model in session.scalars(statement).all()}
        if len(models_by_id) != len(document_ids):
            raise ValueError("one or more cluster documents do not exist")
        return [models_by_id[document_id] for document_id in document_ids]

    @staticmethod
    def _to_persisted_cluster(model: ClusterModel) -> PersistedCluster:
        return PersistedCluster(
            id=model.id,
            run_id=model.run_id,
            local_cluster_id=model.local_cluster_id,
        )

    @staticmethod
    def _validate_cluster(cluster: "DocumentCluster", topic_label: "TopicLabel") -> None:
        if not cluster.documents:
            raise ValueError("cannot persist an empty cluster")
        if cluster.cluster_id != topic_label.cluster_id:
            raise ValueError("cluster and topic label ids must match")

    @staticmethod
    def _calculate_centroid(cluster: "DocumentCluster") -> list[float]:
        embeddings = [document.embedding for document in cluster.documents]
        return np.mean(np.asarray(embeddings, dtype=float), axis=0).tolist()

    @staticmethod
    def _normalize_centroid(centroid: Sequence[float]) -> list[float]:
        if isinstance(centroid, (str, bytes)):
            raise TypeError("centroid must be a sequence of 384 floats")
        normalized = [float(value) for value in centroid]
        if len(normalized) != 384:
            raise ValueError("centroid must contain exactly 384 values")
        if not np.isfinite(normalized).all():
            raise ValueError("centroid values must be finite")
        return normalized
