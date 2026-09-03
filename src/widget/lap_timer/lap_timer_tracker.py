from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class LapTimerData:
    current_lap_s: float = 0.0
    last_lap_s: float = 0.0
    best_lap_s: float = 0.0
    predicted_lap_s: float = 0.0
    theoretical_lap_s: float = 0.0
    completed_laps: int = 0
    current_lap: int = 0
    estimated_total_laps: float | None = None
    remaining_laps: float | None = None
    position: int = 0
    field_count: int = 0
    class_position: int = 0
    class_count: int = 0
    current_invalid: bool = False
    last_invalid: bool = False


def displayed_lap_number(
    completed_laps: int,
    *,
    active: bool = True,
    finish_status: int = 0,
    maximum_laps: int = 0,
) -> int:
    """Converte o contador bruto do LMU para a volta exibida no jogo."""
    if not active:
        return 0
    completed = max(0, int(completed_laps))
    displayed = completed if int(finish_status) in {1, 2, 3} else completed + 1
    maximum = int(maximum_laps)
    if 0 < maximum <= 500:
        displayed = min(displayed, maximum)
    return displayed


def estimated_total_laps_text(value: float | None) -> str:
    """Formata o total estimado exatamente como o Lap Timer."""
    if value is None or not math.isfinite(value):
        return "--"
    if abs(value - round(value)) < 0.001:
        return str(int(round(value)))
    return f"~{int(math.ceil(value))}"


def estimate_laps(
    session: Any,
    driver: Any | None,
    class_rows: list[Any],
    completed: int,
    fraction: float,
) -> tuple[float | None, float | None]:
    """Calcula total e restante com a regra existente do Lap Timer."""
    maximum = int(getattr(session, "max_laps", 0) or 0)
    progress = completed + fraction
    if 0 < maximum <= 500:
        return float(maximum), max(0.0, maximum - progress)
    remaining_s = float(getattr(session, "remaining_time_s", 0.0) or 0.0)
    if remaining_s <= 0.0 or driver is None:
        return None, None
    player_pace = float(getattr(driver, "last_lap_s", 0.0) or 0.0)
    if player_pace < 3.0:
        player_pace = float(getattr(driver, "best_lap_s", 0.0) or 0.0)
    leader = min(
        class_rows,
        key=lambda d: int(getattr(d, "position_in_class", 9999) or 9999),
        default=None,
    )
    leader_pace = 0.0
    if leader is not None:
        leader_pace = float(getattr(leader, "last_lap_s", 0.0) or 0.0)
        if leader_pace < 3.0:
            leader_pace = float(getattr(leader, "best_lap_s", 0.0) or 0.0)
    if player_pace < 3.0:
        player_pace = leader_pace
    if player_pace < 3.0:
        return None, None
    # Inclui a volta de bandeirada. O ritmo do lider da categoria determina
    # quando a corrida encerra; o ritmo do carro de referencia determina
    # quantas voltas ele completa.
    finish_window = remaining_s + (
        leader_pace if leader_pace >= 3.0 else player_pace
    )
    remaining = max(0.0, finish_window / player_pace - fraction)
    total = progress + remaining
    if not math.isfinite(total) or total > progress + 500.0:
        return None, None
    return total, remaining


class LapTimerTracker:
    """Converte o scoring do LMU em valores de exibicao leves.

    O scoring pode atualizar o tempo dentro da volta abaixo da taxa de pintura.
    Guardamos a ultima amostra e interpolamos somente a apresentacao com um
    relogio monotônico. Nenhuma API ou arquivo e consultado neste caminho.
    """

    def __init__(self) -> None:
        self.data = LapTimerData()
        self._sample_lap_time = 0.0
        self._sample_clock = time.monotonic()
        self._running = False
        self._session_key: tuple[str, int] | None = None
        self._last_completed_laps: int | None = None
        self._last_lap_start = 0.0
        self._last_event_time = 0.0

    @staticmethod
    def _player_driver(session: Any) -> Any | None:
        drivers = list(getattr(session, "drivers", []) or [])
        return next((driver for driver in drivers if getattr(driver, "is_player", False)), None)

    def update(self, session: Any) -> LapTimerData:
        player = getattr(session, "player", None)
        driver = self._player_driver(session)
        live = getattr(driver, "live_scoring", None) if driver is not None else None
        live = live if isinstance(live, dict) else {}
        now = time.monotonic()
        key = (
            str(getattr(session, "track_name", "") or ""),
            int(getattr(session, "session", 0) or 0),
        )
        event_time = float(
            getattr(session, "current_event_time_s", 0.0)
            or getattr(session, "current_time_s", 0.0)
            or 0.0
        )
        session_restarted = (
            self._last_event_time > 10.0
            and event_time > 0.0
            and event_time + 10.0 < self._last_event_time
        )
        if self._session_key is not None and (key != self._session_key or session_restarted):
            self.data = LapTimerData()
            self._sample_lap_time = 0.0
            self._last_completed_laps = None
            self._last_lap_start = 0.0
        self._session_key = key
        if event_time > 0.0:
            self._last_event_time = event_time

        observed = (
            float(
                live.get(
                    "time_into_lap_s",
                    getattr(driver, "time_into_lap_s", 0.0),
                )
                or 0.0
            )
            if driver
            else 0.0
        )
        lap_start = (
            float(
                live.get(
                    "lap_start_event_time_s",
                    getattr(driver, "lap_start_event_time_s", 0.0),
                )
                or 0.0
            )
            if driver
            else 0.0
        )
        if observed <= 0.0 and driver is not None:
            if event_time > lap_start > 0.0:
                observed = event_time - lap_start
        previous = self.current_lap_time(now)
        running_now = bool(
            getattr(session, "in_realtime", False)
            and not getattr(session, "telemetry_paused", False)
            and player is not None
        )
        completed_now = int(
            live.get(
                "laps",
                getattr(driver, "laps", getattr(player, "lap", 0)),
            )
            or 0
        )
        lap_counter_advanced = (
            self._last_completed_laps is not None
            and completed_now > self._last_completed_laps
        )
        lap_start_advanced = (
            self._last_lap_start > 0.0
            and lap_start > self._last_lap_start + 0.5
        )
        # Uma amostra menor, sozinha, nunca zera o cronometro: memoria e REST
        # podem alternar durante o enriquecimento. A nova volta exige uma
        # transicao autoritativa do contador ou do instante de inicio.
        new_lap = lap_counter_advanced or lap_start_advanced
        if new_lap or observed >= previous - 0.12 or self._sample_lap_time <= 0.0:
            self._sample_lap_time = max(0.0, observed if new_lap else max(observed, previous))
            self._sample_clock = now
        if not running_now and observed > 0.0:
            self._sample_lap_time = observed
            self._sample_clock = now
        self._running = running_now
        self._last_completed_laps = completed_now
        if lap_start > 0.0:
            self._last_lap_start = lap_start

        drivers = list(getattr(session, "drivers", []) or [])
        class_key = str(getattr(driver, "vehicle_class", "") or "") if driver else ""
        class_rows = [d for d in drivers if str(getattr(d, "vehicle_class", "") or "") == class_key]
        completed = completed_now
        track_length = float(getattr(session, "track_length_m", 0.0) or 0.0)
        lap_distance = (
            float(
                live.get(
                    "lap_distance_m",
                    getattr(driver, "lap_distance_m", 0.0),
                )
                or 0.0
            )
            if driver
            else 0.0
        )
        fraction = max(0.0, min(0.999, lap_distance / track_length)) if track_length > 0.0 else 0.0
        estimated_total, remaining = self._lap_estimate(session, driver, class_rows, completed, fraction)

        theoretical = 0.0
        if driver is not None:
            sectors = (
                float(getattr(driver, "best_sector1_s", 0.0) or 0.0),
                float(getattr(driver, "best_sector2_s", 0.0) or 0.0),
                float(getattr(driver, "best_sector3_s", 0.0) or 0.0),
            )
            if all(value > 0.0 for value in sectors):
                theoretical = sum(sectors)

        best_lap = float(getattr(driver, "best_lap_s", 0.0) or 0.0) if driver else 0.0
        game_prediction = float(getattr(driver, "estimated_lap_s", 0.0) or 0.0) if driver else 0.0
        delta_best = float(getattr(player, "delta_best_s", 0.0) or 0.0) if player else 0.0
        # A previsao que o piloto espera ver e dinamica: melhor volta pessoal
        # somada ao delta atual. Ex.: 92.000 + (-1.000) = 91.000. O valor
        # estimado do scoring permanece como fallback antes da primeira melhor.
        predicted_lap = best_lap + delta_best if best_lap > 0.0 else game_prediction
        if not math.isfinite(predicted_lap) or predicted_lap < 3.0:
            predicted_lap = game_prediction if game_prediction >= 3.0 else 0.0

        self.data = LapTimerData(
            current_lap_s=self.current_lap_time(now),
            last_lap_s=float(getattr(driver, "last_lap_s", 0.0) or 0.0) if driver else 0.0,
            best_lap_s=best_lap,
            predicted_lap_s=predicted_lap,
            theoretical_lap_s=theoretical,
            completed_laps=completed,
            current_lap=displayed_lap_number(
                completed,
                active=player is not None,
                finish_status=(
                    int(getattr(driver, "finish_status", 0) or 0)
                    if driver is not None
                    else 0
                ),
                maximum_laps=int(getattr(session, "max_laps", 0) or 0),
            ),
            estimated_total_laps=estimated_total,
            remaining_laps=remaining,
            position=int(getattr(driver, "position", 0) or 0) if driver else 0,
            field_count=len(drivers),
            class_position=int(getattr(driver, "position_in_class", 0) or 0) if driver else 0,
            class_count=len(class_rows),
            current_invalid=bool(getattr(player, "current_lap_invalidated", False)) if player else False,
            last_invalid=bool(getattr(driver, "last_lap_invalidated", False)) if driver else False,
        )
        return self.data

    def current_lap_time(self, now: float | None = None) -> float:
        value = self._sample_lap_time
        if self._running:
            value += max(0.0, (time.monotonic() if now is None else now) - self._sample_clock)
        return max(0.0, value)

    @staticmethod
    def _lap_estimate(
        session: Any, driver: Any | None, class_rows: list[Any], completed: int, fraction: float
    ) -> tuple[float | None, float | None]:
        return estimate_laps(session, driver, class_rows, completed, fraction)
