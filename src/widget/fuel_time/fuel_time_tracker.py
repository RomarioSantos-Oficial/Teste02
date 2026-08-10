from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import fmean
from typing import Any


@dataclass(slots=True)
class FuelTimeData:
    fuel_l: float = 0.0
    fuel_per_lap_l: float | None = None
    energy_per_lap_pct: float | None = None
    fuel_ratio: float | None = None
    laps_remaining: float | None = None
    fuel_laps: float | None = None
    fuel_needed_l: float | None = None
    fuel_to_add_l: float | None = None
    target_fuel_per_lap_l: float | None = None
    finish_fuel_l: float | None = None
    sample_count: int = 0
    reference: str = "aguardando voltas"


class FuelTimeTracker:
    """Mede consumo por volta e projeta a chegada (REST primeiro, memoria como fallback)."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._fuel_samples: deque[float] = deque(maxlen=8)
        self._energy_samples: deque[float] = deque(maxlen=8)
        self._session_key: tuple[Any, ...] | None = None
        self._lap: int | None = None
        self._lap_start_fuel: float | None = None
        self._lap_start_energy: float | None = None

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = config
        size = max(1, min(20, int(config.get("average_laps", 5))))
        self._fuel_samples = deque(self._fuel_samples, maxlen=size)
        self._energy_samples = deque(self._energy_samples, maxlen=size)

    def reset(self) -> None:
        self._fuel_samples.clear(); self._energy_samples.clear()
        self._lap = None; self._lap_start_fuel = None; self._lap_start_energy = None

    @staticmethod
    def _energy(player: Any) -> float | None:
        for key in ("virtual_energy", "state_of_charge", "battery_fraction"):
            try: value = float(getattr(player, key, 0.0) or 0.0)
            except (TypeError, ValueError): continue
            if value > 0: return value * 100.0 if value <= 1.0 else value
        return None

    @staticmethod
    def _player_driver(session: Any) -> Any | None:
        return next((d for d in list(getattr(session, "drivers", []) or []) if bool(getattr(d, "is_player", False))), None)

    def update(self, session: Any) -> FuelTimeData:
        player = getattr(session, "player", None)
        if player is None: return FuelTimeData()
        key = (getattr(session, "track_name", ""), getattr(session, "session", 0), getattr(session, "start_event_time_s", 0.0))
        if self._session_key != key: self.reset(); self._session_key = key
        fuel = max(0.0, float(getattr(player, "fuel_liters", 0.0) or 0.0))
        capacity = max(0.0, float(getattr(player, "fuel_capacity_liters", 0.0) or 0.0))
        lap = int(getattr(player, "lap", 0) or 0); energy = self._energy(player); driver = self._player_driver(session)
        in_pits = bool(getattr(driver, "in_pits", False) or getattr(driver, "in_garage", False))
        if self._lap is None:
            self._lap, self._lap_start_fuel, self._lap_start_energy = lap, fuel, energy
        elif lap < self._lap:
            self.reset(); self._lap, self._lap_start_fuel, self._lap_start_energy = lap, fuel, energy
        elif lap > self._lap:
            used = (self._lap_start_fuel or 0.0) - fuel
            if not in_pits and lap == self._lap + 1 and 0.03 < used <= max(capacity, 200.0):
                self._fuel_samples.append(used)
                if energy is not None and self._lap_start_energy is not None:
                    energy_used = self._lap_start_energy - energy
                    if 0.001 < energy_used <= 100.0: self._energy_samples.append(energy_used)
            self._lap, self._lap_start_fuel, self._lap_start_energy = lap, fuel, energy
        elif self._lap_start_fuel is not None and fuel > self._lap_start_fuel + 0.25:
            self._lap_start_fuel, self._lap_start_energy = fuel, energy

        fuel_avg = fmean(self._fuel_samples) if self._fuel_samples else None
        energy_avg = fmean(self._energy_samples) if self._energy_samples else None
        remaining, reference = self._remaining_laps(session, driver)
        reserve = max(0.0, float(self.config.get("reserve_laps", 1.0)))
        needed = fuel_avg * (remaining + reserve) if fuel_avg is not None and remaining is not None else None
        target = (fuel - reserve * fuel_avg) / remaining if fuel_avg and remaining and remaining > 0 else None
        return FuelTimeData(fuel, fuel_avg, energy_avg, fuel_avg / energy_avg if fuel_avg and energy_avg else None,
            remaining, fuel / fuel_avg if fuel_avg else None, needed, max(0.0, needed-fuel) if needed is not None else None,
            target, fuel-fuel_avg*remaining if fuel_avg is not None and remaining is not None else None,
            len(self._fuel_samples), reference)

    def _remaining_laps(self, session: Any, driver: Any | None) -> tuple[float | None, str]:
        length = float(getattr(session, "track_length_m", 0.0) or 0.0)
        progress = max(0.0, min(.999, float(getattr(driver, "lap_distance_m", 0.0) or 0.0)/length)) if driver is not None and length > 0 else 0.0
        completed = float(getattr(driver, "laps", getattr(getattr(session, "player", None), "lap", 0)) or 0)
        max_laps = int(getattr(session, "max_laps", 0) or 0)
        if max_laps > 0: return max(0.0, max_laps-completed-progress), "limite de voltas da API"
        remaining_s = float(getattr(session, "remaining_time_s", 0.0) or 0.0)
        if remaining_s <= 0: return None, "sem duracao da sessao"
        valid = [d for d in list(getattr(session, "drivers", []) or []) if float(getattr(d, "best_lap_s", 0.0) or 0.0) > 20]
        fastest = min(valid, key=lambda d: float(getattr(d, "best_lap_s", 0.0))) if valid else None
        leader_lap = float(getattr(fastest, "best_lap_s", 0.0) or 0.0) if fastest else 0.0
        player_lap = float(getattr(driver, "last_lap_s", 0.0) or 0.0) if driver else 0.0
        if player_lap <= 20 and driver is not None: player_lap = float(getattr(driver, "best_lap_s", 0.0) or 0.0)
        if player_lap <= 20: player_lap = leader_lap
        if player_lap <= 20: return None, "aguardando tempo de volta"
        return max(0.0, (remaining_s + (leader_lap or player_lap))/player_lap-progress), "tempo + classe mais rapida"
