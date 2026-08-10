from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


SECTOR_NEUTRAL = "neutral"
SECTOR_BETTER = "better"
SECTOR_WORSE = "worse"
SECTOR_SESSION_BEST = "session_best"


@dataclass(slots=True)
class DeltaSectorData:
    label: str
    delta_s: float | None = None
    time_s: float | None = None
    status: str = SECTOR_NEUTRAL


@dataclass(slots=True)
class FastestLapData:
    driver_name: str = ""
    nationality: str = ""
    country_code: str = ""
    vehicle_name: str = ""
    vehicle_class: str = ""
    manufacturer: str = ""
    logo_path: Path | None = None
    lap_time_s: float = 0.0
    # `position` permanece por compatibilidade e representa a posicao na classe.
    position: int = 0
    class_position: int = 0
    overall_position: int = 0

    @property
    def valid(self) -> bool:
        return self.lap_time_s > 0 and bool(self.driver_name)


@dataclass(slots=True)
class DeltaViewData:
    delta_s: float = 0.0
    session_time_text: str = "--:--:--"
    session_name: str = "Waiting"
    track_state: str = "Unknown"

    # Penalidades pendentes do carro.
    penalties: int = 0

    # Pontos/avisos de limite de pista e limite da sessão.
    penalties_current: float = 0.0
    penalties_limit: float = 0.0

    sectors: list[DeltaSectorData] = field(
        default_factory=lambda: [
            DeltaSectorData("S1"),
            DeltaSectorData("S2"),
            DeltaSectorData("S3"),
        ]
    )
    fastest_lap: FastestLapData | None = None
    fastest_laps: list[FastestLapData] = field(default_factory=list)
    fastest_alpha: float = 0.0
    session_key: str = ""
