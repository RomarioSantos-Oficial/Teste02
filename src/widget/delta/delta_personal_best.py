from __future__ import annotations

from bisect import bisect_left
import math
from typing import Any, Sequence


def interpolate_trace_elapsed(
    trace: Sequence[dict[str, Any]],
    distance_fraction: float,
) -> float | None:
    """Interpolate PB elapsed time at the current normalized track distance."""
    try:
        fraction = float(distance_fraction)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(fraction):
        return None
    fraction = max(0.0, min(1.0, fraction))

    samples: list[tuple[float, float]] = []
    for point in trace:
        if not isinstance(point, dict):
            continue
        try:
            distance = float(point.get("distance", float("nan")))
            elapsed = float(point.get("elapsed_s", float("nan")))
        except (TypeError, ValueError, OverflowError):
            continue
        if (
            not math.isfinite(distance)
            or not math.isfinite(elapsed)
            or not 0.0 <= distance <= 1.0
            or elapsed < 0.0
        ):
            continue
        samples.append((distance, elapsed))

    if len(samples) < 2:
        return None

    samples.sort(key=lambda item: item[0])
    unique: list[tuple[float, float]] = []
    for sample in samples:
        if unique and sample[0] - unique[-1][0] <= 1e-9:
            unique[-1] = sample
        else:
            unique.append(sample)
    if len(unique) < 2:
        return None

    distances = [sample[0] for sample in unique]
    elapsed_values = [sample[1] for sample in unique]
    right_index = bisect_left(distances, fraction)
    if right_index <= 0:
        return elapsed_values[0]
    if right_index >= len(unique):
        return elapsed_values[-1]

    left_distance = distances[right_index - 1]
    right_distance = distances[right_index]
    span = right_distance - left_distance
    if span <= 1e-9:
        return elapsed_values[right_index]
    ratio = (fraction - left_distance) / span
    result = elapsed_values[right_index - 1] + (
        elapsed_values[right_index] - elapsed_values[right_index - 1]
    ) * ratio
    return result if math.isfinite(result) else None

def completed_lap_delta(
    last_lap_seconds: float,
    personal_best_seconds: float,
    *,
    invalidated: bool = False,
) -> float | None:
    """Return completed lap time minus the archived personal-best lap time."""
    if invalidated:
        return None
    try:
        current = float(last_lap_seconds)
        reference = float(personal_best_seconds)
    except (TypeError, ValueError, OverflowError):
        return None
    if (
        not math.isfinite(current)
        or not math.isfinite(reference)
        or not 1.0 < current < 3600.0
        or not 1.0 < reference < 3600.0
    ):
        return None
    return current - reference

 
class DeltaPositionSynchronizer:
    """Keep lap distance monotonic through small Shared Memory position jitters."""

    def __init__(self, max_backward_m: float = 200.0, max_desync: int = 20) -> None:
        self.max_backward_m = max(1.0, float(max_backward_m))
        self.max_desync = max(1, int(max_desync))
        self.reset()

    def reset(self) -> None:
        self._lap_marker: int | None = None
        self._last_raw_distance: float | None = None
        self._last_elapsed: float | None = None
        self._last_speed_kmh = 0.0
        self._estimated_distance = 0.0
        self._synced_distance = 0.0
        self._desync_count = 0

    def update(
        self,
        raw_distance_m: float,
        elapsed_s: float,
        speed_kmh: float,
        lap_marker: int | None = None,
    ) -> float | None:
        try:
            raw = float(raw_distance_m)
            elapsed = float(elapsed_s)
            speed = max(0.0, float(speed_kmh))
            marker = int(lap_marker) if lap_marker is not None else None
        except (TypeError, ValueError, OverflowError):
            return None
        if not all(math.isfinite(value) for value in (raw, elapsed, speed)):
            return None
        if raw < 0.0 or elapsed < 0.0:
            return None

        if self._last_elapsed is None or (
            marker is not None and marker != self._lap_marker
        ):
            self._lap_marker = marker
            self._last_raw_distance = raw
            self._last_elapsed = elapsed
            self._last_speed_kmh = speed
            self._estimated_distance = raw
            self._synced_distance = raw
            self._desync_count = 0
            return raw

        delta_elapsed = elapsed - self._last_elapsed
        delta_distance = 0.0
        if 0.0 < delta_elapsed < 1.0:
            average_speed_ms = (speed + self._last_speed_kmh) / 7.2
            delta_distance = average_speed_ms * delta_elapsed

        if self._last_raw_distance is None or raw != self._last_raw_distance:
            estimated = raw
        else:
            estimated = self._estimated_distance + delta_distance

        synced = self._synced_distance
        if synced > estimated:
            backwards = synced - estimated
            if backwards > self.max_backward_m or self._desync_count > self.max_desync:
                synced = estimated
                self._desync_count = 0
            else:
                self._desync_count += 1
        elif synced < estimated:
            synced = estimated
            self._desync_count = 0

        self._last_raw_distance = raw
        self._last_elapsed = elapsed
        self._last_speed_kmh = speed
        self._estimated_distance = estimated
        self._synced_distance = max(0.0, synced)
        return self._synced_distance
