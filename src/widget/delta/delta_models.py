from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class DeltaSectorData:
    label: str
    delta_s: float | None = None


@dataclass(slots=True)
class FastestLapData:
    driver_name: str = ""
    vehicle_name: str = ""
    vehicle_class: str = ""
    manufacturer: str = ""
    logo_path: Path | None = None
    lap_time_s: float = 0.0
    position: int = 0

    @property
    def valid(self) -> bool:
        return self.lap_time_s > 0 and bool(self.driver_name)


@dataclass(slots=True)
class DeltaViewData:
    delta_s: float = 0.0
    session_time_text: str = "--:--:--"
    session_name: str = "Waiting"
    track_state: str = "Unknown"
    penalties: int = 0
    sectors: list[DeltaSectorData] = field(
        default_factory=lambda: [
            DeltaSectorData("S1"),
            DeltaSectorData("S2"),
            DeltaSectorData("S3"),
        ]
    )
    fastest_lap: FastestLapData | None = None
    fastest_alpha: float = 0.0
    session_key: str = ""
