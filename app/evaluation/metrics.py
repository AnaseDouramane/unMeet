"""Uncertainty for small evaluation sets.

An F1 measured on a few dozen examples has a wide confidence interval; reporting the interval
next to the point estimate keeps comparisons between classifiers honest.
"""

from __future__ import annotations

import numpy as np


def f1_from_counts(true_positives: int, false_positives: int, false_negatives: int) -> float:
    denominator = 2 * true_positives + false_positives + false_negatives
    return 2 * true_positives / denominator if denominator else 0.0


def bootstrap_f1_interval(
    true_positives: int,
    true_negatives: int,
    false_positives: int,
    false_negatives: int,
    confidence: float = 0.95,
    resamples: int = 5000,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap interval for F1, resampling the evaluated cases with replacement."""
    counts = np.array([true_positives, true_negatives, false_positives, false_negatives])
    total = int(counts.sum())
    if total == 0:
        return (0.0, 0.0)
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    rng = np.random.default_rng(seed)
    samples = rng.multinomial(total, counts / total, size=resamples)
    tp, fp, fn = samples[:, 0], samples[:, 2], samples[:, 3]
    denominator = 2 * tp + fp + fn
    scores = np.divide(2 * tp, denominator, out=np.zeros(resamples), where=denominator > 0)
    tail = (1 - confidence) / 2 * 100
    low, high = np.percentile(scores, [tail, 100 - tail])
    return (float(low), float(high))
