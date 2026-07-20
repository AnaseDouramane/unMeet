from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real

from app.clustering.schemas import ClusterTrend


@dataclass(frozen=True)
class OpportunityClusterInput:
    cluster_id: int
    label: str
    keywords: tuple[str, ...]
    document_count: int
    source_count: int
    average_problem_confidence: float


@dataclass(frozen=True)
class OpportunityScoreComponents:
    volume_score: float
    growth_score: float
    source_diversity_score: float
    confidence_score: float


@dataclass(frozen=True)
class OpportunityRankingResult:
    cluster_id: int
    label: str
    rank: int
    opportunity_score: float
    document_count: int
    growth_rate: float | None
    status: str
    source_count: int
    average_problem_confidence: float
    score_components: OpportunityScoreComponents


class OpportunityRankingService:
    _STATUS_VALUES = {"new", "rising", "stable", "falling"}
    _WEIGHT_TOLERANCE = 1e-9

    def __init__(
        self,
        volume_weight: float = 0.35,
        growth_weight: float = 0.35,
        source_diversity_weight: float = 0.15,
        confidence_weight: float = 0.15,
        new_growth_score: float = 0.75,
        stable_growth_score: float = 0.25,
    ) -> None:
        self._weights = self._validate_weights(
            volume_weight,
            growth_weight,
            source_diversity_weight,
            confidence_weight,
        )
        self._new_growth_score = self._validate_normalized_score(
            new_growth_score, "new_growth_score"
        )
        self._stable_growth_score = self._validate_normalized_score(
            stable_growth_score, "stable_growth_score"
        )

    def rank(
        self,
        clusters: Sequence[OpportunityClusterInput],
        trends: Sequence[ClusterTrend],
    ) -> tuple[OpportunityRankingResult, ...]:
        cluster_by_id = self._validate_clusters(clusters)
        trend_by_id = self._validate_trends(trends, cluster_by_id)
        if not cluster_by_id:
            return ()

        max_document_count = max(cluster.document_count for cluster in cluster_by_id.values())
        max_source_count = max(cluster.source_count for cluster in cluster_by_id.values())
        max_rising_growth = max(
            (
                trend.growth_rate
                for trend in trend_by_id.values()
                if (
                    trend.status == "rising"
                    and trend.growth_rate is not None
                    and trend.growth_rate > 0
                )
            ),
            default=0.0,
        )

        candidates = [
            self._score_cluster(
                cluster,
                trend_by_id[cluster_id],
                max_document_count,
                max_source_count,
                max_rising_growth,
            )
            for cluster_id, cluster in sorted(cluster_by_id.items())
        ]
        candidates.sort(
            key=lambda result: (
                -result.opportunity_score,
                -result.document_count,
                result.cluster_id,
            )
        )
        return tuple(
            OpportunityRankingResult(
                cluster_id=result.cluster_id,
                label=result.label,
                rank=rank,
                opportunity_score=result.opportunity_score,
                document_count=result.document_count,
                growth_rate=result.growth_rate,
                status=result.status,
                source_count=result.source_count,
                average_problem_confidence=result.average_problem_confidence,
                score_components=result.score_components,
            )
            for rank, result in enumerate(candidates, start=1)
        )

    def _score_cluster(
        self,
        cluster: OpportunityClusterInput,
        trend: ClusterTrend,
        max_document_count: int,
        max_source_count: int,
        max_rising_growth: float,
    ) -> OpportunityRankingResult:
        components = OpportunityScoreComponents(
            volume_score=(
                cluster.document_count / max_document_count
                if max_document_count
                else 0.0
            ),
            growth_score=self._growth_score(trend, max_rising_growth),
            source_diversity_score=(
                cluster.source_count / max_source_count if max_source_count else 0.0
            ),
            confidence_score=cluster.average_problem_confidence,
        )
        volume_weight, growth_weight, diversity_weight, confidence_weight = self._weights
        opportunity_score = (
            volume_weight * components.volume_score
            + growth_weight * components.growth_score
            + diversity_weight * components.source_diversity_score
            + confidence_weight * components.confidence_score
        )
        return OpportunityRankingResult(
            cluster_id=cluster.cluster_id,
            label=cluster.label,
            rank=0,
            opportunity_score=opportunity_score,
            document_count=cluster.document_count,
            growth_rate=trend.growth_rate,
            status=trend.status,
            source_count=cluster.source_count,
            average_problem_confidence=cluster.average_problem_confidence,
            score_components=components,
        )

    def _growth_score(self, trend: ClusterTrend, max_rising_growth: float) -> float:
        if trend.status == "new":
            return self._new_growth_score
        if trend.status == "rising":
            if trend.growth_rate is None or trend.growth_rate <= 0 or max_rising_growth == 0:
                return 0.0
            return trend.growth_rate / max_rising_growth
        if trend.status == "stable":
            return self._stable_growth_score
        return 0.0

    @classmethod
    def _validate_weights(cls, *weights: float) -> tuple[float, float, float, float]:
        normalized = tuple(
            cls._validate_non_negative_number(weight, "weight") for weight in weights
        )
        total_weight = sum(normalized)
        if total_weight > 1.0 or not math.isclose(
            total_weight, 1.0, abs_tol=cls._WEIGHT_TOLERANCE
        ):
            raise ValueError("weights must sum to 1")
        return normalized[0], normalized[1], normalized[2], normalized[3]

    @classmethod
    def _validate_clusters(
        cls, clusters: Sequence[OpportunityClusterInput]
    ) -> dict[int, OpportunityClusterInput]:
        cluster_by_id: dict[int, OpportunityClusterInput] = {}
        for cluster in clusters:
            if cluster.cluster_id in cluster_by_id:
                raise ValueError(f"duplicate cluster_id: {cluster.cluster_id}")
            cls._validate_count(cluster.document_count, "document_count")
            cls._validate_count(cluster.source_count, "source_count")
            cls._validate_normalized_score(
                cluster.average_problem_confidence, "average_problem_confidence"
            )
            cluster_by_id[cluster.cluster_id] = cluster
        return cluster_by_id

    @classmethod
    def _validate_trends(
        cls,
        trends: Sequence[ClusterTrend],
        cluster_by_id: dict[int, OpportunityClusterInput],
    ) -> dict[int, ClusterTrend]:
        trend_by_id: dict[int, ClusterTrend] = {}
        for trend in trends:
            if trend.current_cluster_id in trend_by_id:
                raise ValueError(f"duplicate trend cluster_id: {trend.current_cluster_id}")
            if trend.current_cluster_id not in cluster_by_id:
                raise ValueError("trend references an unknown cluster")
            if trend.status not in cls._STATUS_VALUES:
                raise ValueError(f"invalid trend status: {trend.status}")
            cls._validate_count(trend.current_count, "trend current_count")
            cls._validate_count(trend.previous_count, "trend previous_count")
            if trend.current_count != cluster_by_id[trend.current_cluster_id].document_count:
                raise ValueError("trend current_count does not match cluster document_count")
            if trend.growth_rate is not None:
                cls._validate_finite_number(trend.growth_rate, "growth_rate")
            trend_by_id[trend.current_cluster_id] = trend
        if set(trend_by_id) != set(cluster_by_id):
            raise ValueError("trends must cover every cluster exactly once")
        return trend_by_id

    @staticmethod
    def _validate_count(value: int, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")

    @classmethod
    def _validate_normalized_score(cls, value: float, name: str) -> float:
        normalized = cls._validate_finite_number(value, name)
        if not 0.0 <= normalized <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1")
        return normalized

    @staticmethod
    def _validate_non_negative_number(value: float, name: str) -> float:
        normalized = OpportunityRankingService._validate_finite_number(value, name)
        if normalized < 0:
            raise ValueError(f"{name} must be non-negative")
        return normalized

    @staticmethod
    def _validate_finite_number(value: float, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must be numeric")
        normalized = float(value)
        if not math.isfinite(normalized):
            raise ValueError(f"{name} must be finite")
        return normalized
