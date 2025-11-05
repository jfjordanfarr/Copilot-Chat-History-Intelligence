"""Compute similarity actionability thresholds from repeat-failure telemetry."""
from __future__ import annotations

import datetime as dt
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

__all__ = [
    "ThresholdResult",
    "DEFAULT_PERCENTILE",
    "DEFAULT_WINDOW_DAYS",
    "FALLBACK_THRESHOLD",
    "similarity_score_from_occurrence",
    "compute_similarity_threshold",
    "percentile_value",
]

DEFAULT_PERCENTILE = 0.9
DEFAULT_WINDOW_DAYS = 7
FALLBACK_THRESHOLD = 0.8


@dataclass(frozen=True)
class ThresholdResult:
    """Summary of a computed similarity threshold."""

    threshold: float
    samples: int
    percentile: float
    fallback_used: bool
    window_start_ms: Optional[int]
    window_end_ms: int

    def as_dict(self) -> dict[str, object]:
        return {
            "threshold": self.threshold,
            "samples": self.samples,
            "percentile": self.percentile,
            "fallback_used": self.fallback_used,
            "window_start_ms": self.window_start_ms,
            "window_end_ms": self.window_end_ms,
        }


def similarity_score_from_occurrence(count: int) -> float:
    """Map an occurrence count to a bounded similarity score.

    The curve approaches 1.0 as the same motif repeats. This keeps thresholds in
    the 0–1 range while rewarding materially repeated behaviour (three
    occurrences yield ~0.95)."""

    if count <= 0:
        return 0.0
    return 1.0 - math.exp(-float(count))


def percentile_value(values: Iterable[float], percentile: float) -> float:
    items: List[float] = [float(v) for v in values if not math.isnan(float(v))]
    if not items:
        raise ValueError("No values available for percentile computation.")
    items.sort()
    if percentile <= 0.0:
        return items[0]
    if percentile >= 1.0:
        return items[-1]
    position = percentile * (len(items) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return items[lower]
    weight = position - lower
    return items[lower] + weight * (items[upper] - items[lower])


def _load_occurrences(db_path: Path) -> List[tuple[int, Optional[int]]]:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT occurrence_count, last_seen_ms FROM metrics_repeat_failures"
        ).fetchall()
    data: List[tuple[int, Optional[int]]] = []
    for row in rows:
        count = row["occurrence_count"] if row["occurrence_count"] is not None else 0
        last_seen_ms = row["last_seen_ms"] if row["last_seen_ms"] is not None else None
        if isinstance(count, int):
            data.append((count, last_seen_ms))
    return data


def compute_similarity_threshold(
    db_path: Path,
    *,
    percentile: float = DEFAULT_PERCENTILE,
    window_days: int = DEFAULT_WINDOW_DAYS,
    fallback_threshold: float = FALLBACK_THRESHOLD,
) -> ThresholdResult:
    """Compute the actionable similarity threshold from repeat-failure telemetry."""

    now = dt.datetime.now(dt.timezone.utc)
    window_start = now - dt.timedelta(days=window_days)
    window_start_ms = int(window_start.timestamp() * 1000)
    window_end_ms = int(now.timestamp() * 1000)
    entries = _load_occurrences(db_path)

    recent_scores = [
        similarity_score_from_occurrence(count)
        for count, last_seen in entries
        if last_seen is None or last_seen >= window_start_ms
    ]
    if recent_scores:
        threshold = percentile_value(recent_scores, percentile)
        return ThresholdResult(
            threshold=threshold,
            samples=len(recent_scores),
            percentile=percentile,
            fallback_used=False,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
        )

    if entries:
        overall_scores = [similarity_score_from_occurrence(count) for count, _ in entries]
        if overall_scores:
            threshold = percentile_value(overall_scores, percentile)
            return ThresholdResult(
                threshold=threshold,
                samples=len(overall_scores),
                percentile=percentile,
                fallback_used=False,
                window_start_ms=None,
                window_end_ms=window_end_ms,
            )

    return ThresholdResult(
        threshold=fallback_threshold,
        samples=0,
        percentile=percentile,
        fallback_used=True,
        window_start_ms=None,
        window_end_ms=window_end_ms,
    )
