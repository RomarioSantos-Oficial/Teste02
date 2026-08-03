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

import json
import math
import re
from pathlib import Path
from typing import Any

from .map_models import MapPoint, TrackMapData


class TrackMapBuilder:
    """
    Aprende o traçado usando a posição mundial do jogador e salva um
    cache por pista. Enquanto não há uma volta suficientemente completa,
    o widget pode usar o círculo temporário, igual ao comportamento do
    arquivo de referência.
    """

    def __init__(
        self,
        project_root: Path,
        config: dict[str, Any],
    ) -> None:
        self.project_root = Path(project_root)
        self.config = config
        self.cache_dir = self._resolve_cache_dir()
        self.reset()

    def update_config(
        self,
        config: dict[str, Any],
    ) -> None:
        self.config = config
        self.cache_dir = self._resolve_cache_dir()

    def reset(self) -> None:
        self.track_key = ""
        self.track_name = ""
        self.track_length_m = 0.0
        self.current_lap: int | None = None
        self.current_points: list[MapPoint] = []
        self.current_sector_points: list[MapPoint] = []
        self.last_sector: int | None = None
        self.last_distance_m: float | None = None
        self.loaded_data: TrackMapData | None = None

    def clear_cache(
        self,
        track_name: str | None = None,
        track_length_m: float | None = None,
    ) -> None:
        if track_name:
            key = self.make_track_key(
                track_name,
                float(track_length_m or 0.0),
            )
            path = self.cache_dir / f"{key}.json"
            path.unlink(missing_ok=True)
        elif self.track_key:
            path = self.cache_dir / f"{self.track_key}.json"
            path.unlink(missing_ok=True)

        self.loaded_data = None
        self.current_points = []
        self.current_sector_points = []
        self.current_lap = None
        self.last_sector = None
        self.last_distance_m = None

    def update(
        self,
        session: Any,
    ) -> TrackMapData:
        player_row = self._player_row(session)
        track_name = str(
            getattr(session, "track_name", "") or "Unknown Track"
        )
        track_length_m = max(
            0.0,
            self._float(session, "track_length_m"),
        )
        key = self.make_track_key(
            track_name,
            track_length_m,
        )

        if key != self.track_key:
            self.reset()
            self.track_key = key
            self.track_name = track_name
            self.track_length_m = track_length_m
            self.loaded_data = self._load_cache(key)

        if self.loaded_data is not None:
            return self.loaded_data

        if player_row is None:
            return self._current_data()

        if (
            bool(getattr(player_row, "in_pits", False))
            or bool(getattr(player_row, "in_garage", False))
            or int(getattr(player_row, "pit_state", 0) or 0) > 0
        ):
            return self._current_data()

        max_path_lateral = max(
            1.0,
            float(
                self.config.get(
                    "maximum_mapping_path_lateral_m",
                    35.0,
                )
            ),
        )
        if abs(
            self._float(player_row, "path_lateral_m")
        ) > max_path_lateral:
            return self._current_data()

        player = getattr(session, "player", None)
        lap = int(
            getattr(player, "lap", 0)
            or getattr(player_row, "laps", 0)
            or 0
        )
        distance_m = max(
            0.0,
            self._float(player_row, "lap_distance_m"),
        )
        world_x = self._float(player_row, "world_x")
        # A projeção 2D usada pelo projeto de referência é X e -Z.
        world_y = -self._float(player_row, "world_z")
        sector = int(
            getattr(player_row, "current_sector", 0)
            or 0
        )

        if not all(
            math.isfinite(value)
            for value in (distance_m, world_x, world_y)
        ):
            return self._current_data()

        wrapped = (
            self.last_distance_m is not None
            and track_length_m > 0
            and self.last_distance_m > track_length_m * 0.75
            and distance_m < track_length_m * 0.25
        )
        lap_changed = (
            self.current_lap is not None
            and lap != self.current_lap
        )

        if lap_changed or wrapped:
            saved = self._finalize_lap()

            if saved is not None:
                self.loaded_data = saved
                return saved

            self.current_points = []
            self.current_sector_points = []
            self.last_sector = None
            self.last_distance_m = None

        if self.current_lap is None or lap_changed:
            self.current_lap = lap

        point = MapPoint(
            distance_m=distance_m,
            world_x=world_x,
            world_y=world_y,
            sector=sector,
        )

        if self._should_record(point):
            self.current_points.append(point)
            self.last_distance_m = distance_m

            if (
                self.last_sector is not None
                and sector != self.last_sector
                and sector > 0
            ):
                self.current_sector_points.append(point)

            self.last_sector = sector

        return self._current_data()

    def preview(self) -> TrackMapData:
        points: list[MapPoint] = []

        for index in range(240):
            progress = index / 239.0
            angle = progress * math.tau
            # Forma semelhante a um circuito de endurance, não um círculo.
            radius_x = 490.0 + 95.0 * math.sin(angle * 3.0)
            radius_y = 285.0 + 65.0 * math.cos(angle * 2.0)
            x = math.cos(angle) * radius_x
            y = math.sin(angle) * radius_y
            points.append(
                MapPoint(
                    distance_m=progress * 13626.0,
                    world_x=x,
                    world_y=y,
                    sector=(
                        1
                        if progress < 0.33
                        else 2
                        if progress < 0.66
                        else 3
                    ),
                )
            )

        return TrackMapData(
            track_key="preview",
            track_name="LE MANS — PREVIEW",
            track_length_m=13626.0,
            points=points,
            sector_points=[
                points[79],
                points[158],
            ],
            complete=True,
            loaded_from_cache=False,
            coverage=1.0,
        )

    def _should_record(
        self,
        point: MapPoint,
    ) -> bool:
        if not self.current_points:
            return True

        previous = self.current_points[-1]
        min_distance = max(
            2.0,
            float(
                self.config.get(
                    "mapping_sample_distance_m",
                    18.0,
                )
            ),
        )
        spatial = math.hypot(
            point.world_x - previous.world_x,
            point.world_y - previous.world_y,
        )
        distance_delta = abs(
            point.distance_m - previous.distance_m
        )

        return (
            distance_delta >= min_distance
            or spatial >= min_distance
        )

    def _finalize_lap(
        self,
    ) -> TrackMapData | None:
        points = sorted(
            self.current_points,
            key=lambda item: item.distance_m,
        )
        minimum_points = max(
            30,
            int(
                self.config.get(
                    "minimum_mapping_points",
                    120,
                )
            ),
        )

        if len(points) < minimum_points:
            return None

        track_length = max(
            self.track_length_m,
            points[-1].distance_m,
            1.0,
        )
        minimum_distance = points[0].distance_m
        maximum_distance = points[-1].distance_m
        coverage = max(
            0.0,
            min(
                1.0,
                (maximum_distance - minimum_distance)
                / track_length,
            ),
        )
        required_coverage = max(
            0.50,
            min(
                0.98,
                float(
                    self.config.get(
                        "minimum_mapping_coverage",
                        0.82,
                    )
                ),
            ),
        )
        starts_near_line = (
            minimum_distance
            <= track_length * 0.10
        )
        ends_near_line = (
            maximum_distance
            >= track_length * 0.80
        )

        if (
            coverage < required_coverage
            or not starts_near_line
            or not ends_near_line
        ):
            return None

        data = TrackMapData(
            track_key=self.track_key,
            track_name=self.track_name,
            track_length_m=track_length,
            points=points,
            sector_points=list(
                self.current_sector_points
            ),
            complete=True,
            loaded_from_cache=False,
            coverage=coverage,
        )

        if bool(
            self.config.get(
                "save_map_cache",
                True,
            )
        ):
            self._save_cache(data)

        return data

    def _current_data(self) -> TrackMapData:
        points = sorted(
            self.current_points,
            key=lambda item: item.distance_m,
        )
        length = max(
            self.track_length_m,
            points[-1].distance_m if points else 0.0,
            1.0,
        )

        if points:
            coverage = max(
                0.0,
                min(
                    1.0,
                    (
                        points[-1].distance_m
                        - points[0].distance_m
                    )
                    / length,
                ),
            )
        else:
            coverage = 0.0

        return TrackMapData(
            track_key=self.track_key,
            track_name=self.track_name,
            track_length_m=self.track_length_m,
            points=points,
            sector_points=list(
                self.current_sector_points
            ),
            complete=False,
            loaded_from_cache=False,
            coverage=coverage,
        )

    def _save_cache(
        self,
        data: TrackMapData,
    ) -> None:
        self.cache_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        path = self.cache_dir / f"{data.track_key}.json"
        payload = {
            "version": 1,
            "track_key": data.track_key,
            "track_name": data.track_name,
            "track_length_m": data.track_length_m,
            "points": [
                {
                    "distance_m": point.distance_m,
                    "world_x": point.world_x,
                    "world_y": point.world_y,
                    "sector": point.sector,
                }
                for point in data.points
            ],
            "sector_points": [
                {
                    "distance_m": point.distance_m,
                    "world_x": point.world_x,
                    "world_y": point.world_y,
                    "sector": point.sector,
                }
                for point in data.sector_points
            ],
        }
        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _load_cache(
        self,
        key: str,
    ) -> TrackMapData | None:
        if not bool(
            self.config.get(
                "load_map_cache",
                True,
            )
        ):
            return None

        path = self.cache_dir / f"{key}.json"

        if not path.exists():
            return None

        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
            points = [
                MapPoint(
                    distance_m=float(item["distance_m"]),
                    world_x=float(item["world_x"]),
                    world_y=float(item["world_y"]),
                    sector=int(item.get("sector", 0)),
                )
                for item in payload.get("points", [])
            ]
            sectors = [
                MapPoint(
                    distance_m=float(item["distance_m"]),
                    world_x=float(item["world_x"]),
                    world_y=float(item["world_y"]),
                    sector=int(item.get("sector", 0)),
                )
                for item in payload.get("sector_points", [])
            ]
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
        ):
            return None

        minimum_points = max(
            20,
            int(
                self.config.get(
                    "minimum_mapping_points",
                    120,
                )
            )
            // 2,
        )
        if len(points) < minimum_points:
            return None

        return TrackMapData(
            track_key=key,
            track_name=str(
                payload.get(
                    "track_name",
                    self.track_name,
                )
            ),
            track_length_m=float(
                payload.get(
                    "track_length_m",
                    self.track_length_m,
                )
                or self.track_length_m
            ),
            points=points,
            sector_points=sectors,
            complete=True,
            loaded_from_cache=True,
            coverage=1.0,
        )

    def _resolve_cache_dir(self) -> Path:
        configured = Path(
            str(
                self.config.get(
                    "cache_directory",
                    "data/track_maps",
                )
            )
        )
        return (
            configured
            if configured.is_absolute()
            else self.project_root / configured
        )

    @staticmethod
    def make_track_key(
        track_name: str,
        track_length_m: float,
    ) -> str:
        normalized = re.sub(
            r"[^a-z0-9]+",
            "_",
            track_name.lower(),
        ).strip("_")
        length = int(
            round(
                max(0.0, track_length_m)
            )
        )
        return (
            f"{normalized}_{length}"
            if length > 0
            else normalized or "unknown_track"
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
    def _float(
        source: Any,
        name: str,
    ) -> float:
        try:
            return float(
                getattr(source, name, 0.0)
                or 0.0
            )
        except (TypeError, ValueError):
            return 0.0
