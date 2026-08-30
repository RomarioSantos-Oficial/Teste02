# SectorFlow is an open-source overlay application for racing simulation.
# Copyright (C) 2022-2026 SectorFlow developers
# Based on the user-provided Standings Hybrid reference.
#
# This file is part of SectorFlow.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.


from __future__ import annotations

import math
import re
import time
from dataclasses import replace
from datetime import datetime
from typing import Any

from .standings_assets import detect_manufacturer
from .standings_models import (
    CategoryBlock,
    DriverMetadata,
    StandingRow,
    StandingsView,
    normalize_identity,
)


CLASS_RULES = (
    ("HYPERCAR", ("hyper", "lmh", "lmdh"), "#D81736"),
    ("LMP2", ("lmp2",), "#1265A8"),
    ("LMP3", ("lmp3",), "#8548F6"),
    ("GTE", ("gte",), "#F58220"),
    ("LMGT3", ("lmgt3", "gt3"), "#058B12"),
    ("LMGT4", ("lmgt4", "gt4"), "#D98200"),
)


def _truncate_tenth(value: float) -> float:
    """Limita a uma casa decimal sem arredondar para cima."""
    numeric = float(value)
    # Tolera o pequeno erro binario de operacoes como 15.7 - 10.0.
    epsilon = math.copysign(1e-9, numeric) if numeric else 0.0
    return math.trunc((numeric + epsilon) * 10.0) / 10.0


def _live_scoring_value(driver: Any, key: str, default: Any = 0) -> Any:
    """Lê o scoring coerente da memória antes do valor enriquecido pelo REST."""
    live = getattr(driver, "live_scoring", None)
    if isinstance(live, dict) and key in live:
        return live[key]
    return getattr(driver, key, default)


def _race_progress(row: StandingRow, track_length_m: float) -> float | None:
    if not math.isfinite(track_length_m) or track_length_m <= 1.0:
        return None
    distance = float(row.lap_distance_m or 0.0)
    if not math.isfinite(distance):
        return None
    fraction = max(0.0, min(1.0, distance / track_length_m))
    return max(0, int(row.laps)) + fraction


def _official_lap_relation(
    row: StandingRow,
    reference: StandingRow,
) -> int | None:
    """Retorna a relação com o mesmo sinal dos gaps: frente -, atrás +."""
    row_behind = int(row.laps_behind_leader)
    reference_behind = int(reference.laps_behind_leader)
    if row_behind < 0 or reference_behind < 0:
        return None
    return row_behind - reference_behind


def _reference_lap_time(*rows: StandingRow) -> float:
    for attribute in ("estimated_lap_s", "last_lap_s", "best_lap_s"):
        for row in rows:
            value = float(getattr(row, attribute, 0.0) or 0.0)
            if math.isfinite(value) and 3.0 <= value <= 1800.0:
                return value
    return 0.0


def _relative_time_seconds(
    row: StandingRow,
    reference: StandingRow,
    track_length_m: float,
) -> float | None:
    """Calcula segundos relativos sem subtrair gaps de voltas diferentes."""
    row_progress = _race_progress(row, track_length_m)
    reference_progress = _race_progress(reference, track_length_m)
    progress_delta = (
        row_progress - reference_progress
        if row_progress is not None and reference_progress is not None
        else None
    )
    row_time = float(row.time_into_lap_s or 0.0)
    reference_time = float(reference.time_into_lap_s or 0.0)
    timing_available = (
        row.lap_start_event_time_s > 0.0
        and reference.lap_start_event_time_s > 0.0
    ) or row_time != 0.0 or reference_time != 0.0
    lap_time = _reference_lap_time(reference, row)

    if timing_available and math.isfinite(row_time) and math.isfinite(reference_time):
        if progress_delta is not None and progress_delta != 0.0:
            if progress_delta > 0.0:
                # row está à frente da referência.
                interval = row_time - reference_time
                if interval < 0.0 and lap_time > 0.0:
                    interval += lap_time
                return -abs(interval)
            # reference está à frente de row.
            interval = reference_time - row_time
            if interval < 0.0 and lap_time > 0.0:
                interval += lap_time
            return abs(interval)
        seconds = row_time - reference_time
        if math.isfinite(seconds):
            return seconds

    if progress_delta is not None and lap_time > 0.0:
        return -progress_delta * lap_time
    return None


def format_driver_name(value: Any, mode: str = "full") -> str:
    """Formata apenas a exibicao, preservando o nome original para identidade."""
    name = " ".join(str(value or "").split())
    parts = name.split()
    if len(parts) < 2 or mode == "full":
        return name
    if mode == "first_last_initial":
        surname_initials = " ".join(f"{part[0].upper()}." for part in parts[1:])
        return f"{parts[0]} {surname_initials}"
    if mode == "first_initial_last":
        return f"{parts[0][0].upper()}. {' '.join(parts[1:])}"
    return name


class StandingsLogic:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._session_key = ""
        self._start_overall: dict[int, int] = {}
        self._start_class: dict[int, int] = {}
        self._pit_started: dict[int, float] = {}
        self._pit_elapsed: dict[int, float] = {}
        self._pit_was_inside: dict[int, bool] = {}
        self._pit_exit_lap: dict[int, int] = {}
        self._previous_best_laps: dict[int, float] = {}
        self._personal_best_until: dict[int, float] = {}
        self._observed_laps_once = False
        self._race_totals: dict[str, int] = {}
        self._last_current_time = 0.0
        self._delta_seen_laps: dict[int, int] = {}
        self._delta_lap_history: dict[int, list[float]] = {}

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = config

    def reset(self) -> None:
        self._session_key = ""
        self._start_overall.clear()
        self._start_class.clear()
        self._pit_started.clear()
        self._pit_elapsed.clear()
        self._pit_was_inside.clear()
        self._pit_exit_lap.clear()
        self._previous_best_laps.clear()
        self._personal_best_until.clear()
        self._observed_laps_once = False
        self._race_totals.clear()
        self._last_current_time = 0.0
        self._delta_seen_laps.clear()
        self._delta_lap_history.clear()

    def build(
        self,
        session: Any | None,
        metadata: dict[str, DriverMetadata],
        source_text: str,
        vehicle_catalog: dict[str, dict[str, str]] | None = None,
    ) -> StandingsView:
        if session is None:
            return StandingsView(source_text=source_text)
        key = self._make_session_key(session)
        if self._session_changed(key, session):
            self.reset()
            self._session_key = key
        now = time.monotonic()
        drivers = sorted(
            list(getattr(session, "drivers", []) or []),
            key=lambda item: int(
                _live_scoring_value(item, "position", 9999) or 9999
            ),
        )
        class_positions = self._class_positions(drivers)
        rows = [
            self._row_from_driver(
                driver,
                session,
                metadata,
                class_positions,
                vehicle_catalog or {},
                now,
            )
            for driver in drivers
        ]
        if (
            bool(self.config.get("show_estimated_driver_rank_gain", False))
            and 10 <= int(getattr(session, "session", 0) or 0) <= 13
        ):
            self._estimate_driver_rank_gains(rows)
        self._apply_lap_states(rows, now)
        session_number = int(getattr(session, "session", 0) or 0)
        if 10 <= session_number <= 13:
            self._update_delta_lap_history(rows)
        self._last_current_time = float(
            getattr(session, "current_time_s", 0.0) or 0.0
        )
        player = next((row for row in rows if row.is_player), None)
        class_leaders = self._class_leaders(rows)
        for row in rows:
            row.gap_text = self._gap_text(row, player, class_leaders.get(row.class_key), session)
        if 10 <= session_number <= 13:
            self._apply_class_intervals(
                rows,
                float(getattr(session, "track_length_m", 0.0) or 0.0),
            )
            self._apply_rolling_deltas(rows, player)
        categories = (
            self._relative_block(rows, player, session)
            if bool(self.config.get("relative_mode", False))
            else self._category_blocks(rows, player, session)
        )
        return StandingsView(
            connected=bool(getattr(session, "connected", False)),
            session_type=self._session_type(session_number),
            session_time=self._format_duration(float(getattr(session, "remaining_time_s", 0.0) or 0.0)),
            server_time=self._server_time(float(getattr(session, "time_of_day", 0.0) or 0.0)),
            local_time=datetime.now().strftime("%H:%M"),
            grip_text=self._grip_text(session),
            track_limits_text=self._track_limits_text(session),
            source_text=source_text,
            track_name=str(getattr(session, "track_name", "") or ""),
            categories=categories,
        )

    def _update_delta_lap_history(self, rows: list[StandingRow]) -> None:
        """Guarda os tempos das ultimas voltas de cada piloto."""
        for row in rows:
            slot = row.slot_id
            completed = max(0, int(row.laps))
            previous = self._delta_seen_laps.get(slot)
            if previous is None:
                self._delta_seen_laps[slot] = completed
                self._delta_lap_history.setdefault(slot, [])
                continue
            if completed < previous:
                self._delta_seen_laps[slot] = completed
                self._delta_lap_history[slot] = []
                continue
            if completed == previous:
                continue
            lap_time = float(row.last_lap_s or 0.0)
            if math.isfinite(lap_time) and 10.0 <= lap_time <= 1800.0:
                history = self._delta_lap_history.setdefault(slot, [])
                history.append(lap_time)
                del history[:-10]
            self._delta_seen_laps[slot] = completed

    def _apply_rolling_deltas(
        self,
        rows: list[StandingRow],
        player: StandingRow | None,
    ) -> None:
        if player is None:
            return
        sample = max(1, min(10, int(self.config.get("delta_sample_laps", 5))))
        player_history = self._delta_lap_history.get(player.slot_id, [])
        for row in rows:
            row.rolling_delta_s = None
            row.rolling_delta_text = "--"
            if row.class_key != player.class_key:
                continue
            rival_history = self._delta_lap_history.get(row.slot_id, [])
            available = min(sample, len(player_history), len(rival_history))
            if available <= 0:
                continue
            player_laps = player_history[-available:]
            rival_laps = rival_history[-available:]
            # Compara volta a volta e mostra a media da amostragem. Um valor
            # positivo significa que, em media, o rival gastou mais tempo que
            # o jogador. Isto e independente do INT instantaneo na pista.
            lap_differences = [
                rival_lap - player_lap
                for player_lap, rival_lap in zip(player_laps, rival_laps)
            ]
            value = sum(lap_differences) / available
            rounded = round(value, 1)
            if abs(rounded) < 0.05:
                rounded = 0.0
                text = "0.0"
            else:
                text = f"{rounded:+.1f}"
            row.rolling_delta_s = rounded
            row.rolling_delta_text = text

    @staticmethod
    def _apply_class_intervals(
        rows: list[StandingRow],
        track_length_m: float = 0.0,
    ) -> None:
        """Preenche INT somente contra o carro anterior da mesma classe."""
        overall = sorted(rows, key=lambda row: row.overall_position or 9999)
        overall_previous = {
            id(row): (overall[index - 1] if index else None)
            for index, row in enumerate(overall)
        }
        by_class: dict[str, list[StandingRow]] = {}
        for row in rows:
            by_class.setdefault(row.class_key, []).append(row)

        for class_rows in by_class.values():
            class_rows.sort(key=lambda row: row.class_position or 9999)
            for index, row in enumerate(class_rows):
                row.interval_text = "--"
                if index == 0:
                    continue
                previous = class_rows[index - 1]

                # lapsBehindLeader possui a mesma base para todos os carros e
                # continua válido mesmo quando outra categoria aparece entre
                # os dois na classificação geral.
                official_lap_delta = _official_lap_relation(row, previous)
                if official_lap_delta is not None and official_lap_delta > 0:
                    row.interval_text = f"+{official_lap_delta}L"
                    continue

                # A API fornece timeBehindNext/lapsBehindNext para a ordem
                # geral. Eles so servem ao INT de classe quando o carro geral
                # imediatamente anterior e o mesmo anterior desta categoria.
                if overall_previous.get(id(row)) is previous:
                    if row.laps_behind_ahead > 0:
                        row.interval_text = f"+{row.laps_behind_ahead}L"
                        continue
                    if row.interval_s > 0 and official_lap_delta == 0:
                        row.interval_text = f"+{_truncate_tenth(row.interval_s):.1f}"
                        continue

                previous_progress = _race_progress(previous, track_length_m)
                row_progress = _race_progress(row, track_length_m)
                if official_lap_delta is None and (
                    previous_progress is not None and row_progress is not None
                ):
                    progress_delta = previous_progress - row_progress
                    if progress_delta >= 1.0:
                        row.interval_text = f"+{max(1, math.floor(progress_delta + 1e-9))}L"
                        continue

                interval = _relative_time_seconds(row, previous, track_length_m)
                if interval is not None and abs(interval) >= 0.05:
                    row.interval_text = f"+{_truncate_tenth(abs(interval)):.1f}"
                    continue

                # Último fallback, seguro apenas quando a informação oficial
                # confirma que ambos pertencem à mesma volta do líder.
                if official_lap_delta == 0:
                    interval = row.gap_leader_s - previous.gap_leader_s
                    if interval >= 0 and (
                        row.gap_leader_s > 0 or previous.gap_leader_s > 0
                    ):
                        row.interval_text = f"+{_truncate_tenth(interval):.1f}"

    def _relative_block(
        self,
        rows: list[StandingRow],
        player: StandingRow | None,
        session: Any,
    ) -> list[CategoryBlock]:
        if player is None:
            return []
        track_length = float(getattr(session, "track_length_m", 0.0) or 0.0)
        if track_length <= 1.0:
            return []
        # O Relative oficial/TinyPedal usa a volta estimada publicada para a
        # sessao. Em multicategoria nao podemos escolher a menor best lap do
        # grid: isso faria um Hypercar/GT3 mudar o gap do jogador apenas por
        # pertencer a uma classe mais rapida ou mais lenta.
        reference_lap = player.estimated_lap_s
        if reference_lap <= 20.0:
            reference_lap = player.best_lap_s
        if reference_lap <= 20.0:
            reference_lap = player.last_lap_s
        if reference_lap <= 20.0:
            estimates = [
                row.estimated_lap_s
                for row in rows
                if row.estimated_lap_s > 20.0
            ]
            same_class_laps = [
                row.best_lap_s
                for row in rows
                if row.class_key == player.class_key and row.best_lap_s > 20.0
            ]
            any_class_laps = [row.best_lap_s for row in rows if row.best_lap_s > 20.0]
            reference_lap = (
                min(estimates) if estimates
                else min(same_class_laps) if same_class_laps
                else min(any_class_laps) if any_class_laps
                else 90.0
            )

        relative_ahead: list[tuple[float, StandingRow]] = []
        relative_behind: list[tuple[float, StandingRow]] = []
        for row in rows:
            if row.is_player:
                row.gap_text = "0.0"
                continue
            if not self._is_relative_car_visible(row):
                continue
            distance = row.lap_distance_m - player.lap_distance_m
            if distance > track_length / 2.0:
                distance -= track_length
            elif distance < -track_length / 2.0:
                distance += track_length
            distance_seconds = distance / track_length * reference_lap
            # Mesmo metodo do TinyPedal/module_relative.py: para cada carro
            # cria um gap circular positivo (frente) e negativo (atras).
            # O modulo mantem os valores continuos quando timeIntoLap zera.
            row_time = float(row.time_into_lap_s or 0.0)
            player_time = float(player.time_into_lap_s or 0.0)
            # O LMU publica valores negativos validos antes da largada
            # (tempo ate cruzar a linha). TinyPedal usa mTimeIntoLap sem
            # descartar o sinal, portanto fazemos o mesmo quando o relogio
            # de inicio da volta confirma que o dado existe.
            timing_available = (
                row.lap_start_event_time_s > 0.0
                and player.lap_start_event_time_s > 0.0
            ) or row_time != 0.0 or player_time != 0.0
            if timing_available:
                raw_seconds = row_time - player_time
                ahead_seconds = raw_seconds % reference_lap
                behind_seconds = ahead_seconds - reference_lap if ahead_seconds > 0 else 0.0
            else:
                ahead_seconds = distance_seconds % reference_lap
                behind_seconds = ahead_seconds - reference_lap if ahead_seconds > 0 else 0.0
            relative_ahead.append((ahead_seconds, row))
            relative_behind.append((behind_seconds, row))

        ahead_count = max(1, min(20, int(self.config.get("relative_cars_ahead", 5))))
        behind_count = max(1, min(20, int(self.config.get("relative_cars_behind", 5))))
        ahead = sorted((item for item in relative_ahead if item[0] > 0), key=lambda item: item[0])[:ahead_count]
        behind = sorted(
            (item for item in relative_behind if item[0] < 0),
            key=lambda item: item[0], reverse=True,
        )[:behind_count]
        # Um mesmo carro pode aparecer nas duas direcoes do circuito. Cada
        # ocorrencia precisa de uma linha independente para que o gap de tras
        # nao sobrescreva o gap mostrado na frente.
        selected: list[tuple[float, StandingRow]] = []
        for seconds, row in list(reversed(ahead)):
            relative = _truncate_tenth(-seconds)
            selected.append((seconds, replace(row, gap_text=f"{relative:+.1f}")))
        selected.append((0.0, player))
        for seconds, row in behind:
            relative = _truncate_tenth(-seconds)
            selected.append((seconds, replace(row, gap_text=f"{relative:+.1f}")))
        player_color = str(
            self.config.get("class_colors", {}).get(player.class_key, "#175C9C")
        )
        return [
            CategoryBlock(
                class_name="RELATIVE",
                class_key=player.class_key,
                color=player_color,
                started=len(rows),
                total=len(rows),
                rows=[row for _, row in selected],
            )
        ]

    @staticmethod
    def _is_relative_car_visible(row: StandingRow) -> bool:
        """Relative contém somente carros ainda ativos fora da garagem."""
        finish = str(row.finish_state or "").strip().casefold()
        return not (
            row.in_garage
            or row.finish_status in {2, 3}
            or finish in {
                "dnf", "didnotfinish", "did not finish", "fstat_dnf", "2",
                "dq", "disqualified", "fstat_dq", "3",
            }
        )

    def _fuel_display(
        self,
        driver: Any,
        session: Any,
        class_key: str,
        raw_class_name: str,
        is_player: bool,
        vehicle_identity: str = "",
    ) -> tuple[float | None, float | None, bool]:
        """Return fuel for non-energy classes, using exact player data when possible."""
        if class_key not in {"GTE", "LMP2", "LMP3"}:
            return None, None, False

        fraction = _optional_float(getattr(driver, "fuel_fraction", None))
        if fraction is not None and not 0.0 <= fraction <= 1.0:
            fraction = None
        player_data = getattr(session, "player", None)
        if is_player and player_data is not None:
            liters = _optional_float(getattr(player_data, "fuel_liters", None))
            capacity = _optional_float(
                getattr(player_data, "fuel_capacity_liters", None)
            )
            if liters is not None and capacity is not None and capacity > 0.0:
                percent = max(0.0, min(100.0, liters / capacity * 100.0))
                return max(0.0, liters), percent, False

        if fraction is None:
            return None, None, False
        capacities = self.config.get("fuel_capacity_defaults_l", {})
        if not isinstance(capacities, dict):
            capacities = {}
        raw = str(raw_class_name or "").casefold()
        if class_key == "LMP2":
            capacity_key = (
                "LMP2_WEC"
                if "wec" in raw or "wec" in str(vehicle_identity).casefold()
                else "LMP2"
            )
            fallback = 63.0 if capacity_key == "LMP2_WEC" else 75.0
        elif class_key == "LMP3":
            capacity_key, fallback = "LMP3", 100.0
        else:
            vehicle = str(vehicle_identity or "").casefold()
            gte_capacities = (
                ("GTE_ASTON_MARTIN", ("aston", "vantage"), 95.0),
                ("GTE_CORVETTE", ("corvette", "c8.r", "c8r"), 91.0),
                ("GTE_FERRARI", ("ferrari", "488"), 84.0),
                ("GTE_PORSCHE", ("porsche", "rsr"), 98.0),
            )
            matched = next(
                (
                    (key, default)
                    for key, aliases, default in gte_capacities
                    if any(alias in vehicle for alias in aliases)
                ),
                None,
            )
            capacity_key, fallback = matched or ("GTE", 90.0)
        capacity = _optional_float(capacities.get(capacity_key)) or fallback
        return fraction * capacity, fraction * 100.0, True

    def _row_from_driver(
        self,
        driver: Any,
        session: Any,
        metadata: dict[str, DriverMetadata],
        class_positions: dict[int, int],
        vehicle_catalog: dict[str, dict[str, str]],
        now: float,
    ) -> StandingRow:
        slot_id = int(getattr(driver, "slot_id", 0) or 0)
        overall = int(_live_scoring_value(driver, "position", 0) or 0)
        class_position = class_positions.get(slot_id, int(getattr(driver, "position_in_class", 0) or 0))
        self._start_overall.setdefault(slot_id, overall)
        self._start_class.setdefault(slot_id, class_position)
        if bool(self.config.get("position_change_in_class", True)):
            change = self._start_class[slot_id] - class_position
        else:
            change = self._start_overall[slot_id] - overall
        name = str(getattr(driver, "driver_name", "") or "")
        extra = metadata.get(normalize_identity(name), DriverMetadata(driver_name=name))
        vehicle_name = extra.vehicle_name or str(getattr(driver, "vehicle_name", "") or "")
        vehicle_filename = str(getattr(driver, "vehicle_filename", "") or "")
        catalog_entry = vehicle_catalog.get(
            normalize_identity(vehicle_name),
            {},
        )
        class_name = str(getattr(driver, "vehicle_class", "") or "UNKNOWN")
        class_key, display_name, _ = canonical_class(class_name, self.config)
        is_player = bool(getattr(driver, "is_player", False))
        current_lap_invalidated = bool(
            getattr(driver, "current_lap_invalidated", False)
        )
        last_lap_invalidated = bool(
            getattr(driver, "last_lap_invalidated", False)
        )
        if extra.current_lap_invalidated is not None:
            current_lap_invalidated = bool(extra.current_lap_invalidated)
        if extra.last_lap_invalidated is not None:
            last_lap_invalidated = bool(extra.last_lap_invalidated)
        if is_player:
            player_data = getattr(session, "player", None)
            if player_data is not None:
                current_lap_invalidated = bool(
                    getattr(
                        player_data,
                        "current_lap_invalidated",
                        current_lap_invalidated,
                    )
                )
                last_lap_invalidated = bool(
                    getattr(
                        player_data,
                        "last_lap_invalidated",
                        last_lap_invalidated,
                    )
                )
        rest_energy = _optional_float(
            getattr(driver, "virtual_energy_fraction", None)
        )
        energy = (
            rest_energy * 100.0
            if rest_energy is not None and 0.0 <= rest_energy <= 1.0
            else extra.energy_percent
        )
        if energy is None and extra.energy_remaining_fraction is not None:
            remaining = extra.energy_remaining_fraction
            used = extra.energy_use_per_lap
            reference_lap = extra.energy_reference_lap
            track_length = float(
                getattr(session, "track_length_m", 0.0) or 0.0
            )
            lap_fraction = (
                max(
                    0.0,
                    float(getattr(driver, "lap_distance_m", 0.0) or 0.0),
                )
                / track_length
                if track_length > 0.0
                else 0.0
            )
            total_progress = (
                float(getattr(driver, "laps", 0) or 0)
                + min(1.0, lap_fraction)
            )
            if (
                used is not None
                and used > 0.0
                and reference_lap is not None
                and total_progress > reference_lap
            ):
                remaining -= (
                    used
                    * 0.95
                    * (total_progress - reference_lap)
                )
            energy = max(0.0, min(100.0, remaining * 100.0))
        if is_player and energy is None:
            player_data = getattr(session, "player", None)
            if player_data is not None:
                for field in ("battery_fraction", "state_of_charge", "virtual_energy"):
                    value = _optional_float(getattr(player_data, field, None))
                    if value is not None and value > 0:
                        energy = value * 100.0 if value <= 1.0 else value
                        if 0.0 <= energy <= 100.0:
                            break
                        energy = None
        fuel_liters, fuel_percent, fuel_is_estimated = self._fuel_display(
            driver,
            session,
            class_key,
            class_name,
            is_player,
            " ".join(
                (
                    vehicle_name,
                    vehicle_filename,
                    extra.vehicle_model,
                    str(catalog_entry.get("manufacturer", "") or ""),
                )
            ),
        )
        # As classes sem sistema de energia virtual usam esta mesma coluna
        # para combustivel. Um zero de VE vindo da API nao deve esconder os
        # litros disponiveis.
        if fuel_liters is not None:
            energy = None
        in_pits = bool(getattr(driver, "in_pits", False)) or bool(
            getattr(driver, "pitting", False)
        )
        completed_laps = int(_live_scoring_value(driver, "laps", 0) or 0)
        was_in_pits = self._pit_was_inside.get(slot_id, False)
        if in_pits:
            self._pit_started.setdefault(slot_id, now)
            self._pit_elapsed[slot_id] = now - self._pit_started[slot_id]
            self._pit_exit_lap.pop(slot_id, None)
        else:
            if was_in_pits:
                self._pit_exit_lap[slot_id] = completed_laps
            self._pit_started.pop(slot_id, None)
        self._pit_was_inside[slot_id] = in_pits
        pit_status_laps = max(
            0,
            int(self.config.get("pit_status_laps", 2) or 0),
        )
        pit_exit_lap = self._pit_exit_lap.get(slot_id)
        pit_status_visible = bool(
            self.config.get("show_pit_status", True)
        ) and (
            in_pits
            or (
                pit_exit_lap is not None
                and completed_laps < pit_exit_lap + pit_status_laps
            )
        )
        car_number = (
            extra.car_number
            or str(getattr(driver, "car_number", "") or "")
            or extract_car_number(vehicle_name, name, slot_id)
        )
        vehicle_model = (
            extra.vehicle_model
            or str(catalog_entry.get("model", "") or "")
        )
        player_model = ""
        if is_player:
            player_model = str(
                getattr(getattr(session, "player", None), "vehicle_model", "")
                or ""
            )
            vehicle_model = vehicle_model or player_model
        manufacturer = detect_manufacturer(
            " ".join((vehicle_name, vehicle_model, player_model)),
            vehicle_filename,
            extra.manufacturer
            or str(catalog_entry.get("manufacturer", "") or ""),
        )
        damage_percent = extra.damage_percent
        damage_is_estimated = False
        if damage_percent is None and is_player:
            raw_damage = _optional_float(
                getattr(getattr(session, "player", None), "vehicle_damage", None)
            )
            if raw_damage is not None:
                damage_percent = (
                    raw_damage * 100.0 if raw_damage <= 1.0 else raw_damage
                )
        if damage_percent is None:
            damage_percent = _optional_float(
                getattr(driver, "damage_percent", None)
            )
            damage_is_estimated = bool(
                getattr(driver, "damage_is_estimated", False)
            )
        raw_tyre_compounds = list(
            (getattr(driver, "tire_compounds", []) or [])[:4]
        )
        tyre_compounds = tuple(
            str(value or "").strip() for value in raw_tyre_compounds
        )
        if not any(tyre_compounds) and extra.tyre_compound:
            parts = [
                part.strip()
                for part in str(extra.tyre_compound).split("/")
                if part.strip()
            ]
            if len(parts) >= 4:
                tyre_compounds = tuple(parts[:4])
            elif len(parts) == 2:
                # O enriquecimento REST compacto publica dianteiro/traseiro.
                tyre_compounds = (parts[0], parts[0], parts[1], parts[1])
            else:
                tyre_compounds = (str(extra.tyre_compound).strip(),) * 4
        return StandingRow(
            slot_id=slot_id,
            overall_position=overall,
            class_position=class_position,
            position_change=change,
            driver_name=name,
            team_name=(
                extra.team_name
                or str(getattr(driver, "team_name", "") or "")
            ),
            vehicle_name=vehicle_name,
            vehicle_model=vehicle_model,
            class_name=display_name,
            class_key=class_key,
            car_number=car_number,
            manufacturer=manufacturer,
            nationality=extra.nationality,
            country_code=extra.country_code,
            badge=extra.badge,
            driver_rank=extra.driver_rank,
            driver_rank_progress=extra.driver_rank_progress,
            safety_rank=extra.safety_rank,
            safety_rank_progress=extra.safety_rank_progress,
            estimated_driver_rank_gain=extra.estimated_driver_rank_gain,
            laps=completed_laps,
            lap_distance_m=float(
                _live_scoring_value(driver, "lap_distance_m", 0.0) or 0.0
            ),
            time_into_lap_s=float(
                _live_scoring_value(driver, "time_into_lap_s", 0.0) or 0.0
            ),
            lap_start_event_time_s=float(
                _live_scoring_value(driver, "lap_start_event_time_s", 0.0)
                or 0.0
            ),
            best_lap_s=float(getattr(driver, "best_lap_s", 0.0) or 0.0),
            estimated_lap_s=float(
                getattr(driver, "estimated_lap_s", 0.0) or 0.0
            ),
            last_lap_s=float(getattr(driver, "last_lap_s", 0.0) or 0.0),
            current_lap_invalidated=current_lap_invalidated,
            last_lap_invalidated=last_lap_invalidated,
            gap_leader_s=float(
                _live_scoring_value(driver, "gap_leader_s", 0.0) or 0.0
            ),
            interval_s=float(
                _live_scoring_value(driver, "gap_ahead_s", 0.0) or 0.0
            ),
            tyre_compound=(
                extra.tyre_compound
                or self._compound_label(
                    getattr(driver, "tire_compounds", [])
                )
            ),
            tyre_compounds=tyre_compounds,
            energy_percent=energy,
            fuel_liters=fuel_liters,
            fuel_percent=fuel_percent,
            fuel_is_estimated=fuel_is_estimated,
            damage_percent=damage_percent,
            damage_is_estimated=damage_is_estimated,
            penalties=int(getattr(driver, "penalties", 0) or 0),
            track_limits_text=self._driver_track_limits_text(
                driver, session, is_player
            ),
            penalty_text=self._penalty_text(driver, session, is_player),
            laps_behind_leader=int(
                _live_scoring_value(driver, "laps_behind_leader", 0) or 0
            ),
            laps_behind_ahead=int(
                _live_scoring_value(driver, "laps_behind_ahead", 0) or 0
            ),
            finish_state=(
                extra.finish_state
                or str(getattr(driver, "finish_status_name", "") or "")
                or (
                    str(int(getattr(driver, "finish_status", 0) or 0))
                    if int(getattr(driver, "finish_status", 0) or 0)
                    in {2, 3}
                    else ""
                )
            ),
            finish_status=int(
                getattr(driver, "finish_status", 0) or 0
            ),
            in_pits=in_pits,
            in_garage=bool(getattr(driver, "in_garage", False)),
            under_yellow=(
                bool(getattr(driver, "under_yellow", False))
                or int(getattr(driver, "flag", 0) or 0) in {1, 2}
                # Mesmo fallback usado pelo TinyPedal: um carro muito lento
                # fora do pit/garagem e tratado como causador de amarela.
                or (
                    float(getattr(driver, "speed_kmh", 0.0) or 0.0) < 28.8
                    and not in_pits
                    and not bool(getattr(driver, "in_garage", False))
                    and int(getattr(session, "game_phase", 0) or 0) >= 5
                    and int(getattr(driver, "finish_status", 0) or 0) == 0
                )
            ),
            flag=int(getattr(driver, "flag", 0) or 0),
            is_player=is_player,
            pit_time_s=self._pit_elapsed.get(slot_id, 0.0),
            pit_status_visible=pit_status_visible,
        )

    @staticmethod
    def _compound_label(values: Any) -> str:
        compounds = [str(value or "").strip() for value in (values or [])]
        compounds = [value for value in compounds if value]
        if not compounds:
            return ""
        if len(set(compounds)) == 1:
            return compounds[0]
        if len(compounds) >= 4:
            front = compounds[0] if compounds[0] == compounds[1] else "/".join(compounds[:2])
            rear = compounds[2] if compounds[2] == compounds[3] else "/".join(compounds[2:4])
            return front if front == rear else f"{front}/{rear}"
        return "/".join(dict.fromkeys(compounds))

    @staticmethod
    def _penalty_text(driver: Any, session: Any, is_player: bool) -> str:
        finish = int(getattr(driver, "finish_status", 0) or 0)
        finish_name = str(getattr(driver, "finish_status_name", "") or "").upper()
        if finish == 3 or finish_name in {"DQ", "FSTAT_DQ", "DISQUALIFIED"}:
            return "DQ"
        raw_type = str(getattr(driver, "penalty_type", "") or "").strip().upper()
        seconds = float(getattr(driver, "penalty_time_s", 0.0) or 0.0)
        if raw_type:
            if "DRIVE" in raw_type or raw_type in {"DT", "DRIVETHROUGH"}:
                return "DT"
            if "STOP" in raw_type or raw_type.startswith("SG"):
                return f"SG{seconds:.0f}" if seconds > 0.0 else "SG"
            if "TIME" in raw_type and seconds > 0.0:
                return f"+{seconds:.0f}"
            if "DISQUAL" in raw_type or raw_type == "DQ":
                return "DQ"
            return raw_type[:5]
        if seconds > 0.0:
            return f"+{seconds:.0f}"
        count = max(0, int(getattr(driver, "penalties", 0) or 0))
        if count > 0:
            # REST e shared memory informam a quantidade, nao o tipo. Evita
            # apresentar P1 como se fosse o nome de uma punicao.
            return "PEN"
        return "--"

    @staticmethod
    def _driver_track_limits_text(driver: Any, session: Any, is_player: bool) -> str:
        points = getattr(driver, "track_limits_points", None)
        steps = getattr(driver, "track_limits_steps", None)
        if points is None and steps is not None:
            steps_per_point = max(
                1,
                int(getattr(session, "track_limits_steps_per_point", 0) or 0),
            )
            points = float(steps) / steps_per_point
        if points is None and is_player:
            points = float(getattr(session, "track_limits_current", 0.0) or 0.0)
        if points is None:
            return "--"
        limit = float(getattr(session, "track_limits_limit", 0.0) or 0.0)
        return f"{points:g}/{limit:g}" if limit > 0.0 else f"{points:g}"

    def _apply_lap_states(
        self,
        rows: list[StandingRow],
        now: float,
    ) -> None:
        highlight_seconds = max(
            0.0,
            float(self.config.get("lap_highlight_seconds", 5.0) or 0.0),
        )

        for row in rows:
            current = row.best_lap_s
            previous = self._previous_best_laps.get(row.slot_id, 0.0)
            new_personal_best = (
                current > 0.0
                and (
                    (previous > 0.0 and current < previous - 0.0005)
                    or (previous <= 0.0 and self._observed_laps_once)
                )
            )
            if new_personal_best and highlight_seconds > 0.0:
                self._personal_best_until[row.slot_id] = (
                    now + highlight_seconds
                )
            if current > 0.0:
                self._previous_best_laps[row.slot_id] = current
            row.personal_best_highlight = (
                now < self._personal_best_until.get(row.slot_id, 0.0)
            )

        valid_best_times = [
            row.best_lap_s for row in rows if row.best_lap_s > 0.0
        ]
        session_fastest = min(valid_best_times, default=0.0)
        for row in rows:
            row.is_session_fastest = (
                session_fastest > 0.0
                and abs(row.best_lap_s - session_fastest) <= 0.0005
            )

        self._observed_laps_once = True

    def _category_blocks(
        self,
        rows: list[StandingRow],
        player: StandingRow | None,
        session: Any,
    ) -> list[CategoryBlock]:
        groups: dict[str, list[StandingRow]] = {}
        for row in rows:
            groups.setdefault(row.class_key, []).append(row)
        session_number = int(getattr(session, "session", 0) or 0)
        is_race = 10 <= session_number <= 13
        if is_race:
            for class_key, class_rows in groups.items():
                self._race_totals[class_key] = max(
                    self._race_totals.get(class_key, 0),
                    len(class_rows),
                )
        ordered = sorted(groups.items(), key=lambda item: min((row.overall_position or 9999) for row in item[1]))
        if player is not None:
            player_item = next((item for item in ordered if item[0] == player.class_key), None)
            if player_item is not None:
                ordered.remove(player_item)
                ordered.append(player_item)
        maximum_classes = max(
            1,
            min(5, int(self.config.get("maximum_categories", 3))),
        )
        if len(ordered) > maximum_classes:
            selected = ordered[:maximum_classes]
            if player is not None and all(key != player.class_key for key, _ in selected):
                player_item = next((item for item in ordered if item[0] == player.class_key), None)
                if player_item is not None:
                    selected[-1] = player_item
            ordered = selected
        num_classes = len(ordered)
        blocks: list[CategoryBlock] = []
        player_row_limit = max(
            1,
            min(10, int(self.config.get("player_category_rows", 8))),
        )
        other_row_limit = max(
            1,
            min(5, int(self.config.get("other_category_rows", 3))),
        )
        for class_key, class_rows in ordered:
            class_rows.sort(key=lambda row: row.class_position or 9999)
            is_player_class = player is not None and class_key == player.class_key
            if is_player_class:
                selected_rows = self._select_player_class(
                    class_rows,
                    player_row_limit,
                    num_classes,
                )
            else:
                selected_rows = self._select_priority_rows(
                    class_rows, other_row_limit
                )
            class_name = class_rows[0].class_name if class_rows else class_key
            _, _, color = canonical_class(class_key, self.config)
            leader_reference = class_rows[0] if class_rows else None
            reference = (
                leader_reference
                if is_race
                else (player if is_player_class else leader_reference)
            )
            current_lap = (reference.laps + 1) if reference is not None else 0
            if is_race:
                total_text, total_calc = self._total_laps_info(
                    leader_reference,
                    session,
                    class_rows,
                )
            else:
                total_text, total_calc = "--", "session_not_race"
            active_count = sum(
                1 for row in class_rows if self._is_active_race_car(row)
            )
            sof_rank, sof_progress, sof_drivers = self._driver_rank_sof(
                class_rows
            )
            blocks.append(CategoryBlock(
                class_name=class_name,
                class_key=class_key,
                color=color,
                started=(active_count if is_race else len(class_rows)),
                total=(
                    self._race_totals.get(class_key, len(class_rows))
                    if is_race
                    else len(class_rows)
                ),
                current_lap=current_lap,
                total_laps_text=total_text,
                total_laps_calc=total_calc,
                # A quantidade de pilotos tambem e util em treino e quali.
                # Na corrida o primeiro numero representa somente ativos;
                # nas demais sessoes representa todos os inscritos da classe.
                show_count=bool(class_rows),
                dr_sof_rank=sof_rank,
                dr_sof_progress=sof_progress,
                dr_sof_drivers=sof_drivers,
                rows=selected_rows,
            ))
        return blocks

    @staticmethod
    def _driver_rank_sof(
        rows: list[StandingRow],
    ) -> tuple[str, float | None, int]:
        tier_base = {
            "bronze": 0,
            "silver": 3,
            "gold": 6,
            "platinum": 9,
        }
        values: list[float] = []
        for row in rows:
            match = re.search(
                r"(bronze|silver|gold|platinum)\s*([1-3])?",
                str(row.driver_rank or ""),
                re.IGNORECASE,
            )
            if match is None:
                continue
            progress = _optional_float(row.driver_rank_progress)
            if progress is None:
                progress = 0.0
            if 0.0 <= progress <= 1.0:
                progress *= 100.0
            values.append(
                tier_base[match.group(1).casefold()]
                + max(0, int(match.group(2) or 1) - 1)
                + max(0.0, min(100.0, progress)) / 100.0
            )
        if not values:
            return "", None, 0
        average = max(0.0, min(11.999, sum(values) / len(values)))
        whole = int(average)
        tier_index = whole // 3
        tier = ("B", "S", "G", "P")[tier_index]
        subrank = whole % 3 + 1
        progress = (average - whole) * 100.0
        return f"{tier}{subrank}", progress, len(values)

    @classmethod
    def _estimate_driver_rank_gains(cls, rows: list[StandingRow]) -> None:
        """Preenche um delta local quando RaceControl nao publica a previsao.

        E uma estimativa Elo relativa ao grid da propria classe. Valores que
        vierem da API sao sempre preservados e continuam tendo prioridade.
        """
        grouped: dict[str, list[tuple[StandingRow, float]]] = {}
        for row in rows:
            value = cls._driver_rank_value(row)
            if value is not None:
                grouped.setdefault(row.class_key, []).append((row, value))
        for class_rows in grouped.values():
            if len(class_rows) < 2:
                continue
            for row, rating in class_rows:
                if row.estimated_driver_rank_gain is not None:
                    continue
                actual_total = expected_total = 0.0
                comparisons = 0
                for opponent, opponent_rating in class_rows:
                    if opponent.slot_id == row.slot_id:
                        continue
                    actual = (
                        1.0 if row.class_position < opponent.class_position
                        else 0.0 if row.class_position > opponent.class_position
                        else 0.5
                    )
                    expected = 1.0 / (1.0 + 10.0 ** ((opponent_rating - rating) / 4.0))
                    actual_total += actual; expected_total += expected; comparisons += 1
                if comparisons:
                    # Limite de seis pontos percentuais reduz os saltos com
                    # grids pequenos; o valor final e identificado como
                    # estimativa pelo sinal junto ao progresso do DR.
                    delta = 6.0 * (
                        actual_total / comparisons - expected_total / comparisons
                    )
                    row.estimated_driver_rank_gain = max(-6.0, min(6.0, delta))

    @staticmethod
    def _driver_rank_value(row: StandingRow) -> float | None:
        match = re.search(
            r"(bronze|silver|gold|platinum)\s*([1-3])?",
            str(row.driver_rank or ""), re.IGNORECASE,
        )
        if match is None:
            return None
        base = {"bronze": 0, "silver": 3, "gold": 6, "platinum": 9}
        progress = _optional_float(row.driver_rank_progress) or 0.0
        if 0.0 <= progress <= 1.0:
            progress *= 100.0
        subrank = max(1, min(3, int(match.group(2) or 1)))
        return base[match.group(1).casefold()] + subrank - 1 + max(0.0, min(100.0, progress)) / 100.0

    @staticmethod
    def _is_active_race_car(row: StandingRow) -> bool:
        finish = row.finish_state.casefold()
        inactive_finish = finish in {
            "dnf",
            "didnotfinish",
            "dq",
            "disqualified",
            "2",
            "3",
        }
        return (
            row.overall_position > 0
            and row.finish_status not in {2, 3}
            and not inactive_finish
            and not row.in_garage
        )

    @staticmethod
    def _select_player_class(rows: list[StandingRow], limit: int, number_classes: int) -> list[StandingRow]:
        player_index = next((index for index, row in enumerate(rows) if row.is_player), -1)
        limit = max(1, min(limit, len(rows))) if rows else 0
        if player_index < 0:
            return rows[:limit]
        if limit == 1:
            return [rows[player_index]]
        indices: set[int] = {player_index}
        # O líder permanece visível, mas punição/amarela nunca puxa para o
        # painel um carro distante do recorte escolhido pelo usuário.
        if len(indices) < limit:
            indices.add(0)
        distance = 1
        while len(indices) < limit and distance < len(rows):
            before = player_index - distance
            after = player_index + distance
            if before >= 0:
                indices.add(before)
            if len(indices) < limit and after < len(rows):
                indices.add(after)
            distance += 1
        for index in range(len(rows)):
            if len(indices) >= limit:
                break
            indices.add(index)
        return [rows[index] for index in sorted(indices)[:limit]]

    @staticmethod
    def _is_priority_row(row: StandingRow) -> bool:
        return (
            row.under_yellow
            or row.flag in {1, 2}
            or row.penalties > 0
            or row.penalty_text not in {"", "--"}
        )

    @staticmethod
    def _priority_key(row: StandingRow) -> tuple[int, int]:
        yellow = row.under_yellow or row.flag in {1, 2}
        return (0 if yellow else 1, row.class_position or 9999)

    @staticmethod
    def _select_priority_rows(rows: list[StandingRow], limit: int) -> list[StandingRow]:
        limit = max(1, min(limit, len(rows))) if rows else 0
        return rows[:limit]

    @staticmethod
    def _class_positions(drivers: list[Any]) -> dict[int, int]:
        counters: dict[str, int] = {}
        result: dict[int, int] = {}
        for driver in drivers:
            key, _, _ = canonical_class(str(getattr(driver, "vehicle_class", "") or "UNKNOWN"), {})
            counters[key] = counters.get(key, 0) + 1
            result[int(getattr(driver, "slot_id", 0) or 0)] = counters[key]
        return result

    @staticmethod
    def _class_leaders(rows: list[StandingRow]) -> dict[str, StandingRow]:
        leaders: dict[str, StandingRow] = {}
        for row in rows:
            current = leaders.get(row.class_key)
            if current is None or (row.class_position or 9999) < (current.class_position or 9999):
                leaders[row.class_key] = row
        return leaders

    def _gap_text(
        self,
        row: StandingRow,
        player: StandingRow | None,
        leader: StandingRow | None,
        session: Any,
    ) -> str:
        session_number = int(getattr(session, "session", 0) or 0)
        is_race = 10 <= session_number <= 13
        if not is_race:
            if leader is None or row.slot_id == leader.slot_id:
                return "--"
            if row.best_lap_s > 0 and leader.best_lap_s > 0:
                return f"+{row.best_lap_s - leader.best_lap_s:.3f}"
            return "--"
        reference = player if player is not None and player.class_key == row.class_key else leader
        if reference is None:
            return "--"
        if row.slot_id == reference.slot_id:
            # O jogador e a origem dos gaps da propria categoria.
            return "0.0" if row.is_player else "P1"
        track_length = float(getattr(session, "track_length_m", 0.0) or 0.0)
        official_lap_relation = _official_lap_relation(row, reference)
        if official_lap_relation:
            # Mantém o mesmo sinal usado nos segundos: frente -, atrás +.
            return f"{official_lap_relation:+d}L"

        row_progress = _race_progress(row, track_length)
        reference_progress = _race_progress(reference, track_length)
        progress_delta = (
            row_progress - reference_progress
            if row_progress is not None and reference_progress is not None
            else None
        )
        if official_lap_relation is None:
            # Valores negativos de lapsBehindLeader são transitórios na linha.
            # Só o progresso completo pode confirmar uma volta nesse caso.
            if progress_delta is not None and abs(progress_delta) >= 1.0:
                completed_laps = max(1, math.floor(abs(progress_delta) + 1e-9))
                relation = -completed_laps if progress_delta > 0.0 else completed_laps
                return f"{relation:+d}L"
            if progress_delta is None and abs(row.laps - reference.laps) >= 1:
                relation = reference.laps - row.laps
                return f"{relation:+d}L"

        # timeBehindLeader só possui uma base comparável quando o LMU confirma
        # que os dois carros estão na mesma volta relativa ao líder.
        gap = 0.0
        if official_lap_relation == 0:
            gap = row.gap_leader_s - reference.gap_leader_s
        if abs(gap) < 0.05:
            calculated = _relative_time_seconds(row, reference, track_length)
            if calculated is not None:
                gap = calculated
            elif official_lap_relation is None:
                # Durante o único tick inválido da linha ainda é melhor manter
                # o pequeno gap oficial do que apagar a informação.
                gap = row.gap_leader_s - reference.gap_leader_s
        if abs(gap) < 0.05:
            return "0.0"
        return f"{gap:+.1f}"

    @staticmethod
    def _total_laps_text(reference: StandingRow | None, session: Any) -> str:
        # Compatibilidade retroativa: delega para a nova função que retorna
        # também a explicação do cálculo. Aqui não temos acesso a class_rows
        # então chamamos a versão reduzida (classe vazia) que tenta com a
        # referência apenas.
        text, _ = StandingsLogic._total_laps_info(reference, session, [])
        return text

    @staticmethod
    def _total_laps_info(reference: StandingRow | None, session: Any, class_rows: list[StandingRow] | None = None) -> tuple[str, str]:
        """Retorna (texto, explicacao).

        - texto: valor curto a exibir (ex: '18' ou '18.3' ou '--')
        - explicacao: string curta explicando a fonte do cálculo
          (ex: 'ref=leader lap=92.3s rem=600s est=18.3')
        """
        maximum = int(getattr(session, "max_laps", 0) or 0)
        if maximum > 0:
            # sanity-check para evitar valores absurdos vindos do servidor
            if maximum < 1 or maximum > 500:
                return "--", f"bad_fixed:{maximum}"
            return str(maximum), f"fixo={maximum}"
        if reference is None:
            return "--", "no_ref"
        try:
            remaining = float(getattr(session, "remaining_time_s", 0.0) or 0.0)
        except (TypeError, ValueError):
            remaining = 0.0
        lap_time = reference.last_lap_s if reference.last_lap_s > 0 else reference.best_lap_s
        if remaining > 0 and lap_time > 0:
            # Rejeitar voltas de referência impossivelmente curtas (dados corrompidos)
            if lap_time < 3.0:
                return "--", f"lap_time_too_small:{lap_time:.3f}s"
            track_length = float(
                getattr(session, "track_length_m", 0.0) or 0.0
            )
            lap_fraction = (
                max(0.0, min(0.999, reference.lap_distance_m / track_length))
                if track_length > 0.0
                else 0.0
            )
            progress = reference.laps + lap_fraction
            # Estimativa fracionaria usando o progresso dentro da volta e o
            # tempo restante fornecido diretamente pela API do jogo.
            estimate = progress + remaining / lap_time
            # Limites razoáveis para evitar overflow/valores absurdos
            if estimate < 0 or estimate > progress + 500:
                return "--", "bad_estimate"
            # Evitar estimativas muito elevadas por divisão por valores pequenos
            if remaining / lap_time > 200:
                return "--", "large_ratio"
            calc = f"ref={ 'player' if reference.is_player else 'leader' } lap={lap_time:.1f}s rem={int(remaining)}s est={estimate:.1f}"
            # Se a estimativa parece muito superior ao esperado, tentar usar
            # a média da classe (quando disponível) como fallback.
            if estimate > progress + 20 and class_rows:
                valid = [r.best_lap_s for r in class_rows if r.best_lap_s > 0]
                if valid:
                    avg = sum(valid) / len(valid)
                    if 3.0 <= avg <= 600.0:
                        alt_est = progress + remaining / avg
                        if 0 <= alt_est <= progress + 500 and remaining / avg <= 200:
                            calc = f"ref=class_avg lap={avg:.1f}s rem={int(remaining)}s est={alt_est:.1f}"
                            return f"{alt_est:.1f}", calc
            return f"{estimate:.1f}", calc
        # Sem tempo/volta válida
        return "--", "no_time"

    @staticmethod
    def _session_type(number: int) -> str:
        if 1 <= number <= 4:
            return "Practice"
        if 5 <= number <= 8:
            return "Quali"
        if 10 <= number <= 13:
            return "Race"
        return "Session"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        if seconds <= 0:
            return "--:--"
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def _server_time(seconds: float) -> str:
        if seconds <= 0:
            return "--:--"
        seconds = int(seconds) % 86400
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        return f"{hours:02d}:{minutes:02d}"

    @staticmethod
    def _grip_text(session: Any) -> str:
        rain = float(getattr(session, "raining", 0.0) or 0.0)
        wet = float(getattr(session, "avg_path_wetness", 0.0) or 0.0)
        if rain >= 0.25 or wet >= 0.22:
            return "Wet"
        if rain >= 0.02 or wet >= 0.035:
            return "Damp"
        return "Dry"

    @staticmethod
    def _track_limits_text(session: Any) -> str:
        try:
            current = float(getattr(session, "track_limits_current", 0.0) or 0.0)
            limit = float(getattr(session, "track_limits_limit", 0.0) or 0.0)
        except (TypeError, ValueError):
            return "-- / --"
        if limit <= 0:
            return f"{current:g}x / --"
        return f"{current:g}x / {limit:g}x"

    def _session_changed(self, key: str, session: Any) -> bool:
        if not self._session_key or key != self._session_key:
            return True
        current_time = float(
            getattr(session, "current_time_s", 0.0) or 0.0
        )
        return (
            self._last_current_time > 2.0
            and current_time + 2.0 < self._last_current_time
        )

    @staticmethod
    def _make_session_key(session: Any) -> str:
        return "|".join((
            str(getattr(session, "track_name", "") or ""),
            str(getattr(session, "session", 0) or 0),
            str(getattr(session, "max_laps", 0) or 0),
        ))


def canonical_class(value: str, config: dict[str, Any]) -> tuple[str, str, str]:
    lower = str(value or "UNKNOWN").casefold()
    custom = config.get("class_colors", {}) if isinstance(config, dict) else {}
    for key, keywords, default_color in CLASS_RULES:
        if any(keyword in lower for keyword in keywords) or lower == key.casefold():
            return key, key, str(custom.get(key, default_color))
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(value or "UNKNOWN")).upper()[:12] or "UNKNOWN"
    return cleaned, cleaned, str(custom.get(cleaned, "#1D5C91"))


def extract_car_number(vehicle_name: str, driver_name: str, slot_id: int) -> str:
    for source in (vehicle_name, driver_name):
        match = re.search(r"#\s*(\d{1,3})", str(source or ""))
        if match:
            return match.group(1)
    return str(slot_id) if 0 < slot_id <= 999 else ""


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
