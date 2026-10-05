from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from .state import UnifiedState


@dataclass(slots=True)
class RoutePreview:
    source: str
    track_key: str
    lookahead_m: float
    target_distance_m: float
    target_world_xy_m: tuple[float, float]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class RouteAssessment:
    status: str
    source: str | None = None
    distance_to_route_m: float | None = None
    heading_alignment: float | None = None
    nearest_route_distance_m: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize_track_name(name: str) -> str:
    value = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", value))


class RecordedRouteRepository:
    """Loads sampled routes created by SectorFlow's map recorder (not AIW files)."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def _matching_map(self, state: UnifiedState) -> dict | None:
        vehicle = state.vehicle
        if vehicle is None or vehicle.lap_distance_m is None or not state.track_length_m:
            return None
        track_name = _normalize_track_name(state.track_name)
        if not track_name:
            return None
        best: tuple[float, dict] | None = None
        for path in self.directory.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                map_name = _normalize_track_name(str(data.get("track_name", "")))
                map_length = float(data.get("track_length_m", 0))
                points = data.get("points", [])
                if map_name != track_name or map_length <= 0 or len(points) < 2:
                    continue
                length_error = abs(map_length - state.track_length_m) / state.track_length_m
                if length_error > 0.02:
                    continue
                if best is None or length_error < best[0]:
                    best = (length_error, data)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return best[1] if best else None

    def preview(self, state: UnifiedState, lookahead_m: float = 30.0) -> RoutePreview | None:
        vehicle = state.vehicle
        if vehicle is None or vehicle.lap_distance_m is None:
            return None
        data = self._matching_map(state)
        if data is None:
            return None
        points = sorted(data["points"], key=lambda item: float(item["distance_m"]))
        length = float(data["track_length_m"])
        target_distance = (vehicle.lap_distance_m + max(0.0, lookahead_m)) % length
        # Select the first recorded sample at or after the preview distance, wrapping at S/F.
        target = next((p for p in points if float(p["distance_m"]) >= target_distance), points[0])
        return RoutePreview(
            source="RECORDED_MAP",
            track_key=str(data.get("track_key", "")),
            lookahead_m=max(0.0, lookahead_m),
            target_distance_m=float(target["distance_m"]),
            target_world_xy_m=(float(target["world_x"]), float(target["world_y"])),
        )

    def assess(self, state: UnifiedState, deviation_limit_m: float = 5.0) -> RouteAssessment:
        vehicle = state.vehicle
        if vehicle is None or vehicle.world_position_m is None or vehicle.forward_direction is None:
            return RouteAssessment("INSUFFICIENT_TELEMETRY")
        data = self._matching_map(state)
        if data is None:
            return RouteAssessment("NO_MATCHING_ROUTE")
        points = sorted(data["points"], key=lambda item: float(item["distance_m"]))
        # Map files use (world_x, -world_z), matching the map widget coordinate transform.
        x, y = vehicle.world_position_m[0], -vehicle.world_position_m[2]
        fx, fy = vehicle.forward_direction[0], -vehicle.forward_direction[2]
        forward_norm = math.hypot(fx, fy)
        if forward_norm < 1e-6:
            return RouteAssessment("INSUFFICIENT_TELEMETRY", source="RECORDED_MAP")
        fx, fy = fx / forward_norm, fy / forward_norm
        best: tuple[float, float] | None = None
        for index, point in enumerate(points):
            following = points[(index + 1) % len(points)]
            ax, ay = float(point["world_x"]), float(point["world_y"])
            bx, by = float(following["world_x"]), float(following["world_y"])
            dx, dy = bx - ax, by - ay
            segment_sq = dx * dx + dy * dy
            if segment_sq < 1e-9:
                continue
            ratio = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / segment_sq))
            px, py = ax + ratio * dx, ay + ratio * dy
            error_x, error_y = x - px, y - py
            distance = math.hypot(error_x, error_y)
            # Signed error is positive to the segment's left, negative to its right.
            signed_error = math.copysign(distance, dx * error_y - dy * error_x) if distance else 0.0
            if best is None or distance < best[0]:
                best = (distance, signed_error)
                tangent_norm = math.sqrt(segment_sq)
                alignment = (fx * dx + fy * dy) / tangent_norm
        if best is None:
            return RouteAssessment("INSUFFICIENT_ROUTE_POINTS", source="RECORDED_MAP")
        if best[0] > deviation_limit_m:
            status = "OFF_ROUTE"
        elif alignment < -0.25:
            status = "WRONG_DIRECTION"
        elif alignment < 0.5:
            status = "HEADING_MISMATCH"
        else:
            status = "ON_ROUTE"
        return RouteAssessment(status, "RECORDED_MAP", best[1], alignment, best[0])
