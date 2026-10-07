"""Small statistics helpers shared by the validation scripts (no scipy dependency)."""

import numpy as np


def rankdata(values) -> np.ndarray:
    """Ranks with ties replaced by their average rank (as scipy.stats.rankdata(method="average"))."""
    arr = np.asarray(values, dtype=float)
    order = np.argsort(arr, kind="mergesort")
    ranks = np.empty(len(arr))
    ranks[order] = np.arange(len(arr), dtype=float)
    sorted_vals = arr[order]
    i = 0
    while i < len(arr):
        j = i
        while j + 1 < len(arr) and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j) / 2
        i = j + 1
    return ranks


def spearman(a, b) -> float | None:
    """Spearman's rho with proper handling of ties; None when one side is constant."""
    ra, rb = rankdata(a), rankdata(b)
    if len(ra) < 2 or ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])
