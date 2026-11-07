import pytest

from app.evaluation.metrics import bootstrap_f1_interval, f1_from_counts


def test_f1_from_counts_matches_the_definition() -> None:
    assert f1_from_counts(8, 2, 2) == pytest.approx(0.8)
    assert f1_from_counts(0, 0, 0) == 0.0


def test_interval_contains_the_point_estimate_and_shrinks_with_more_data() -> None:
    small = bootstrap_f1_interval(16, 15, 2, 2)
    large = bootstrap_f1_interval(1600, 1500, 200, 200)
    point = f1_from_counts(16, 2, 2)

    assert small[0] <= point <= small[1]
    assert (large[1] - large[0]) < (small[1] - small[0]) / 5


def test_interval_is_deterministic_for_a_seed() -> None:
    assert bootstrap_f1_interval(10, 10, 3, 2, seed=1) == bootstrap_f1_interval(
        10, 10, 3, 2, seed=1
    )


def test_empty_counts_give_a_zero_interval() -> None:
    assert bootstrap_f1_interval(0, 0, 0, 0) == (0.0, 0.0)
