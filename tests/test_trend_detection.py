import pytest

from app.clustering.schemas import ClusterMatch, ClusterTrend, TrendCluster
from app.clustering.trend_detection import TrendDetectionService


def _cluster(cluster_id: int, label: str, document_count: int) -> TrendCluster:
    return TrendCluster(id=cluster_id, label=label, document_count=document_count)


def _match(
    current_cluster_id: int,
    previous_cluster_id: int | None,
    similarity: float | None = 0.9,
) -> ClusterMatch:
    return ClusterMatch(
        current_cluster_id=current_cluster_id,
        previous_cluster_id=previous_cluster_id,
        similarity=similarity,
        status="new" if previous_cluster_id is None else "matched",
    )


def test_detect_marks_unmatched_clusters_as_new() -> None:
    trends = TrendDetectionService().detect(
        [],
        [_cluster(2, "New topic", 5)],
        [_match(2, None)],
    )

    assert trends == [
        ClusterTrend(
            current_cluster_id=2,
            previous_cluster_id=None,
            label="New topic",
            current_count=5,
            previous_count=0,
            absolute_change=5,
            growth_rate=None,
            status="new",
            similarity=None,
        )
    ]


def test_detect_marks_growth_above_the_threshold_as_rising() -> None:
    trends = TrendDetectionService(change_threshold=0.2).detect(
        [_cluster(1, "Previous", 10)],
        [_cluster(2, "Current", 15)],
        [_match(2, 1)],
    )

    assert trends[0].status == "rising"
    assert trends[0].growth_rate == pytest.approx(0.5)
    assert trends[0].absolute_change == 5


def test_detect_marks_decline_above_the_threshold_as_falling() -> None:
    trends = TrendDetectionService(change_threshold=0.2).detect(
        [_cluster(1, "Previous", 10)],
        [_cluster(2, "Current", 7)],
        [_match(2, 1)],
    )

    assert trends[0].status == "falling"
    assert trends[0].growth_rate == pytest.approx(-0.3)
    assert trends[0].absolute_change == -3


def test_detect_marks_changes_within_the_threshold_as_stable() -> None:
    trends = TrendDetectionService(change_threshold=0.2).detect(
        [_cluster(1, "Previous", 10)],
        [_cluster(2, "Current", 11)],
        [_match(2, 1)],
    )

    assert trends[0].status == "stable"
    assert trends[0].growth_rate == pytest.approx(0.1)


def test_detect_treats_a_change_at_the_threshold_as_stable() -> None:
    trends = TrendDetectionService(change_threshold=0.2).detect(
        [_cluster(1, "Previous", 10)],
        [_cluster(2, "Current", 12)],
        [_match(2, 1)],
    )

    assert trends[0].status == "stable"
    assert trends[0].growth_rate == pytest.approx(0.2)


def test_detect_handles_a_matched_cluster_with_zero_previous_count() -> None:
    trends = TrendDetectionService().detect(
        [_cluster(1, "Previous", 0)],
        [_cluster(2, "Current", 3)],
        [_match(2, 1)],
    )

    assert trends[0].previous_count == 0
    assert trends[0].growth_rate is None
    assert trends[0].status == "rising"


@pytest.mark.parametrize(
    "matches, error",
    [
        ([_match(99, None)], "unknown current"),
        ([_match(2, 99)], "unknown previous"),
        ([_match(2, None), _match(2, None)], "duplicate current_cluster_id"),
    ],
)
def test_detect_rejects_incoherent_matching_results(
    matches: list[ClusterMatch], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        TrendDetectionService().detect([], [_cluster(2, "Current", 1)], matches)


def test_detect_returns_an_empty_list_for_empty_input() -> None:
    assert TrendDetectionService().detect([], [], []) == []


def test_detect_is_deterministic_regardless_of_input_order() -> None:
    previous = [_cluster(1, "First", 10), _cluster(2, "Second", 10)]
    current = [_cluster(20, "Current second", 12), _cluster(10, "Current first", 8)]
    matches = [_match(20, 2, 0.8), _match(10, 1, 0.9)]
    service = TrendDetectionService(change_threshold=0.1)

    trends = service.detect(previous, current, matches)
    reversed_trends = service.detect(
        list(reversed(previous)),
        list(reversed(current)),
        list(reversed(matches)),
    )

    assert trends == reversed_trends
    assert [trend.current_cluster_id for trend in trends] == [10, 20]


@pytest.mark.parametrize("similarity", [2.0, -2.0])
def test_detect_rejects_similarity_outside_the_cosine_range(similarity: float) -> None:
    with pytest.raises(ValueError, match="between -1 and 1"):
        TrendDetectionService().detect(
            [_cluster(1, "Previous", 1)],
            [_cluster(2, "Current", 1)],
            [_match(2, 1, similarity)],
        )


@pytest.mark.parametrize("similarity", [-1.0, 1.0])
def test_detect_accepts_similarity_at_the_cosine_range_limits(similarity: float) -> None:
    trends = TrendDetectionService().detect(
        [_cluster(1, "Previous", 1)],
        [_cluster(2, "Current", 1)],
        [_match(2, 1, similarity)],
    )

    assert trends[0].similarity == similarity


@pytest.mark.parametrize("similarity", [1.0 + 5e-13, -1.0 - 5e-13])
def test_detect_accepts_similarity_within_the_numeric_tolerance(similarity: float) -> None:
    trends = TrendDetectionService().detect(
        [_cluster(1, "Previous", 1)],
        [_cluster(2, "Current", 1)],
        [_match(2, 1, similarity)],
    )

    assert trends[0].similarity == similarity


def test_detect_accepts_none_similarity_for_a_new_cluster() -> None:
    trends = TrendDetectionService().detect(
        [],
        [_cluster(2, "New", 1)],
        [_match(2, None, None)],
    )

    assert trends[0].similarity is None
