from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .state import UnifiedState
from .route import RecordedRouteRepository


Mode = Literal["OBSERVE", "ASSIST", "AUTONOMOUS"]


@dataclass(slots=True)
class DriverDecision:
    mode: Mode
    timestamp_s: float
    steering: float | None = None
    throttle: float | None = None
    brake: float | None = None
    applied: bool = False
    status: str = "observation_only"
    reason: str = "No supported LMU control-output interface is configured."
    route_preview: dict | None = None
    route_assessment: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ObserveDriver:
    """Safe first-stage driver: observes state and never emits control inputs."""

    def __init__(self, route_repository: RecordedRouteRepository | None = None) -> None:
        self.route_repository = route_repository

    def decide(self, state: UnifiedState) -> DriverDecision:
        if not state.connected:
            reason = "LMU telemetry is disconnected."
        elif state.vehicle is None:
            reason = "Waiting for the player's vehicle telemetry."
        elif state.telemetry_paused:
            reason = "Telemetry is paused; control must remain disabled."
        else:
            reason = "OBSERVE mode records telemetry; control output is disabled."
        preview = self.route_repository.preview(state) if self.route_repository else None
        route_preview = preview.to_dict() if preview is not None else None
        route_assessment = self.route_repository.assess(state).to_dict() if self.route_repository else None
        if route_assessment and route_assessment["status"] in {"OFF_ROUTE", "WRONG_DIRECTION", "HEADING_MISMATCH"}:
            reason = f"Route monitor alert: {route_assessment['status']}; control output remains disabled."
        return DriverDecision(
            mode="OBSERVE",
            timestamp_s=state.timestamp_s,
            status="ready" if state.connected and state.vehicle else "waiting",
            reason=reason,
            route_preview=route_preview,
            route_assessment=route_assessment,
        )
