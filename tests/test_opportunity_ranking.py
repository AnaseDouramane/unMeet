import math

import pytest

from app.clustering.schemas import ClusterTrend
from app.opportunities.ranking import OpportunityClusterInput, OpportunityRankingService


def _cluster(
    cluster_id: int, count: int, sources: int, confidence: float
) -> OpportunityClusterInput:
    return OpportunityClusterInput(
        cluster_id,
        f"cluster-{cluster_id}",
        ("keyword",),
        count,
        sources,
        confidence,
    )


def _trend(
    cluster_id: int, count: int, status: str, growth_rate: float | None
) -> ClusterTrend:
    return ClusterTrend(
        cluster_id,
        None,
        f"cluster-{cluster_id}",
        count,
        1,
        count - 1,
        growth_rate,
        status,
        None,
    )


def test_ranking_scores_volume_growth_diversity_and_confidence() -> None:
    results = OpportunityRankingService().rank(
        [_cluster(1, 10, 1, 0.5), _cluster(2, 5, 3, 1.0)],
        [_trend(1, 10, "stable", 0.0), _trend(2, 5, "rising", 2.0)],
    )

    assert [result.cluster_id for result in results] == [2, 1]
    assert results[0].score_components.volume_score == 0.5
    assert results[0].score_components.growth_score == 1.0
    assert results[0].score_components.source_diversity_score == 1.0
    assert results[0].score_components.confidence_score == 1.0
    assert results[1].score_components.volume_score == 1.0
    assert results[1].score_components.growth_score == 0.25
    assert all(0.0 <= result.opportunity_score <= 1.0 for result in results)


def test_new_and_falling_clusters_follow_growth_policy() -> None:
    results = OpportunityRankingService(new_growth_score=0.8).rank(
        [_cluster(1, 4, 1, 0.5), _cluster(2, 4, 1, 0.5)],
        [_trend(1, 4, "new", None), _trend(2, 4, "falling", -0.9)],
    )

    assert results[0].cluster_id == 1
    assert results[0].score_components.growth_score == 0.8
    assert results[1].score_components.growth_score == 0.0


def test_single_cluster_and_equal_values_are_normalized_deterministically() -> None:
    single = OpportunityRankingService().rank(
        [_cluster(2, 3, 1, 0.7)],
        [_trend(2, 3, "stable", None)],
    )
    equal = OpportunityRankingService().rank(
        [_cluster(2, 3, 2, 0.7), _cluster(1, 3, 2, 0.7)],
        [_trend(2, 3, "stable", 0.0), _trend(1, 3, "stable", 0.0)],
    )

    assert single[0].score_components.volume_score == 1.0
    assert single[0].score_components.source_diversity_score == 1.0
    assert [result.cluster_id for result in equal] == [1, 2]
    assert [result.rank for result in equal] == [1, 2]


def test_all_maximum_components_produce_a_score_of_one() -> None:
    result = OpportunityRankingService(
        volume_weight=0.25,
        growth_weight=0.25,
        source_diversity_weight=0.25,
        confidence_weight=0.25,
        new_growth_score=1.0,
    ).rank(
        [_cluster(1, 4, 2, 1.0)],
        [_trend(1, 4, "new", None)],
    )[0]

    assert result.score_components.volume_score == 1.0
    assert result.score_components.growth_score == 1.0
    assert result.score_components.source_diversity_score == 1.0
    assert result.score_components.confidence_score == 1.0
    assert result.opportunity_score == 1.0
    assert 0.0 <= result.opportunity_score <= 1.0


def test_zero_counts_produce_zero_relative_volume_and_diversity_scores() -> None:
    service = OpportunityRankingService()

    results = service.rank(
        [_cluster(2, 0, 0, 0.5), _cluster(1, 0, 0, 0.5)],
        [_trend(2, 0, "stable", None), _trend(1, 0, "stable", None)],
    )

    assert [result.cluster_id for result in results] == [1, 2]
    assert all(result.score_components.volume_score == 0.0 for result in results)
    assert all(
        result.score_components.source_diversity_score == 0.0 for result in results
    )


def test_tie_breaks_by_document_count_then_cluster_id() -> None:
    service = OpportunityRankingService(
        volume_weight=0.0,
        growth_weight=0.0,
        source_diversity_weight=0.0,
        confidence_weight=1.0,
    )

    results = service.rank(
        [
            _cluster(3, 2, 1, 0.5),
            _cluster(1, 5, 1, 0.5),
            _cluster(2, 5, 1, 0.5),
        ],
        [
            _trend(3, 2, "stable", None),
            _trend(1, 5, "stable", None),
            _trend(2, 5, "stable", None),
        ],
    )

    assert [result.cluster_id for result in results] == [1, 2, 3]


def test_empty_input_returns_an_empty_ranking() -> None:
    assert OpportunityRankingService().rank([], []) == ()


@pytest.mark.parametrize(
    "weights",
    [
        (0.5, 0.5, 0.5, -0.5),
        (0.3, 0.3, 0.3, 0.3),
        (0.25, 0.25, 0.25, 0.2500000001),
        (math.nan, 0.35, 0.15, 0.15),
    ],
)
def test_ranking_rejects_invalid_weights(weights) -> None:
    with pytest.raises(ValueError):
        OpportunityRankingService(*weights)


@pytest.mark.parametrize(
    "clusters, trends, error",
    [
        ([_cluster(1, -1, 1, 0.5)], [_trend(1, -1, "stable", 0.0)], "document_count"),
        ([_cluster(1, 1, 1, 1.1)], [_trend(1, 1, "stable", 0.0)], "confidence"),
        ([_cluster(1, 1, 1, 0.5)], [_trend(1, 1, "unknown", 0.0)], "status"),
        ([_cluster(1, 1, 1, 0.5)], [_trend(1, 1, "stable", math.inf)], "growth_rate"),
        ([_cluster(1, 1, 1, 0.5)], [], "cover every cluster"),
        (
            [_cluster(1, 1, 1, 0.5), _cluster(1, 1, 1, 0.5)],
            [_trend(1, 1, "stable", 0.0)],
            "duplicate",
        ),
    ],
)
def test_ranking_rejects_incoherent_data(clusters, trends, error) -> None:
    with pytest.raises(ValueError, match=error):
        OpportunityRankingService().rank(clusters, trends)


def test_ranking_is_deterministic_when_input_order_changes() -> None:
    clusters = [
        _cluster(3, 2, 1, 0.5),
        _cluster(1, 4, 2, 0.6),
        _cluster(2, 3, 1, 0.9),
    ]
    trends = [
        _trend(3, 2, "new", None),
        _trend(1, 4, "rising", 0.5),
        _trend(2, 3, "stable", 0.0),
    ]

    first = OpportunityRankingService().rank(clusters, trends)
    second = OpportunityRankingService().rank(
        list(reversed(clusters)), list(reversed(trends))
    )

    assert first == second
