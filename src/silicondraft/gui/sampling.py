"""Deterministic downsampling shared by the GUI previews."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

IntArray = NDArray[np.int64]


def sample_indices(size: int, limit: int) -> IntArray:
    """Return evenly spaced, strictly increasing indices, capped at ``limit``.

    Preview widgets use this to bound their work on very large runs while
    keeping the selection stable across repaints.
    """
    if size <= 0 or limit <= 0:
        return np.empty(0, dtype=np.int64)
    if size <= limit:
        return np.arange(size, dtype=np.int64)
    return np.unique(np.linspace(0, size - 1, limit).astype(np.int64))
