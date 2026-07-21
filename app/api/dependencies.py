from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from app.analytics.schemas import (
    AnalyticsResult,
    ClusterRankingItem,
    DashboardSummary,
    SourceProblemCount,
    TimeSeriesGranularity,
    TrendDistribution,
)
from app.analytics.service import AnalyticsService
from app.database.repository import ClusterRepository, SourceItemRepository
from app.embeddings.embedding_service import EmbeddingService
from app.opportunities.ranking import OpportunityClusterInput, OpportunityRankingService


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


class EmptyAnalyticsReadFacade:
    """Default reader for a valid database with no analytics data yet."""

    @staticmethod
    def _empty_result() -> AnalyticsResult:
        return AnalyticsResult(
            summary=DashboardSummary(0, 0, 0, 0, 0, 0, 0, None, None),
            top_opportunities=(),
            source_breakdown=(),
            trend_distribution=TrendDistribution(0, 0, 0, 0),
            time_series=(),
        )

    def get_analytics(self, period: TimeSeriesGranularity) -> AnalyticsResult:
        return self._empty_result()

    def get_opportunities(self) -> Sequence[ClusterRankingItem]:
        return ()

    def get_clusters(self) -> Sequence[ClusterRankingItem]:
        return ()

    def get_cluster(self, cluster_id: int) -> ClusterDetail | None:
        return None


class RepositoryAnalyticsReadFacade:
    """Read persisted analytics data, preserving empty analysis runs."""

    def __init__(
        self,
        cluster_repository: ClusterRepository,
        source_item_repository: SourceItemRepository,
        analytics_service: AnalyticsService | None = None,
    ) -> None:
        self._cluster_repository = cluster_repository
        self._source_item_repository = source_item_repository
        self._analytics_service = analytics_service or AnalyticsService()
        self._opportunity_ranking_service = OpportunityRankingService()

    def get_analytics(self, period: TimeSeriesGranularity) -> AnalyticsResult:
        try:
            latest_run = self._cluster_repository.find_latest_run()
            if latest_run is None:
                return EmptyAnalyticsReadFacade._empty_result()
            source_problem_counts = tuple(
                SourceProblemCount(source, problem_count)
                for source, problem_count in self._source_item_repository.count_problems_by_source()
            )
            clusters = self._cluster_repository.get_clusters_for_run(latest_run.id)
            trends = self._cluster_repository.get_trends_for_run(latest_run.id)
            rankings = ()
            if clusters:
                statistics_by_cluster_id = {
                    item.cluster_id: item
                    for item in self._cluster_repository.get_opportunity_statistics_for_run(
                        latest_run.id
                    )
                }
                ranking_inputs = tuple(
                    OpportunityClusterInput(
                        cluster_id=cluster.id,
                        label=cluster.label,
                        keywords=cluster.keywords,
                        document_count=cluster.document_count,
                        source_count=statistics_by_cluster_id[cluster.id].source_count,
                        average_problem_confidence=(
                            statistics_by_cluster_id[cluster.id].average_problem_confidence
                        ),
                    )
                    for cluster in clusters
                )
                rankings = self._opportunity_ranking_service.rank(ranking_inputs, trends)
            return self._analytics_service.build(
                latest_run,
                clusters,
                trends,
                rankings,
                source_problem_counts,
                (),
                period,
            )
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError("database is unavailable") from error

    def get_opportunities(self) -> Sequence[ClusterRankingItem]:
        return self.get_analytics(TimeSeriesGranularity.DAY).top_opportunities

    def get_clusters(self) -> Sequence[ClusterRankingItem]:
        return self.get_opportunities()

    def get_cluster(self, cluster_id: int) -> ClusterDetail | None:
        cluster = next(
            (item for item in self.get_clusters() if item.cluster_id == cluster_id),
            None,
        )
        return None if cluster is None else ClusterDetail(cluster, ())


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
        analytics_reader=RepositoryAnalyticsReadFacade(
            ClusterRepository(),
            SourceItemRepository(),
        ),
        semantic_search=RepositorySemanticSearch(
            EmbeddingService(embedding_model),
            SourceItemRepository(),
        ),
    )


def get_dependencies(request: Request) -> ApiDependencies:
    return request.app.state.dependencies
