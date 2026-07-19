import numpy as np
import pytest

from app.clustering.matching import ClusterMatchingService
from app.clustering.schemas import ClusterCentroid, ClusterMatch


def _cluster(cluster_id: int, *components: tuple[int, float]) -> ClusterCentroid:
    centroid = [0.0] * 384
    for index, value in components:
        centroid[index] = value
    return ClusterCentroid(cluster_id=cluster_id, centroid=tuple(centroid))


def test_matching_selects_the_most_similar_previous_cluster() -> None:
    previous = [_cluster(10, (0, 1.0)), _cluster(20, (1, 1.0))]
    current = [_cluster(100, (0, 3.0), (1, 4.0)), _cluster(101, (0, 1.0))]

    matches = ClusterMatchingService(similarity_threshold=0.7).match(previous, current)

    assert matches == [
        ClusterMatch(
            current_cluster_id=100,
            previous_cluster_id=20,
            similarity=pytest.approx(0.8),
            status="matched",
        ),
        ClusterMatch(
            current_cluster_id=101,
            previous_cluster_id=10,
            similarity=pytest.approx(1.0),
            status="matched",
        ),
    ]


def test_matching_marks_a_cluster_as_new_below_the_threshold() -> None:
    previous = [_cluster(10, (0, 1.0))]
    current = [_cluster(100, (1, 1.0))]

    matches = ClusterMatchingService(similarity_threshold=0.1).match(previous, current)

    assert matches == [
        ClusterMatch(
            current_cluster_id=100,
            previous_cluster_id=None,
            similarity=pytest.approx(0.0),
            status="new",
        )
    ]


def test_matching_is_deterministic_for_equal_similarity() -> None:
    previous = [_cluster(20, (0, 1.0)), _cluster(10, (0, 1.0))]
    current = [_cluster(100, (0, 1.0))]

    match = ClusterMatchingService().match(previous, current)[0]

    assert match.previous_cluster_id == 10
    assert match.status == "matched"


def test_each_previous_cluster_is_assigned_to_at_most_one_current_cluster() -> None:
    previous = [_cluster(10, (0, 1.0))]
    current = [_cluster(100, (0, 1.0)), _cluster(101, (0, 2.0))]

    matches = ClusterMatchingService().match(previous, current)

    assert [
        (match.current_cluster_id, match.previous_cluster_id, match.status) for match in matches
    ] == [
        (100, 10, "matched"),
        (101, None, "new"),
    ]


def test_matching_resolves_conflicts_globally_and_is_independent_of_input_order() -> None:
    previous = [_cluster(10, (0, 1.0)), _cluster(20, (1, 1.0))]
    current = [_cluster(100, (0, 0.9), (1, 0.435889894)), _cluster(101, (0, 1.0))]
    service = ClusterMatchingService(similarity_threshold=0.4)

    matches = service.match(previous, current)
    reversed_matches = service.match(list(reversed(previous)), list(reversed(current)))

    assert matches == reversed_matches
    assert [(match.current_cluster_id, match.previous_cluster_id) for match in matches] == [
        (100, 20),
        (101, 10),
    ]


@pytest.mark.parametrize("length", [383, 385])
def test_matching_rejects_centroids_with_invalid_length(length: int) -> None:
    centroid = ClusterCentroid(cluster_id=1, centroid=tuple([1.0] * length))

    with pytest.raises(ValueError, match="exactly 384 values"):
        ClusterMatchingService().match([centroid], [])


@pytest.mark.parametrize("invalid_value", [np.nan, np.inf, -np.inf])
def test_matching_rejects_non_finite_centroids(invalid_value: float) -> None:
    centroid = list(_cluster(1, (0, 1.0)).centroid)
    centroid[10] = invalid_value

    with pytest.raises(ValueError, match="must be finite"):
        ClusterMatchingService().match([ClusterCentroid(1, tuple(centroid))], [])


def test_matching_rejects_zero_centroids_and_invalid_thresholds() -> None:
    zero_centroid = ClusterCentroid(cluster_id=1, centroid=tuple([0.0] * 384))

    with pytest.raises(ValueError, match="zero vector"):
        ClusterMatchingService().match([zero_centroid], [])
    with pytest.raises(ValueError, match="between -1 and 1"):
        ClusterMatchingService(similarity_threshold=1.1)
