from __future__ import annotations

import math


def resolve_live_lap_elapsed(
    time_into_lap_s: float,
    current_event_time_s: float,
    lap_start_event_time_s: float,
) -> float:
    """Resolve current lap time using a matching event-clock pair when available."""
    try:
        elapsed = float(time_into_lap_s)
        current_event = float(current_event_time_s)
        lap_start = float(lap_start_event_time_s)
    except (TypeError, ValueError, OverflowError):
        return 0.0

    if not math.isfinite(elapsed) or elapsed < 0.0:
        elapsed = 0.0
    if not math.isfinite(current_event) or not math.isfinite(lap_start):
        return elapsed

    event_elapsed = current_event - lap_start
    if event_elapsed > 0.0 and math.isfinite(event_elapsed):
        tolerance = max(0.75, event_elapsed * 0.04)
        if elapsed <= 0.0 or abs(elapsed - event_elapsed) > tolerance:
            return event_elapsed
    return elapsed
