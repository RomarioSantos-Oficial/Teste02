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

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = config

    def reset(self) -> None:
        self._session_key = ""
        self._start_overall.clear()
        self._start_class.clear()
        self._pit_started.clear()
        self._pit_elapsed.clear()

    def build(
        self,
        session: Any | None,
        metadata: dict[str, DriverMetadata],
        source_text: str,
    ) -> StandingsView:
        if session is None:
            return StandingsView(source_text=source_text)
        key = self._make_session_key(session)
        if key != self._session_key:
            self.reset()
            self._session_key = key
        drivers = sorted(
            list(getattr(session, "drivers", []) or []),
            key=lambda item: int(getattr(item, "position", 9999) or 9999),
        )
        class_positions = self._class_positions(drivers)
        rows = [self._row_from_driver(driver, session, metadata, class_positions) for driver in drivers]
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
        class_name = str(getattr(driver, "vehicle_class", "") or "UNKNOWN")
        class_key, display_name, _ = canonical_class(class_name, self.config)
        is_player = bool(getattr(driver, "is_player", False))
        energy = extra.energy_percent
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
        in_pits = bool(getattr(driver, "in_pits", False))
        now = time.monotonic()
        if in_pits:
            self._pit_started.setdefault(slot_id, now)
            self._pit_elapsed[slot_id] = now - self._pit_started[slot_id]
        else:
            self._pit_started.pop(slot_id, None)
        car_number = extra.car_number or extract_car_number(vehicle_name, name, slot_id)
        manufacturer = detect_manufacturer(vehicle_name, vehicle_filename, extra.manufacturer)
        return StandingRow(
            slot_id=slot_id,
            overall_position=overall,
            class_position=class_position,
            position_change=change,
            driver_name=name,
            team_name=extra.team_name,
            vehicle_name=vehicle_name,
            class_name=display_name,
            class_key=class_key,
            car_number=car_number,
            manufacturer=manufacturer,
            nationality=extra.nationality,
            country_code=extra.country_code,
            badge=extra.badge,
            laps=int(getattr(driver, "laps", 0) or 0),
            lap_distance_m=float(getattr(driver, "lap_distance_m", 0.0) or 0.0),
            best_lap_s=float(getattr(driver, "best_lap_s", 0.0) or 0.0),
            last_lap_s=float(getattr(driver, "last_lap_s", 0.0) or 0.0),
            gap_leader_s=float(getattr(driver, "gap_leader_s", 0.0) or 0.0),
            interval_s=float(getattr(driver, "gap_ahead_s", 0.0) or 0.0),
            tyre_compound=extra.tyre_compound,
            energy_percent=energy,
            damage_percent=extra.damage_percent,
            penalties=int(getattr(driver, "penalties", 0) or 0),
            finish_state=extra.finish_state,
            in_pits=in_pits,
            in_garage=bool(getattr(driver, "in_garage", False)),
            under_yellow=bool(getattr(driver, "under_yellow", False)),
            flag=int(getattr(driver, "flag", 0) or 0),
            is_player=is_player,
            pit_time_s=self._pit_elapsed.get(slot_id, 0.0),
        )

    def _category_blocks(
        self,
        rows: list[StandingRow],
        player: StandingRow | None,
        session: Any,
    ) -> list[CategoryBlock]:
        groups: dict[str, list[StandingRow]] = {}
        for row in rows:
            groups.setdefault(row.class_key, []).append(row)
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
            total_text = self._total_laps_text(reference, session)
            blocks.append(CategoryBlock(
                class_name=class_name,
                class_key=class_key,
                color=color,
                started=sum(1 for row in class_rows if row.overall_position > 0),
                total=len(class_rows),
                current_lap=current_lap,
                total_laps_text=total_text,
                rows=selected_rows,
            ))
        return blocks

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
        maximum = int(getattr(session, "max_laps", 0) or 0)
        if maximum > 0:
            return str(maximum)
        if reference is None:
            return "--"
        remaining = float(getattr(session, "remaining_time_s", 0.0) or 0.0)
        lap_time = reference.last_lap_s if reference.last_lap_s > 0 else reference.best_lap_s
        if remaining > 0 and lap_time > 0:
            progress = reference.laps + 1
            estimate = progress + remaining / lap_time
            return f"{estimate:.1f}"
        return "--"

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
