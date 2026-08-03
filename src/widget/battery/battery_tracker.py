#  SectorFlow is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 SectorFlow developers
#  Based on TinyPedal - Copyright (C) 2022-2026 TinyPedal developers
#
#  This file is part of SectorFlow.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from __future__ import annotations

import math
from bisect import bisect_left
from typing import Any

from .battery_models import (
    BatteryLapMetrics,
    BatteryViewData,
)


class BatteryLapTracker:
    """
    Mede o uso real da bateria por volta e compara a volta atual com
    a última volta válida na mesma distância da pista.

    Uso líquido:
        descarga acumulada - regeneração acumulada

    Delta:
        uso atual - uso da volta anterior na mesma distância

    Delta negativo = gastando menos que na última volta.
    Delta positivo = gastando mais que na última volta.
    """

    MOTOR_STATES = {
        0: "OFF",
        1: "IDLE",
        2: "BOOST",
        3: "REGEN",
    }

    def __init__(
        self,
        config: dict[str, Any],
    ) -> None:
        self.config = config
        self.reset()

    def update_config(
        self,
        config: dict[str, Any],
    ) -> None:
        self.config = config

    def reset(self) -> None:
        self._session_key = ""
        self._last_session_time: float | None = None
        self._last_lap: int | None = None
        self._last_charge_pct: float | None = None

        self._current_drain_pct = 0.0
        self._current_regen_pct = 0.0
        self._current_samples: list[
            tuple[float, float]
        ] = []
        self._last_samples: list[
            tuple[float, float]
        ] = []
        self._last_metrics = BatteryLapMetrics()

        self._last_sample_distance = -1.0
        self._ever_available = False

    def update(
        self,
        session: Any,
    ) -> BatteryViewData:
        player = getattr(
            session,
            "player",
            None,
        )

        if player is None:
            return BatteryViewData()

        player_row = self._player_row(
            session
        )
        session_key = self._make_session_key(
            session
        )
        session_time = self._float(
            session,
            "current_time_s",
        )

        restarted = (
            self._last_session_time is not None
            and session_time
            < self._last_session_time - 3.0
        )
        self._last_session_time = session_time

        if (
            session_key != self._session_key
            or restarted
        ):
            self.reset()
            self._session_key = session_key
            self._last_session_time = session_time

        class_name = str(
            getattr(
                player_row,
                "vehicle_class",
                "",
            )
            or ""
        )
        charge_pct, source_name = (
            self._charge_percent(
                player,
                class_name,
            )
        )

        motor_state = self._int(
            player,
            "electric_motor_state",
        )
        regen_kw = self._float(
            player,
            "regen_kw",
        )
        torque_nm = self._float(
            player,
            "electric_motor_torque_nm",
        )
        motor_rpm = self._float(
            player,
            "electric_motor_rpm",
        )
        motor_power_kw = (
            torque_nm
            * motor_rpm
            * 2.0
            * math.pi
            / 60.0
            / 1000.0
        )

        raw_available = (
            self._float(
                player,
                "battery_fraction",
            )
            > 0.0
            or self._float(
                player,
                "state_of_charge",
            )
            > 0.0
            or self._float(
                player,
                "virtual_energy",
            )
            > 0.0
            or motor_state > 0
            or abs(regen_kw) > 0.01
            or abs(torque_nm) > 0.01
            or "HYPER" in class_name.upper()
            or "LMDH" in class_name.upper()
            or "LMH" in class_name.upper()
        )
        self._ever_available = (
            self._ever_available
            or raw_available
        )
        available = (
            bool(
                self.config.get(
                    "always_show",
                    False,
                )
            )
            or self._ever_available
        )

        lap = self._int(
            player,
            "lap",
        )
        distance_m = max(
            0.0,
            self._float(
                player_row,
                "lap_distance_m",
            ),
        )
        track_length_m = max(
            0.0,
            self._float(
                session,
                "track_length_m",
            ),
        )
        in_pits = bool(
            getattr(
                player_row,
                "in_pits",
                False,
            )
        ) or bool(
            getattr(
                player_row,
                "in_garage",
                False,
            )
        )

        if (
            self._last_lap is not None
            and lap < self._last_lap
        ):
            self.reset()
            self._session_key = session_key
            self._last_session_time = session_time

        if self._last_lap is None:
            self._last_lap = lap
            self._last_charge_pct = (
                charge_pct
            )

        elif lap != self._last_lap:
            self._finish_lap(
                in_pits=in_pits,
            )
            self._last_lap = lap
            self._last_charge_pct = (
                charge_pct
            )

        else:
            self._accumulate_charge_change(
                charge_pct=charge_pct,
                in_pits=in_pits,
            )

        current_net = (
            self._current_drain_pct
            - self._current_regen_pct
        )

        sample_distance = max(
            5.0,
            float(
                self.config.get(
                    "sample_distance_m",
                    25.0,
                )
            ),
        )
        if (
            distance_m >= 0.0
            and (
                self._last_sample_distance < 0
                or distance_m
                - self._last_sample_distance
                >= sample_distance
            )
        ):
            self._current_samples.append(
                (
                    distance_m,
                    current_net,
                )
            )
            self._last_sample_distance = (
                distance_m
            )

        last_at_distance = (
            self._value_at_distance(
                self._last_samples,
                distance_m,
            )
        )
        delta = (
            current_net
            - last_at_distance
            if last_at_distance is not None
            else None
        )

        progress = (
            min(
                1.0,
                distance_m / track_length_m,
            )
            if track_length_m > 0.0
            else 0.0
        )
        projected = None
        minimum_projection_progress = max(
            0.05,
            min(
                0.90,
                float(
                    self.config.get(
                        "projection_min_progress",
                        0.15,
                    )
                ),
            ),
        )

        if (
            progress
            >= minimum_projection_progress
            and current_net > 0.02
        ):
            projected = (
                current_net
                / max(
                    progress,
                    0.01,
                )
            )

        reference_use = (
            projected
            if projected is not None
            and projected > 0.05
            else (
                self._last_metrics.net_use_pct
                if (
                    self._last_metrics.completed
                    and self._last_metrics.net_use_pct
                    > 0.05
                )
                else None
            )
        )
        laps_remaining = (
            charge_pct / reference_use
            if reference_use is not None
            else None
        )

        virtual_energy = self._fraction_percent(
            self._float(
                player,
                "virtual_energy",
            )
        )

        return BatteryViewData(
            available=available,
            charge_pct=charge_pct,
            virtual_energy_pct=virtual_energy,
            current_lap=lap,
            lap_progress_pct=progress * 100.0,
            current=BatteryLapMetrics(
                drain_pct=self._current_drain_pct,
                regen_pct=self._current_regen_pct,
                net_use_pct=current_net,
                completed=False,
            ),
            last=BatteryLapMetrics(
                drain_pct=self._last_metrics.drain_pct,
                regen_pct=self._last_metrics.regen_pct,
                net_use_pct=self._last_metrics.net_use_pct,
                completed=self._last_metrics.completed,
            ),
            delta_vs_last_pct=delta,
            projected_lap_use_pct=projected,
            laps_remaining=laps_remaining,
            regen_kw=regen_kw,
            motor_power_kw=motor_power_kw,
            motor_torque_nm=torque_nm,
            motor_rpm=motor_rpm,
            motor_temp_c=self._float(
                player,
                "electric_motor_temp_c",
            ),
            motor_water_temp_c=self._float(
                player,
                "electric_motor_water_temp_c",
            ),
            motor_state=motor_state,
            motor_state_text=self.MOTOR_STATES.get(
                motor_state,
                f"STATE {motor_state}",
            ),
            source_name=source_name,
            comparison_ready=(
                delta is not None
            ),
        )

    def preview(self) -> BatteryViewData:
        return BatteryViewData(
            available=True,
            charge_pct=67.0,
            virtual_energy_pct=54.0,
            current_lap=8,
            lap_progress_pct=58.0,
            current=BatteryLapMetrics(
                drain_pct=4.8,
                regen_pct=1.4,
                net_use_pct=3.4,
            ),
            last=BatteryLapMetrics(
                drain_pct=6.1,
                regen_pct=1.7,
                net_use_pct=4.4,
                completed=True,
            ),
            delta_vs_last_pct=-0.7,
            projected_lap_use_pct=5.8,
            laps_remaining=11.5,
            regen_kw=42.0,
            motor_power_kw=168.0,
            motor_torque_nm=282.0,
            motor_rpm=5680.0,
            motor_temp_c=71.0,
            motor_water_temp_c=58.0,
            motor_state=2,
            motor_state_text="BOOST",
            source_name="BATTERY",
            comparison_ready=True,
        )

    def _accumulate_charge_change(
        self,
        charge_pct: float,
        in_pits: bool,
    ) -> None:
        if self._last_charge_pct is None:
            self._last_charge_pct = charge_pct
            return

        change = (
            charge_pct
            - self._last_charge_pct
        )
        self._last_charge_pct = charge_pct

        if (
            bool(
                self.config.get(
                    "ignore_pit_charge_changes",
                    True,
                )
            )
            and in_pits
        ):
            return

        max_step = max(
            0.1,
            float(
                self.config.get(
                    "maximum_valid_step_pct",
                    5.0,
                )
            ),
        )

        if abs(change) > max_step:
            return

        if change < 0.0:
            self._current_drain_pct += (
                -change
            )
        elif change > 0.0:
            self._current_regen_pct += (
                change
            )

    def _finish_lap(
        self,
        in_pits: bool,
    ) -> None:
        net = (
            self._current_drain_pct
            - self._current_regen_pct
        )
        minimum_samples = max(
            2,
            int(
                self.config.get(
                    "minimum_lap_samples",
                    8,
                )
            ),
        )
        valid = (
            len(
                self._current_samples
            )
            >= minimum_samples
            and not in_pits
        )

        if valid:
            self._last_samples = list(
                self._current_samples
            )
            self._last_metrics = (
                BatteryLapMetrics(
                    drain_pct=(
                        self._current_drain_pct
                    ),
                    regen_pct=(
                        self._current_regen_pct
                    ),
                    net_use_pct=net,
                    completed=True,
                )
            )

        self._current_drain_pct = 0.0
        self._current_regen_pct = 0.0
        self._current_samples = []
        self._last_sample_distance = -1.0

    def _charge_percent(
        self,
        player: Any,
        class_name: str,
    ) -> tuple[float, str]:
        source = str(
            self.config.get(
                "charge_source",
                "auto",
            )
        ).lower()
        battery_fraction = self._float(
            player,
            "battery_fraction",
        )
        state_of_charge = self._float(
            player,
            "state_of_charge",
        )
        virtual_energy = self._float(
            player,
            "virtual_energy",
        )

        values = {
            "battery_fraction": (
                self._fraction_percent(
                    battery_fraction
                ),
                "BATTERY",
            ),
            "state_of_charge": (
                self._soc_percent(
                    state_of_charge
                ),
                "SOC",
            ),
            "virtual_energy": (
                self._fraction_percent(
                    virtual_energy
                ),
                "VIRTUAL",
            ),
        }

        if source in values:
            return values[source]

        if 0.0 < battery_fraction <= 1.0:
            return values[
                "battery_fraction"
            ]

        if 0.0 < state_of_charge <= 100.0:
            return values[
                "state_of_charge"
            ]

        if (
            0.0 < virtual_energy <= 1.0
            and bool(
                self.config.get(
                    "allow_virtual_energy_fallback",
                    False,
                )
            )
        ):
            return values[
                "virtual_energy"
            ]

        # Mantém 0% visível em carros híbridos mesmo com bateria vazia.
        if any(
            token in class_name.upper()
            for token in (
                "HYPER",
                "LMDH",
                "LMH",
            )
        ):
            return (
                self._fraction_percent(
                    battery_fraction
                ),
                "BATTERY",
            )

        return 0.0, "N/A"

    @staticmethod
    def _value_at_distance(
        samples: list[
            tuple[float, float]
        ],
        distance_m: float,
    ) -> float | None:
        if not samples:
            return None

        distances = [
            item[0]
            for item in samples
        ]
        index = bisect_left(
            distances,
            distance_m,
        )

        if index <= 0:
            return samples[0][1]

        if index >= len(samples):
            return samples[-1][1]

        x0, y0 = samples[index - 1]
        x1, y1 = samples[index]

        if x1 <= x0:
            return y1

        ratio = (
            distance_m - x0
        ) / (x1 - x0)
        return y0 + (
            y1 - y0
        ) * ratio

    @staticmethod
    def _fraction_percent(
        value: float,
    ) -> float:
        if 0.0 <= value <= 1.0:
            return value * 100.0

        return max(
            0.0,
            min(100.0, value),
        )

    @staticmethod
    def _soc_percent(
        value: float,
    ) -> float:
        return max(
            0.0,
            min(100.0, value),
        )

    @staticmethod
    def _player_row(
        session: Any,
    ) -> Any | None:
        for driver in list(
            getattr(
                session,
                "drivers",
                [],
            )
            or []
        ):
            if bool(
                getattr(
                    driver,
                    "is_player",
                    False,
                )
            ):
                return driver

        return None

    @staticmethod
    def _make_session_key(
        session: Any,
    ) -> str:
        return "|".join(
            [
                str(
                    getattr(
                        session,
                        "track_name",
                        "",
                    )
                    or ""
                ),
                str(
                    getattr(
                        session,
                        "session",
                        0,
                    )
                ),
                str(
                    getattr(
                        session,
                        "max_laps",
                        0,
                    )
                ),
            ]
        )

    @staticmethod
    def _float(
        source: Any,
        name: str,
    ) -> float:
        try:
            return float(
                getattr(
                    source,
                    name,
                    0.0,
                )
                or 0.0
            )
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _int(
        source: Any,
        name: str,
    ) -> int:
        try:
            return int(
                getattr(
                    source,
                    name,
                    0,
                )
                or 0
            )
        except (TypeError, ValueError):
            return 0
