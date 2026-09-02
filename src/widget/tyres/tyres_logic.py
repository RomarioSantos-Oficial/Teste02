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
import time
from dataclasses import dataclass
from typing import Any, Callable

from .tyres_models import (
    TyreWheelViewData,
    TyresViewData,
)


WHEEL_NAMES = ("FL", "FR", "RL", "RR")
COMPOUND_NAMES = {
    0: "Soft",
    1: "Medium",
    2: "Hard",
    3: "Wet",
    4: "Intermediate",
}

_INNER_TEMPERATURE_SOURCES = {
    "inner_average",
    "inner_center",
    "lmu_weighted",
}


@dataclass(slots=True)
class _TemperatureHealth:
    reference_inner: tuple[float, float, float]
    reference_aux: tuple[float, float]
    unchanged_since: float
    stale: bool = False
    fallback_source: str = "lmu_weighted"


class TyresLogic:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.config = config
        self._clock = clock or time.monotonic
        self._gte_vehicle = False
        self._hyper_vehicle = False
        self._lmp3_vehicle = False
        self._vehicle_identity = ""
        self._temperature_health: dict[int, _TemperatureHealth] = {}

    def update_config(
        self,
        config: dict[str, Any],
    ) -> None:
        health_keys = (
            "temperature_source",
            "gte_temperature_mode",
            "gte_temperature_source",
            "hyper_temperature_mode",
            "hyper_temperature_source",
            "lmp3_temperature_mode",
            "lmp3_temperature_source",
            "temperature_stale_fallback_enabled",
            "temperature_stale_timeout_s",
            "temperature_stale_epsilon_c",
            "temperature_stale_aux_delta_c",
        )
        if any(config.get(key) != self.config.get(key) for key in health_keys):
            self._temperature_health.clear()
        self.config = config

    def build_view(
        self,
        player: Any,
    ) -> TyresViewData:
        identity = self._identity(player)
        if identity != self._vehicle_identity:
            self._vehicle_identity = identity
            self._temperature_health.clear()
        self._gte_vehicle = self._is_gte_vehicle(player)
        self._hyper_vehicle = self._is_hyper_vehicle(player)
        self._lmp3_vehicle = self._is_lmp3_vehicle(player)
        now = self._clock()
        vehicle_speed_kmh = self._float(player, "speed_kmh")
        wheels_raw = list(
            getattr(
                player,
                "wheels",
                [],
            )
            or []
        )
        wheels: list[
            TyreWheelViewData
        ] = []

        for index in range(4):
            raw = (
                wheels_raw[index]
                if index < len(wheels_raw)
                else None
            )
            wheels.append(
                self._wheel_view(
                    index,
                    raw,
                    now,
                    vehicle_speed_kmh,
                )
            )

        front_fallback = str(
            getattr(player, "front_tire_compound", "") or ""
        )
        rear_fallback = str(
            getattr(player, "rear_tire_compound", "") or ""
        )
        return TyresViewData(
            front_compound=self._axle_compound(wheels[:2], front_fallback),
            rear_compound=self._axle_compound(wheels[2:], rear_fallback),
            wheels=wheels,
        )

    @staticmethod
    def _axle_compound(
        wheels: list[TyreWheelViewData], fallback: str
    ) -> str:
        names = [wheel.compound_name for wheel in wheels if wheel.compound_name]
        if not names:
            return fallback
        return names[0] if len(set(names)) == 1 else "/".join(names)

    def preview(self) -> TyresViewData:
        preview_wheels = [
            self._preview_wheel(
                0,
                78.4,
                96.0,
                425,
                176.0,
            ),
            self._preview_wheel(
                1,
                81.1,
                95.0,
                448,
                177.5,
            ),
            self._preview_wheel(
                2,
                86.3,
                91.0,
                510,
                173.0,
            ),
            self._preview_wheel(
                3,
                88.2,
                90.0,
                528,
                174.0,
            ),
        ]

        return TyresViewData(
            front_compound="MEDIUM",
            rear_compound="MEDIUM",
            wheels=preview_wheels,
        )

    def main_temperature_c(
        self,
        wheel: TyreWheelViewData,
    ) -> float:
        source = self._temperature_source(wheel)
        gte_mode = self._gte_vehicle and bool(
            self.config.get("gte_temperature_mode", True)
        )

        # O valor usado pelo MFD/doX combina a carcaça com as três
        # amostras da camada interna. Em alguns GT3 elas ficam muito
        # próximas; nos protótipos a diferença pode ultrapassar 10 °C.
        inner_values = (
            wheel.inner_left_c,
            wheel.inner_center_c,
            wheel.inner_right_c,
        )
        weighted_values_valid = (
            1.0 < wheel.carcass_temp_c < 300.0
            and all(1.0 < value < 300.0 for value in inner_values)
        )
        lmu_weighted = (
            wheel.carcass_temp_c * 0.34
            + inner_values[0] * 0.22
            + inner_values[1] * 0.22
            + inner_values[2] * 0.22
            if weighted_values_valid
            else 0.0
        )

        candidates = {
            "lmu_weighted": (
                lmu_weighted,
                wheel.carcass_temp_c,
                wheel.inner_average_c,
                wheel.surface_average_c,
            ),
            "inner_average": (
                wheel.inner_average_c,
                wheel.carcass_temp_c,
                wheel.surface_average_c,
            ),
            "surface_average": (
                wheel.surface_average_c,
                wheel.inner_average_c,
                wheel.carcass_temp_c,
            ),
            "carcass": (
                wheel.carcass_temp_c,
                wheel.inner_average_c,
                wheel.surface_average_c,
            ),
            "surface_center": (
                wheel.surface_center_c,
                wheel.inner_center_c,
                wheel.carcass_temp_c,
            ),
            "inner_center": (
                wheel.inner_center_c,
                wheel.inner_average_c,
                wheel.carcass_temp_c,
            ),
        }

        values = candidates.get(
            source,
            candidates["lmu_weighted"],
        )

        for value in values:
            if 1.0 < value < 300.0:
                if gte_mode:
                    correction = max(
                        -40.0,
                        min(
                            40.0,
                            float(
                                self.config.get(
                                    "gte_temperature_offset_c", 0.0
                                )
                            ),
                        ),
                    )
                    return value + correction
                return value

        return 0.0

    def _temperature_source(self, wheel: TyreWheelViewData) -> str:
        source = str(
            self.config.get("temperature_source", "lmu_weighted")
        ).lower()
        if self._lmp3_vehicle and bool(
            self.config.get("lmp3_temperature_mode", True)
        ):
            # O LMP3 publica uma superfície bem mais fria que a temperatura
            # principal exibida pelo jogo. A média da camada interna acompanha
            # melhor o estado térmico do pneu sem aplicar um offset fixo.
            source = str(
                self.config.get("lmp3_temperature_source", "inner_average")
            ).lower()
        elif self._gte_vehicle and bool(
            self.config.get("gte_temperature_mode", True)
        ):
            source = str(
                self.config.get("gte_temperature_source", "carcass")
            ).lower()
        elif (
            self._hyper_vehicle
            and bool(self.config.get("hyper_temperature_mode", True))
            and source in _INNER_TEMPERATURE_SOURCES
        ):
            # A camada interna pode deixar de ser atualizada em alguns
            # Hypercars. A leitura ponderada continua acompanhando a carcaça
            # e corresponde melhor ao valor térmico principal do LMU.
            source = str(
                self.config.get("hyper_temperature_source", "lmu_weighted")
            ).lower()

        health = self._temperature_health.get(wheel.index)
        if (
            health is not None
            and health.stale
            and source in _INNER_TEMPERATURE_SOURCES
            and bool(
                self.config.get("temperature_stale_fallback_enabled", True)
            )
        ):
            source = health.fallback_source
        return source

    def temperature_source_stale(self, wheel_index: int) -> bool:
        """Informa se a fonte interna deixou de acompanhar as demais."""
        health = self._temperature_health.get(int(wheel_index))
        return bool(health is not None and health.stale)

    @staticmethod
    def _identity(player: Any) -> str:
        return "|".join(
            str(getattr(player, name, "") or "").casefold()
            for name in ("vehicle_name", "vehicle_model", "vehicle_class")
        )

    def _is_gte_vehicle(self, player: Any) -> bool:
        """Detecta somente carros GT configurados para a leitura especial."""
        identity = " ".join(
            (
                str(getattr(player, "vehicle_name", "") or ""),
                str(getattr(player, "vehicle_model", "") or ""),
                str(getattr(player, "vehicle_class", "") or ""),
            )
        ).casefold()
        raw_keywords = str(
            self.config.get(
                "gte_detection_keywords",
                "gte,lmgt3,gt3",
            )
        )
        keywords = (
            word.strip().casefold()
            for word in raw_keywords.split(",")
        )
        return any(word and word in identity for word in keywords)

    def _is_lmp3_vehicle(self, player: Any) -> bool:
        """Detecta LMP3 pela classe oficial e usa texto apenas como fallback."""
        class_name = "".join(
            character
            for character in str(
                getattr(player, "vehicle_class", "") or ""
            ).casefold()
            if character.isalnum()
        )
        if class_name == "lmp3":
            return True

        identity = " ".join(
            (
                str(getattr(player, "vehicle_name", "") or ""),
                str(getattr(player, "vehicle_model", "") or ""),
            )
        ).casefold()
        raw_keywords = str(
            self.config.get("lmp3_detection_keywords", "lmp3")
        )
        keywords = (
            word.strip().casefold()
            for word in raw_keywords.split(",")
        )
        return any(word and word in identity for word in keywords)

    def _is_hyper_vehicle(self, player: Any) -> bool:
        identity = " ".join(
            (
                str(getattr(player, "vehicle_name", "") or ""),
                str(getattr(player, "vehicle_model", "") or ""),
                str(getattr(player, "vehicle_class", "") or ""),
            )
        ).casefold()
        raw_keywords = str(
            self.config.get(
                "hyper_detection_keywords",
                "hyper,hypercar,lmh,lmdh",
            )
        )
        keywords = (
            word.strip().casefold()
            for word in raw_keywords.split(",")
        )
        return any(word and word in identity for word in keywords)

    def temperature_color(
        self,
        wheel: TyreWheelViewData,
        temp_c: float,
    ) -> str:
        colors = self.config.get(
            "colors",
            {},
        )
        mode = str(
            self.config.get(
                "temperature_color_mode",
                "optimal",
            )
        ).lower()
        optimal = wheel.optimal_temp_c

        if (
            mode == "optimal"
            and 20.0 <= optimal <= 180.0
        ):
            cold_delta, hot_delta, critical_delta = self._thermal_deltas(
                wheel
            )

            if temp_c < optimal - cold_delta:
                return colors.get(
                    "tyre_cold",
                    "#1565C0",
                )
            if temp_c <= optimal + hot_delta:
                return colors.get(
                    "tyre_optimal",
                    "#2E7D32",
                )
            if temp_c <= optimal + critical_delta:
                return colors.get(
                    "tyre_warm",
                    "#F9A825",
                )
            return colors.get(
                "tyre_hot",
                "#C62828",
            )

        cold_limit = float(
            self.config.get(
                "tyre_cold_limit_c",
                70.0,
            )
        )
        optimal_limit = float(
            self.config.get(
                "tyre_optimal_limit_c",
                90.0,
            )
        )
        warm_limit = float(
            self.config.get(
                "tyre_warm_limit_c",
                100.0,
            )
        )

        if temp_c < cold_limit:
            return colors.get(
                "tyre_cold",
                "#1565C0",
            )
        if temp_c < optimal_limit:
            return colors.get(
                "tyre_optimal",
                "#2E7D32",
            )
        if temp_c < warm_limit:
            return colors.get(
                "tyre_warm",
                "#F9A825",
            )
        return colors.get(
            "tyre_hot",
            "#C62828",
        )

    def _thermal_deltas(
        self, wheel: TyreWheelViewData
    ) -> tuple[float, float, float]:
        """Janela relativa ao ótimo publicado pelo LMU para cada roda."""
        name = wheel.compound_name.casefold()
        if "wet" in name or "rain" in name or wheel.compound_type == 3:
            return (
                float(self.config.get("wet_cold_delta_c", 8.0)),
                float(self.config.get("wet_hot_delta_c", 5.0)),
                float(self.config.get("wet_critical_delta_c", 12.0)),
            )
        if "inter" in name or wheel.compound_type == 4:
            return (
                float(self.config.get("inter_cold_delta_c", 10.0)),
                float(self.config.get("inter_hot_delta_c", 7.0)),
                float(self.config.get("inter_critical_delta_c", 16.0)),
            )
        return (
            float(self.config.get("optimal_cold_delta_c", 15.0)),
            float(self.config.get("optimal_hot_delta_c", 10.0)),
            float(self.config.get("optimal_critical_delta_c", 22.0)),
        )

    def brake_color(
        self,
        temp_c: float,
    ) -> str:
        colors = self.config.get(
            "colors",
            {},
        )
        cool = float(
            self.config.get(
                "brake_cool_limit_c",
                200.0,
            )
        )
        optimal = float(
            self.config.get(
                "brake_optimal_limit_c",
                500.0,
            )
        )
        hot = float(
            self.config.get(
                "brake_hot_limit_c",
                700.0,
            )
        )

        if temp_c < cool:
            return colors.get(
                "brake_cold",
                "#37474F",
            )
        if temp_c < optimal:
            return colors.get(
                "brake_optimal",
                "#558B2F",
            )
        if temp_c < hot:
            return colors.get(
                "brake_hot",
                "#EF6C00",
            )
        return colors.get(
            "brake_critical",
            "#D84315",
        )

    def wear_color(
        self,
        wheel: TyreWheelViewData,
    ) -> str:
        remaining = (
            wheel.wear_remaining_pct
            if str(
                self.config.get(
                    "wear_display",
                    "remaining",
                )
            )
            == "remaining"
            else 100.0
            - wheel.wear_used_pct
        )
        colors = self.config.get(
            "colors",
            {},
        )

        if remaining > 98:
            return colors.get(
                "wear_new",
                "#FFFFFF",
            )
        if remaining > 70:
            return colors.get(
                "wear_good",
                "#CCCCCC",
            )
        if remaining > 40:
            return colors.get(
                "wear_warning",
                "#FFEE58",
            )
        return colors.get(
            "wear_critical",
            "#FF5252",
        )

    def wear_text(
        self,
        wheel: TyreWheelViewData,
    ) -> str:
        mode = str(
            self.config.get(
                "wear_display",
                "remaining",
            )
        ).lower()

        value = (
            wheel.wear_used_pct
            if mode == "used"
            else wheel.wear_remaining_pct
        )
        prefix = (
            "W "
            if bool(
                self.config.get(
                    "show_value_prefixes",
                    False,
                )
            )
            else ""
        )
        return f"{prefix}{value:.0f}%"

    def pressure_text(
        self,
        pressure_kpa: float,
    ) -> str:
        unit = str(
            self.config.get(
                "pressure_unit",
                "kpa",
            )
        ).lower()

        if unit == "psi":
            return (
                f"{pressure_kpa * 0.1450377377:.1f}"
                " psi"
            )

        if unit == "bar":
            return (
                f"{pressure_kpa / 100.0:.2f}"
                " bar"
            )

        return f"{pressure_kpa:.0f} kPa"

    def temperature_text(
        self,
        temp_c: float,
        decimals: int = 1,
    ) -> str:
        unit = str(
            self.config.get(
                "temperature_unit",
                "C",
            )
        ).upper()

        value = (
            temp_c * 9.0 / 5.0 + 32.0
            if unit == "F"
            else temp_c
        )
        suffix = "°F" if unit == "F" else "°"
        return f"{value:.{decimals}f}{suffix}"

    @staticmethod
    def status_text(
        wheel: TyreWheelViewData,
    ) -> str:
        if wheel.detached:
            return "DETACHED"
        if wheel.flat:
            return "FLAT"
        return ""

    def advanced_text(
        self,
        wheel: TyreWheelViewData,
    ) -> str:
        parts: list[str] = []

        if bool(
            self.config.get(
                "show_tire_load",
                False,
            )
        ):
            parts.append(
                f"LOAD "
                f"{wheel.tire_load_n / 1000.0:.1f}kN"
            )

        if bool(
            self.config.get(
                "show_grip_fraction",
                False,
            )
        ):
            parts.append(
                f"SLIP "
                f"{wheel.grip_fraction * 100:.0f}%"
            )

        if bool(
            self.config.get(
                "show_camber",
                False,
            )
        ):
            parts.append(
                f"CAM "
                f"{math.degrees(wheel.camber_rad):.1f}°"
            )

        if bool(
            self.config.get(
                "show_toe",
                False,
            )
        ):
            parts.append(
                f"TOE "
                f"{math.degrees(wheel.toe_rad):.2f}°"
            )

        if bool(
            self.config.get(
                "show_deflection",
                False,
            )
        ):
            parts.append(
                f"DEF "
                f"{wheel.vertical_tire_deflection_m * 1000.0:.1f}mm"
            )

        return " | ".join(parts)

    def _wheel_view(
        self,
        index: int,
        raw: Any,
        now: float,
        vehicle_speed_kmh: float,
    ) -> TyreWheelViewData:
        if raw is None:
            return TyreWheelViewData(
                index=index,
                position=WHEEL_NAMES[index],
            )

        wear_raw = max(
            0.0,
            min(
                1.0,
                self._float(
                    raw,
                    "wear",
                ),
            ),
        )
        wheel = TyreWheelViewData(
            index=index,
            position=WHEEL_NAMES[index],
            surface_left_c=self._float(
                raw,
                "surface_left_c",
            ),
            surface_center_c=self._float(
                raw,
                "surface_center_c",
            ),
            surface_right_c=self._float(
                raw,
                "surface_right_c",
            ),
            inner_left_c=self._float(
                raw,
                "inner_left_c",
            ),
            inner_center_c=self._float(
                raw,
                "inner_center_c",
            ),
            inner_right_c=self._float(
                raw,
                "inner_right_c",
            ),
            carcass_temp_c=self._float(
                raw,
                "carcass_temp_c",
            ),
            optimal_temp_c=self._float(
                raw,
                "optimal_temp_c",
            ),
            pressure_kpa=self._float(
                raw,
                "pressure_kpa",
            ),
            # O LMU fornece a fracao de vida restante: 1.0 para pneu
            # novo e o valor diminui conforme o pneu se desgasta.
            wear_used_pct=(
                1.0 - wear_raw
            )
            * 100.0,
            wear_remaining_pct=(
                wear_raw * 100.0
            ),
            brake_temp_c=self._float(
                raw,
                "brake_temp_c",
            ),
            brake_pressure=self._float(
                raw,
                "brake_pressure",
            ),
            tire_load_n=self._float(
                raw,
                "tire_load_n",
            ),
            grip_fraction=self._float(
                raw,
                "grip_fraction",
            ),
            camber_rad=self._float(
                raw,
                "camber_rad",
            ),
            toe_rad=self._float(
                raw,
                "toe_rad",
            ),
            suspension_deflection_m=self._float(
                raw,
                "suspension_deflection_m",
            ),
            vertical_tire_deflection_m=self._float(
                raw,
                "vertical_tire_deflection_m",
            ),
            ride_height_m=self._float(
                raw,
                "ride_height_m",
            ),
            rotation_rad_s=self._float(
                raw,
                "rotation_rad_s",
            ),
            surface_type=self._int(
                raw,
                "surface_type",
            ),
            terrain_name=str(
                getattr(
                    raw,
                    "terrain_name",
                    "",
                )
                or ""
            ),
            compound_type=self._int(
                raw,
                "compound_type",
            ),
            compound_index=self._int(
                raw,
                "compound_index",
            ),
            compound_name=COMPOUND_NAMES.get(
                self._int(raw, "compound_type"),
                f"C{self._int(raw, 'compound_index')}",
            ),
            flat=bool(
                getattr(
                    raw,
                    "flat",
                    False,
                )
            ),
            detached=bool(
                getattr(
                    raw,
                    "detached",
                    False,
                )
            ),
        )
        self._update_temperature_health(
            wheel,
            now,
            vehicle_speed_kmh,
        )
        wheel.main_temp_c = (
            self.main_temperature_c(
                wheel
            )
        )
        return wheel

    def _update_temperature_health(
        self,
        wheel: TyreWheelViewData,
        now: float,
        vehicle_speed_kmh: float,
    ) -> None:
        inner = (
            wheel.inner_left_c,
            wheel.inner_center_c,
            wheel.inner_right_c,
        )
        carcass = wheel.carcass_temp_c
        surface = wheel.surface_average_c
        if not (
            all(1.0 < value < 300.0 for value in inner)
            and (1.0 < carcass < 300.0 or 1.0 < surface < 300.0)
        ):
            self._temperature_health.pop(wheel.index, None)
            return

        aux = (carcass, surface)
        state = self._temperature_health.get(wheel.index)
        if state is None:
            self._temperature_health[wheel.index] = _TemperatureHealth(
                reference_inner=inner,
                reference_aux=aux,
                unchanged_since=now,
            )
            return

        inner_epsilon = max(
            0.001,
            float(self.config.get("temperature_stale_epsilon_c", 0.02)),
        )
        inner_changed = max(
            abs(value - reference)
            for value, reference in zip(inner, state.reference_inner)
        ) >= inner_epsilon
        if inner_changed:
            state.reference_inner = inner
            state.reference_aux = aux
            state.unchanged_since = now
            state.stale = False
            state.fallback_source = "lmu_weighted"
            return

        minimum_speed = max(
            0.0,
            float(self.config.get("temperature_stale_min_speed_kmh", 20.0)),
        )
        moving = (
            vehicle_speed_kmh >= minimum_speed
            or abs(wheel.rotation_rad_s) >= 5.0
        )
        if not moving:
            if not state.stale:
                state.reference_aux = aux
                state.unchanged_since = now
            return

        timeout = max(
            1.0,
            float(self.config.get("temperature_stale_timeout_s", 3.0)),
        )
        aux_delta = max(
            0.05,
            float(self.config.get("temperature_stale_aux_delta_c", 0.35)),
        )
        carcass_changed = (
            1.0 < carcass < 300.0
            and abs(carcass - state.reference_aux[0]) >= aux_delta
        )
        surface_changed = (
            1.0 < surface < 300.0
            and abs(surface - state.reference_aux[1]) >= aux_delta
        )
        if (
            now - state.unchanged_since >= timeout
            and (carcass_changed or surface_changed)
        ):
            state.stale = True
            # Prefira a ponderada quando a carcaça continua viva; ela evita
            # um salto grande ao sair da média interna. Se só a superfície
            # variar, use-a diretamente para não conservar outro valor parado.
            state.fallback_source = (
                "lmu_weighted" if carcass_changed else "surface_average"
            )

    def _preview_wheel(
        self,
        index: int,
        temp_c: float,
        remaining_pct: float,
        brake_temp_c: float,
        pressure_kpa: float,
    ) -> TyreWheelViewData:
        return TyreWheelViewData(
            index=index,
            position=WHEEL_NAMES[index],
            main_temp_c=temp_c,
            surface_left_c=temp_c - 2.0,
            surface_center_c=temp_c,
            surface_right_c=temp_c + 1.0,
            inner_left_c=temp_c - 1.0,
            inner_center_c=temp_c,
            inner_right_c=temp_c + 1.0,
            carcass_temp_c=temp_c - 4.0,
            optimal_temp_c=82.0,
            pressure_kpa=pressure_kpa,
            wear_used_pct=100.0 - remaining_pct,
            wear_remaining_pct=remaining_pct,
            brake_temp_c=brake_temp_c,
            brake_pressure=0.42,
            tire_load_n=3100 + index * 180,
            grip_fraction=0.08 + index * 0.02,
            camber_rad=math.radians(
                -3.1 + index * 0.2
            ),
            toe_rad=math.radians(
                0.05 + index * 0.01
            ),
            suspension_deflection_m=0.028,
            vertical_tire_deflection_m=0.012,
            ride_height_m=0.065,
            rotation_rad_s=-81.0,
            surface_type=0,
            terrain_name="DRY",
            compound_type=1,
            compound_index=1,
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
