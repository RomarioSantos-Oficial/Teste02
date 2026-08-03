from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FlagCar:
    slot_id: int = 0
    driver: str = ""
    category: str = ""
    position: int = 0
    distance: float = 0.0
    tempo_gap: float = 0.0
    raw_pos_x: float = 0.0
    raw_pos_y: float = 0.0
    speed_kmh: float = 0.0
    is_blue_context: bool = False


@dataclass(slots=True)
class FlagAlert:
    active: bool = False
    driver: str = ""
    category: str = ""
    position: int = 0
    distance: float = 0.0
    tempo_gap: float = 0.0
    cars: list[FlagCar] = field(default_factory=list)
    player_is_hazard: bool = False


@dataclass(slots=True)
class FlagsSnapshot:
    yellow: FlagAlert = field(default_factory=FlagAlert)
    blue: FlagAlert = field(default_factory=FlagAlert)
    green_active: bool = False
