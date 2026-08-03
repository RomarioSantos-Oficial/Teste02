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

import time
from collections import deque
from typing import Any

from .weather_models import WeatherForecast, WeatherSample


class WeatherTrendPredictor:
    """
    Cria uma tendência de curto prazo usando somente amostras reais
    recebidas do LMU.

    O LMU fornece o clima atual, mas não publica a agenda climática
    futura na memória compartilhada. Por isso os blocos +5m...+25m são
    identificados como tendência estimada, nunca como dado futuro real.
    """

    def __init__(
        self,
        max_samples: int = 180,
        sample_interval_seconds: float = 2.0,
    ) -> None:
        self.samples: deque[WeatherSample] = deque(
            maxlen=max(10, int(max_samples))
        )
        self.sample_interval_seconds = max(
            0.25,
            float(sample_interval_seconds),
        )
        self._last_sample_at = 0.0
        self._session_key = ""

    def update_config(
        self,
        sample_interval_seconds: float,
    ) -> None:
        self.sample_interval_seconds = max(
            0.25,
            float(sample_interval_seconds),
        )

    def reset(self) -> None:
        self.samples.clear()
        self._last_sample_at = 0.0
        self._session_key = ""

    def add_session(
        self,
        session: Any,
        now_s: float | None = None,
    ) -> WeatherSample:
        now = (
            time.monotonic()
            if now_s is None
            else float(now_s)
        )
        session_key = self._make_session_key(session)

        if session_key != self._session_key:
            self.reset()
            self._session_key = session_key

        sample = WeatherSample(
            timestamp_s=now,
            track_temp_c=self._float(
                session,
                "track_temp_c",
            ),
            air_temp_c=self._float(
                session,
                "ambient_temp_c",
            ),
            rain=self._clamp01(
                self._float(
                    session,
                    "raining",
                )
            ),
            wetness=self._clamp01(
                self._float(
                    session,
                    "avg_path_wetness",
                )
            ),
            dark_cloud=self._clamp01(
                self._float(
                    session,
                    "dark_cloud",
                )
            ),
            cloud_coverage=max(
                0,
                min(
                    10,
                    self._int(
                        session,
                        "cloud_coverage",
                    ),
                ),
            ),
            time_of_day_s=max(
                0.0,
                self._float(
                    session,
                    "time_of_day",
                ),
            ),
            wind_speed_kmh=max(
                0.0,
                self._float(
                    session,
                    "wind_speed_kmh",
                ),
            ),
        )

        if (
            not self.samples
            or now - self._last_sample_at
            >= self.sample_interval_seconds
        ):
            self.samples.append(sample)
            self._last_sample_at = now

        return sample

    def forecast(
        self,
        current: WeatherSample,
        count: int = 5,
        interval_minutes: int = 5,
    ) -> list[WeatherForecast]:
        count = max(1, min(8, int(count)))
        interval_minutes = max(
            1,
            min(30, int(interval_minutes)),
        )
        slopes = self._slopes()

        result: list[WeatherForecast] = []

        for index in range(count):
            minutes = (index + 1) * interval_minutes
            seconds = minutes * 60.0

            air_temp = self._project(
                current.air_temp_c,
                slopes["air_temp_c"],
                seconds,
                minimum=-20.0,
                maximum=70.0,
            )
            rain = self._project(
                current.rain,
                slopes["rain"],
                seconds,
                minimum=0.0,
                maximum=1.0,
            )
            wetness = self._project(
                current.wetness,
                slopes["wetness"],
                seconds,
                minimum=0.0,
                maximum=1.0,
            )
            dark_cloud = self._project(
                current.dark_cloud,
                slopes["dark_cloud"],
                seconds,
                minimum=0.0,
                maximum=1.0,
            )
            cloud_value = self._project(
                float(current.cloud_coverage),
                slopes["cloud_coverage"],
                seconds,
                minimum=0.0,
                maximum=10.0,
            )
            future_time = (
                current.time_of_day_s + seconds
            ) % 86400.0
            cloud_coverage = int(round(cloud_value))

            result.append(
                WeatherForecast(
                    minutes_ahead=minutes,
                    air_temp_c=air_temp,
                    rain=rain,
                    wetness=wetness,
                    dark_cloud=dark_cloud,
                    cloud_coverage=cloud_coverage,
                    time_of_day_s=future_time,
                    weather_state=self.weather_state(
                        rain=rain,
                        wetness=wetness,
                        dark_cloud=dark_cloud,
                        cloud_coverage=cloud_coverage,
                        time_of_day_s=future_time,
                    ),
                    estimated=True,
                )
            )

        return result

    def official_forecast(
        self,
        session: Any,
        current: WeatherSample,
        count: int = 5,
        interval_minutes: int = 5,
    ) -> list[WeatherForecast] | None:
        """Converte a agenda oficial da API REST do LMU em tempos futuros."""
        schedule = getattr(
            session,
            "weather_schedule",
            {},
        )
        session_code = self._int(
            session,
            "session",
        )
        if 1 <= session_code <= 4:
            session_name = "PRACTICE"
        elif 5 <= session_code <= 9:
            session_name = "QUALIFY"
        elif 10 <= session_code <= 13:
            session_name = "RACE"
        else:
            return None

        nodes = (
            schedule.get(session_name, {})
            if isinstance(schedule, dict)
            else {}
        )
        positions = (
            (0.0, "START"),
            (0.25, "NODE_25"),
            (0.50, "NODE_50"),
            (0.75, "NODE_75"),
            (1.0, "FINISH"),
        )
        if not all(
            isinstance(nodes.get(name), dict)
            for _, name in positions
        ):
            return None

        current_time = self._float(
            session,
            "current_time_s",
        )
        remaining_time = self._float(
            session,
            "remaining_time_s",
        )
        total_time = current_time + remaining_time
        if current_time < 0.0 or total_time <= 1.0:
            return None

        count = max(1, min(8, int(count)))
        interval_minutes = max(1, min(30, int(interval_minutes)))
        result: list[WeatherForecast] = []

        for index in range(count):
            minutes = (index + 1) * interval_minutes
            progress = max(
                0.0,
                min(
                    1.0,
                    (current_time + minutes * 60.0)
                    / total_time,
                ),
            )
            lower_pos, lower_name = positions[0]
            upper_pos, upper_name = positions[-1]
            for node_index in range(1, len(positions)):
                if progress <= positions[node_index][0]:
                    lower_pos, lower_name = positions[node_index - 1]
                    upper_pos, upper_name = positions[node_index]
                    break

            span = max(0.0001, upper_pos - lower_pos)
            ratio = max(0.0, min(1.0, (progress - lower_pos) / span))
            lower = nodes[lower_name]
            upper = nodes[upper_name]
            air_temp = self._schedule_value(
                lower,
                upper,
                "WNV_TEMPERATURE",
                ratio,
                current.air_temp_c,
            )
            rain = self._schedule_value(
                lower,
                upper,
                "WNV_RAIN_CHANCE",
                ratio,
                0.0,
            ) / 100.0
            sky = self._schedule_value(
                lower,
                upper,
                "WNV_SKY",
                ratio,
                float(current.cloud_coverage),
            )
            cloud_coverage = max(0, min(10, int(round(sky))))
            future_time = (
                current.time_of_day_s + minutes * 60.0
            ) % 86400.0
            result.append(
                WeatherForecast(
                    minutes_ahead=minutes,
                    air_temp_c=air_temp,
                    rain=max(0.0, min(1.0, rain)),
                    wetness=current.wetness,
                    dark_cloud=cloud_coverage / 10.0,
                    cloud_coverage=cloud_coverage,
                    time_of_day_s=future_time,
                    weather_state=self.weather_state(
                        # RainChance pertence ao proprio no futuro. Usar a
                        # chuva atual aqui fazia todos os icones repetirem o
                        # clima presente, mesmo quando o LMU previa chuva.
                        rain=max(0.0, min(1.0, rain)),
                        wetness=current.wetness,
                        dark_cloud=cloud_coverage / 10.0,
                        cloud_coverage=cloud_coverage,
                        time_of_day_s=future_time,
                    ),
                    estimated=False,
                )
            )

        return result

    @staticmethod
    def _schedule_value(
        lower: dict[str, Any],
        upper: dict[str, Any],
        field_name: str,
        ratio: float,
        default: float,
    ) -> float:
        def value(node: dict[str, Any]) -> float:
            field = node.get(field_name, {})
            try:
                return float(field.get("currentValue", default))
            except (AttributeError, TypeError, ValueError):
                return float(default)

        start = value(lower)
        end = value(upper)
        return start + (end - start) * ratio

    @classmethod
    def weather_state(
        cls,
        rain: float,
        wetness: float,
        dark_cloud: float,
        cloud_coverage: int,
        time_of_day_s: float,
    ) -> str:
        is_day = cls.is_day(time_of_day_s)

        # A agua acumulada descreve a pista, nao o ceu. Uma pista pode
        # continuar molhada depois que a chuva terminou; nesse caso o
        # aviso de pista molhada permanece, mas o icone nao deve indicar
        # chuva. No LMU, cobertura 5 a 10 representa de garoa a tempestade.
        if rain >= 0.01 or cloud_coverage >= 5:
            return "Chuva"

        if (
            dark_cloud >= 0.35
            or cloud_coverage >= 3
        ):
            return (
                "nublado"
                if is_day
                else "noite_nublada"
            )

        return "Sol" if is_day else "noite"

    @staticmethod
    def is_day(
        time_of_day_s: float,
    ) -> bool:
        hours = (
            max(0.0, float(time_of_day_s))
            / 3600.0
        ) % 24.0
        return 6.0 <= hours < 18.0

    def _slopes(self) -> dict[str, float]:
        zero = {
            "air_temp_c": 0.0,
            "rain": 0.0,
            "wetness": 0.0,
            "dark_cloud": 0.0,
            "cloud_coverage": 0.0,
        }

        if len(self.samples) < 2:
            return zero

        newest = self.samples[-1]
        oldest = self.samples[0]
        elapsed = (
            newest.timestamp_s
            - oldest.timestamp_s
        )

        # Não cria tendência com menos de 8 segundos de histórico.
        if elapsed < 8.0:
            return zero

        # Limites evitam extrapolações irreais em horizontes de 25 min.
        limits_per_minute = {
            "air_temp_c": 0.18,
            "rain": 0.035,
            "wetness": 0.045,
            "dark_cloud": 0.040,
            "cloud_coverage": 0.35,
        }

        result: dict[str, float] = {}

        for field_name in zero:
            first = float(
                getattr(oldest, field_name)
            )
            last = float(
                getattr(newest, field_name)
            )
            slope = (last - first) / elapsed
            limit_per_second = (
                limits_per_minute[field_name]
                / 60.0
            )
            result[field_name] = max(
                -limit_per_second,
                min(
                    limit_per_second,
                    slope,
                ),
            )

        return result

    @staticmethod
    def _project(
        current: float,
        slope_per_second: float,
        seconds: float,
        minimum: float,
        maximum: float,
    ) -> float:
        value = (
            float(current)
            + float(slope_per_second)
            * float(seconds)
        )
        return max(
            minimum,
            min(maximum, value),
        )

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
    def _clamp01(
        value: float,
    ) -> float:
        return max(
            0.0,
            min(1.0, float(value)),
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
