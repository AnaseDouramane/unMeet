from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from app.analytics.schemas import AnalyticsResult, ClusterRankingItem, TimeSeriesGranularity
from app.database.repository import SourceItemRepository
from app.embeddings.embedding_service import EmbeddingService


class DatabaseUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class PublicDocument:
    id: int
    source: str
    title: str
    body: str
    url: str
    author: str | None
    published_at: datetime
    problem_confidence: float


@dataclass(frozen=True)
class ClusterDetail:
    cluster: ClusterRankingItem
    documents: tuple[PublicDocument, ...]


class AnalyticsReadFacade(Protocol):
    def get_analytics(self, period: TimeSeriesGranularity) -> AnalyticsResult: ...

    def get_opportunities(self) -> Sequence[ClusterRankingItem]: ...

    def get_clusters(self) -> Sequence[ClusterRankingItem]: ...

    def get_cluster(self, cluster_id: int) -> ClusterDetail | None: ...


class SemanticSearch(Protocol):
    def search(self, query: str, limit: int) -> Sequence[PublicDocument]: ...


class UnavailableAnalyticsReadFacade:
    """Default until an application composition supplies persisted read snapshots."""

    @staticmethod
    def _raise() -> None:
        raise DatabaseUnavailableError("analytics read data is unavailable")

    def get_analytics(self, period: TimeSeriesGranularity) -> AnalyticsResult:
        self._raise()

    def get_opportunities(self) -> Sequence[ClusterRankingItem]:
        self._raise()

    def get_clusters(self) -> Sequence[ClusterRankingItem]:
        self._raise()

    def get_cluster(self, cluster_id: int) -> ClusterDetail | None:
        self._raise()


class RepositorySemanticSearch:
    def __init__(self, embedding_service: EmbeddingService, repository: SourceItemRepository) -> None:
        self._embedding_service = embedding_service
        self._repository = repository

    def search(self, query: str, limit: int) -> Sequence[PublicDocument]:
        try:
            embedding = self._embedding_service.encode(query)
            documents = self._repository.find_similar(
                embedding,
                self._embedding_service.model_name,
                limit,
            )
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError("database is unavailable") from error
        return tuple(
            PublicDocument(
                id=document.id,
                source=document.source,
                title=document.title,
                body=document.body,
                url=document.url,
                author=document.author,
                published_at=document.published_at,
                problem_confidence=document.problem_confidence or 0.0,
            )
            for document in documents
            if document.is_problem is True
        )


@dataclass(frozen=True)
class ApiDependencies:
    analytics_reader: AnalyticsReadFacade
    semantic_search: SemanticSearch


def build_default_dependencies(embedding_model: str) -> ApiDependencies:
    return ApiDependencies(
        analytics_reader=UnavailableAnalyticsReadFacade(),
        semantic_search=RepositorySemanticSearch(
            EmbeddingService(embedding_model),
            SourceItemRepository(),
        ),
    )


def get_dependencies(request: Request) -> ApiDependencies:
    return request.app.state.dependencies
