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
    ("LMGT3", ("lmgt3", "gt3"), "#058B12"),
    ("LMGT4", ("lmgt4", "gt4"), "#D98200"),
)


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
            key=lambda item: int(getattr(item, "position", 9999) or 9999),
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
        self._apply_lap_states(rows, now)
        self._last_current_time = float(
            getattr(session, "current_time_s", 0.0) or 0.0
        )
        player = next((row for row in rows if row.is_player), None)
        class_leaders = self._class_leaders(rows)
        for row in rows:
            row.gap_text = self._gap_text(row, player, class_leaders.get(row.class_key), session)
        categories = self._category_blocks(rows, player, session)
        return StandingsView(
            connected=bool(getattr(session, "connected", False)),
            session_type=self._session_type(int(getattr(session, "session", 0) or 0)),
            session_time=self._format_duration(float(getattr(session, "remaining_time_s", 0.0) or 0.0)),
            server_time=self._server_time(float(getattr(session, "time_of_day", 0.0) or 0.0)),
            local_time=datetime.now().strftime("%H:%M"),
            grip_text=self._grip_text(session),
            track_limits_text=self._track_limits_text(session),
            source_text=source_text,
            track_name=str(getattr(session, "track_name", "") or ""),
            categories=categories,
        )

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
        overall = int(getattr(driver, "position", 0) or 0)
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
        in_pits = bool(getattr(driver, "in_pits", False)) or bool(
            getattr(driver, "pitting", False)
        )
        completed_laps = int(getattr(driver, "laps", 0) or 0)
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
        if damage_percent is None and is_player:
            raw_damage = _optional_float(
                getattr(getattr(session, "player", None), "vehicle_damage", None)
            )
            if raw_damage is not None:
                damage_percent = (
                    raw_damage * 100.0 if raw_damage <= 1.0 else raw_damage
                )
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
            estimated_driver_rank_gain=extra.estimated_driver_rank_gain,
            laps=completed_laps,
            lap_distance_m=float(getattr(driver, "lap_distance_m", 0.0) or 0.0),
            best_lap_s=float(getattr(driver, "best_lap_s", 0.0) or 0.0),
            last_lap_s=float(getattr(driver, "last_lap_s", 0.0) or 0.0),
            current_lap_invalidated=current_lap_invalidated,
            last_lap_invalidated=last_lap_invalidated,
            gap_leader_s=float(getattr(driver, "gap_leader_s", 0.0) or 0.0),
            interval_s=float(getattr(driver, "gap_ahead_s", 0.0) or 0.0),
            tyre_compound=extra.tyre_compound,
            energy_percent=energy,
            damage_percent=damage_percent,
            penalties=int(getattr(driver, "penalties", 0) or 0),
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
            under_yellow=bool(getattr(driver, "under_yellow", False)),
            flag=int(getattr(driver, "flag", 0) or 0),
            is_player=is_player,
            pit_time_s=self._pit_elapsed.get(slot_id, 0.0),
            pit_status_visible=pit_status_visible,
        )

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
        maximum_classes = max(1, min(3, int(self.config.get("maximum_categories", 3))))
        if len(ordered) > maximum_classes:
            selected = ordered[:maximum_classes]
            if player is not None and all(key != player.class_key for key, _ in selected):
                player_item = next((item for item in ordered if item[0] == player.class_key), None)
                if player_item is not None:
                    selected[-1] = player_item
            ordered = selected
        num_classes = len(ordered)
        blocks: list[CategoryBlock] = []
        for class_key, class_rows in ordered:
            class_rows.sort(key=lambda row: row.class_position or 9999)
            is_player_class = player is not None and class_key == player.class_key
            if num_classes == 1:
                selected_rows = self._select_player_class(class_rows, 10, 1)
            elif is_player_class:
                selected_rows = self._select_player_class(class_rows, 8, num_classes)
            else:
                selected_rows = class_rows[:3]
            class_name = class_rows[0].class_name if class_rows else class_key
            _, _, color = canonical_class(class_key, self.config)
            reference = player if is_player_class else (class_rows[0] if class_rows else None)
            current_lap = (reference.laps + 1) if reference is not None else 0
            total_text, total_calc = self._total_laps_info(reference, session, class_rows)
            active_count = sum(
                1 for row in class_rows if self._is_active_race_car(row)
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
                show_count=is_race,
                rows=selected_rows,
            ))
        return blocks

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
        indices: set[int] = set()
        player_index = next((index for index, row in enumerate(rows) if row.is_player), -1)
        if number_classes == 1:
            if player_index != -1:
                indices.add(player_index)
            indices.update(range(min(3, len(rows))))
            if player_index >= 3:
                for offset in range(-3, 4):
                    index = player_index + offset
                    if 0 <= index < len(rows):
                        indices.add(index)
                        if len(indices) >= limit:
                            break
        else:
            if rows:
                indices.add(0)
            if player_index != -1:
                indices.add(player_index)
            if player_index > 0:
                remaining = max(0, limit - 2)
                before = remaining // 2
                after = remaining - before
                for offset in range(1, before + 2):
                    index = player_index - offset
                    if index > 0:
                        indices.add(index)
                for offset in range(1, after + 2):
                    index = player_index + offset
                    if index < len(rows):
                        indices.add(index)
        if len(indices) < limit:
            start = 1 if number_classes > 1 else 0
            for index in range(start, len(rows)):
                indices.add(index)
                if len(indices) >= limit:
                    break
        return [rows[index] for index in sorted(indices)[:limit]]

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
            return "PLAYER" if row.is_player else "P1"
        track_length = float(getattr(session, "track_length_m", 0.0) or 0.0)
        if track_length > 0:
            row_progress = row.laps + max(0.0, row.lap_distance_m) / track_length
            ref_progress = reference.laps + max(0.0, reference.lap_distance_m) / track_length
            lap_diff = row_progress - ref_progress
            if abs(lap_diff) >= 0.85:
                return f"{lap_diff:+.0f}L"
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
            progress = reference.laps + 1
            # Estimativa de quantas voltas cabem no tempo restante usando a volta de referência
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
