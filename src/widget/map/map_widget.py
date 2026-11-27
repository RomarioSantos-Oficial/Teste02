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

import hashlib
import math
import time
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from PySide6.QtCore import (
    QLineF,
    QPoint,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QSizePolicy,
    QWidget,
)

from .map_builder import TrackMapBuilder
from .map_models import MapPoint, TrackMapData


PROJECT_ROOT = Path(
    __file__
).resolve().parents[3]


@dataclass(slots=True)
class MapProjection:
    project: Callable[
        [float, float],
        QPointF,
    ]
    scale: float
    world_center_x: float
    world_center_y: float


def map_vehicle_marker_size(
    vehicle_size: float,
    scale: float,
    is_player: bool = False,
    player_scale: float = 1.10,
) -> float:
    size = max(7.0, float(vehicle_size) * float(scale))
    return size * max(1.0, float(player_scale)) if is_player else size


def map_leader_roles(
    driver: Any,
    config: dict[str, Any],
) -> tuple[str, ...]:
    if (
        bool(config.get("show_overall_leader_marker", True))
        and int(getattr(driver, "position", 0) or 0) == 1
    ):
        # O líder geral já é, necessariamente, o destaque máximo. Não
        # desenhe uma segunda coroa de categoria sobre a mesma bolinha.
        return ("overall",)
    if (
        bool(config.get("show_class_leader_markers", True))
        and int(getattr(driver, "position_in_class", 0) or 0) == 1
    ):
        return ("class",)
    return ()


class TrackMapWidget(QWidget):
    geometry_changed = Signal(
        str,
        float,
        float,
        float,
        float,
    )
    selected = Signal(str)

    BASE_SIZE = 480.0

    def __init__(
        self,
        widget_id: str,
        config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.widget_id = widget_id
        self.config = config
        self.builder = TrackMapBuilder(
            PROJECT_ROOT,
            config,
        )
        self.map_data = TrackMapData()
        self.session: Any | None = None
        self.edit_mode = False
        self._last_rebuild_request = int(
            config.get(
                "rebuild_request",
                0,
            )
            or 0
        )

        self._dragging = False
        self._resizing = False
        self._drag_offset = QPoint()
        self._resize_start_global = QPoint()
        self._resize_start_size = 0
        self._responsive_scale = 1.0
        self._map_geometry_cache_key: tuple[Any, ...] | None = None
        self._map_geometry_cache: tuple[
            MapProjection,
            QPainterPath,
            bool,
        ] | None = None
        self._raw_drivers: list[Any] = []
        self._render_drivers: list[Any] = []
        self._player_driver: Any | None = None
        self._motion_start_positions: dict[
            tuple[str, str],
            tuple[float, float, float],
        ] = {}
        self._motion_target_positions: dict[
            tuple[str, str],
            tuple[float, float, float],
        ] = {}
        self._motion_start_time = 0.0
        self._motion_duration = 0.0
        self._last_motion_snapshot_time: float | None = None
        self._preview_map_data: TrackMapData | None = None
        self._preview_driver_cache: list[Any] | None = None
        self._marker_pixmap_cache: dict[
            tuple[str, int],
            QPixmap | None,
        ] = {}
        self._class_color_cache: dict[str, QColor] = {}
        self._vehicle_font_cache: dict[tuple[str, int], QFont] = {}
        self._track_distance_cache_key: int | None = None
        self._track_distances_cache: list[float] = []
        self._motion_timer = QTimer(self)
        self._motion_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._motion_timer.setInterval(16)
        self._motion_timer.timeout.connect(self._animate_motion)

        self.setWindowTitle(
            "Sector Flow Drive - Track Map"
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.setMinimumSize(
            220,
            220,
        )
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.apply_config()

    def apply_config(self) -> None:
        self.builder.update_config(
            self.config
        )
        self._marker_pixmap_cache.clear()
        self._class_color_cache.clear()
        self._vehicle_font_cache.clear()
        self._refresh_render_drivers()
        request = int(
            self.config.get(
                "rebuild_request",
                0,
            )
            or 0
        )

        if request != self._last_rebuild_request:
            self._last_rebuild_request = request
            self.builder.clear_cache(
                self.map_data.track_name or None,
                self.map_data.track_length_m,
            )
            self.map_data = TrackMapData()
            self._clear_map_geometry_cache()

        self.setWindowOpacity(
            max(
                0.10,
                min(
                    1.0,
                    float(
                        self.config.get(
                            "opacity",
                            0.96,
                        )
                    ),
                ),
            )
        )
        self._update_scale()
        self.update()

    def update_config(
        self,
        config: dict[str, Any],
    ) -> None:
        self.config = config
        self.apply_config()

    def apply_normalized_geometry(
        self,
        screen_geometry,
    ) -> None:
        position = self.config.get(
            "position",
            {},
        )
        size = self.config.get(
            "size",
            {},
        )
        scale = max(
            0.35,
            float(
                self.config.get(
                    "scale",
                    1.0,
                )
            ),
        )
        width = max(
            self.minimumWidth(),
            int(
                screen_geometry.width()
                * float(
                    size.get(
                        "width",
                        0.25,
                    )
                )
                * scale
            ),
        )

        if bool(
            self.config.get(
                "lock_aspect_ratio",
                True,
            )
        ):
            height = width
        else:
            height = max(
                self.minimumHeight(),
                int(
                    screen_geometry.height()
                    * float(
                        size.get(
                            "height",
                            0.40,
                        )
                    )
                    * scale
                ),
            )

        x = int(
            screen_geometry.left()
            + screen_geometry.width()
            * float(
                position.get(
                    "x",
                    0.73,
                )
            )
        )
        y = int(
            screen_geometry.top()
            + screen_geometry.height()
            * float(
                position.get(
                    "y",
                    0.32,
                )
            )
        )
        self.resize(width, height)
        self.move(x, y)
        self._update_scale()

    def update_from_session(
        self,
        session: Any,
    ) -> None:
        self.session = session
        self.map_data = self.builder.update(
            session
        )
        self._refresh_render_drivers()
        self._capture_vehicle_positions(
            self._raw_drivers
        )
        self.update()

    def set_edit_mode(
        self,
        enabled: bool,
    ) -> None:
        self.edit_mode = bool(enabled)

        if self.edit_mode:
            self.show()

        self._refresh_render_drivers()
        self.setCursor(
            Qt.CursorShape.SizeAllCursor
            if self.edit_mode
            else Qt.CursorShape.ArrowCursor
        )
        self.update()

    @staticmethod
    def _driver_motion_key(
        driver: Any,
    ) -> tuple[str, str]:
        for name in (
            "slot_id",
            "vehicle_id",
            "driver_id",
            "driver_name",
            "car_number",
        ):
            value = getattr(driver, name, None)
            if value not in (None, ""):
                return name, str(value)
        return "object", str(id(driver))

    @staticmethod
    def _float_attribute(
        driver: Any,
        name: str,
    ) -> float:
        try:
            value = float(getattr(driver, name, 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return value if math.isfinite(value) else 0.0

    def _refresh_render_drivers(self) -> None:
        if self.edit_mode and self.session is None:
            drivers = self._preview_drivers()
        else:
            drivers = list(
                getattr(self.session, "drivers", []) or []
            )
        self._raw_drivers = drivers
        self._player_driver = next(
            (
                driver
                for driver in drivers
                if bool(getattr(driver, "is_player", False))
            ),
            None,
        )
        self._render_drivers = self._filter_drivers(
            drivers,
            self._player_driver,
        )
        self._render_drivers.sort(
            key=lambda driver: (
                bool(getattr(driver, "is_player", False)),
                int(getattr(driver, "position", 999) or 999) == 1,
            )
        )

    def _capture_vehicle_positions(
        self,
        drivers: list[Any],
        now: float | None = None,
    ) -> None:
        captured_at = time.monotonic() if now is None else float(now)
        targets = {
            self._driver_motion_key(driver): (
                self._float_attribute(driver, "world_x"),
                self._float_attribute(driver, "world_z"),
                self._float_attribute(driver, "lap_distance_m"),
            )
            for driver in drivers
        }
        previous_sample = self._last_motion_snapshot_time
        self._motion_start_positions = (
            self._positions_at(captured_at)
            if previous_sample is not None
            else dict(targets)
        )
        interval = (
            captured_at - previous_sample
            if previous_sample is not None
            else 0.0
        )
        smoothing_enabled = bool(
            self.config.get("smooth_vehicle_motion", True)
        )
        if not smoothing_enabled or interval <= 0.0 or interval > 0.30:
            self._motion_start_positions = dict(targets)
            self._motion_duration = 0.0
            self._motion_timer.stop()
        else:
            self._motion_duration = max(0.016, min(0.150, interval))
        self._motion_target_positions = targets
        self._motion_start_time = captured_at
        self._last_motion_snapshot_time = captured_at

        moving = any(
            key in self._motion_start_positions
            and any(
                abs(start - target) > 0.01
                for start, target in zip(
                    self._motion_start_positions[key],
                    target_values,
                )
            )
            for key, target_values in targets.items()
        )
        if smoothing_enabled and self._motion_duration > 0.0 and moving:
            self._motion_timer.start()
        else:
            self._motion_timer.stop()

    def _positions_at(
        self,
        now: float,
    ) -> dict[tuple[str, str], tuple[float, float, float]]:
        if not self._motion_target_positions:
            return {}
        if self._motion_duration <= 0.0:
            return dict(self._motion_target_positions)
        return {
            key: self._position_at(key, now)
            for key in self._motion_target_positions
        }

    def _position_at(
        self,
        key: tuple[str, str],
        now: float,
    ) -> tuple[float, float, float]:
        target = self._motion_target_positions[key]
        if self._motion_duration <= 0.0:
            return target

        start = self._motion_start_positions.get(key, target)
        progress = max(
            0.0,
            min(
                1.0,
                (now - self._motion_start_time) / self._motion_duration,
            ),
        )
        distance_delta = target[2] - start[2]
        track_length = max(
            0.0,
            self._float_attribute(self.session, "track_length_m"),
        )
        if track_length > 0.0:
            if distance_delta < -track_length * 0.5:
                distance_delta += track_length
            elif distance_delta > track_length * 0.5:
                distance_delta -= track_length
        distance = start[2] + distance_delta * progress
        if track_length > 0.0:
            distance %= track_length
        return (
            start[0] + (target[0] - start[0]) * progress,
            start[1] + (target[1] - start[1]) * progress,
            distance,
        )

    def _interpolated_driver_position(
        self,
        driver: Any,
    ) -> tuple[float, float, float]:
        key = self._driver_motion_key(driver)
        if key in self._motion_target_positions:
            return self._position_at(
                key,
                time.monotonic(),
            )
        return (
            self._float_attribute(driver, "world_x"),
            self._float_attribute(driver, "world_z"),
            self._float_attribute(driver, "lap_distance_m"),
        )

    def _animate_motion(self) -> None:
        if (
            not bool(self.config.get("smooth_vehicle_motion", True))
            or self._motion_duration <= 0.0
            or time.monotonic() >= self._motion_start_time + self._motion_duration
        ):
            self._motion_timer.stop()
        self.update()

    def reset_session_state(self) -> None:
        self.builder.reset()
        self.map_data = TrackMapData()
        self.session = None
        self._motion_timer.stop()
        self._motion_start_positions = {}
        self._motion_target_positions = {}
        self._motion_duration = 0.0
        self._last_motion_snapshot_time = None
        self._refresh_render_drivers()
        self._clear_map_geometry_cache()
        self.update()

    def _clear_map_geometry_cache(self) -> None:
        self._map_geometry_cache_key = None
        self._map_geometry_cache = None

    def resizeEvent(
        self,
        event: QResizeEvent,
    ) -> None:
        super().resizeEvent(event)
        self._update_scale()

    def _update_scale(self) -> None:
        internal = max(
            0.50,
            float(
                self.config.get(
                    "internal_scale",
                    1.0,
                )
            ),
        )
        minimum = max(
            0.30,
            float(
                self.config.get(
                    "responsive_min_scale",
                    0.48,
                )
            ),
        )
        maximum = max(
            minimum,
            float(
                self.config.get(
                    "responsive_max_scale",
                    2.20,
                )
            ),
        )
        self._responsive_scale = max(
            minimum,
            min(
                maximum,
                min(
                    self.width(),
                    self.height(),
                )
                / self.BASE_SIZE
                * internal,
            ),
        )
        self.update()

    def paintEvent(
        self,
        event: QPaintEvent,
    ) -> None:
        del event

        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True,
        )
        painter.setRenderHint(
            QPainter.RenderHint.TextAntialiasing,
            True,
        )

        colors = self.config.get(
            "colors",
            {},
        )
        s = self._responsive_scale
        outer = QRectF(self.rect()).adjusted(
            1,
            1,
            -1,
            -1,
        )
        radius = max(
            5.0,
            12.0 * s,
        )

        if bool(
            self.config.get(
                "show_background",
                True,
            )
        ):
            painter.setPen(
                QPen(
                    QColor(
                        colors.get(
                            "border",
                            "#344155",
                        )
                    ),
                    max(
                        1.0,
                        1.4 * s,
                    ),
                )
            )
            painter.setBrush(
                QBrush(
                    QColor(
                        colors.get(
                            "background",
                            "#0A0F17",
                        )
                    )
                )
            )
            painter.drawRoundedRect(
                outer,
                radius,
                radius,
            )

        margin = max(
            8.0,
            float(
                self.config.get(
                    "area_margin",
                    24.0,
                )
            )
            * s,
        )
        header_height = (
            max(
                24.0,
                42.0 * s,
            )
            if bool(
                self.config.get(
                    "show_header",
                    True,
                )
            )
            else 0.0
        )

        if header_height > 0.0:
            self._draw_header(
                painter,
                QRectF(
                    outer.left() + margin,
                    outer.top() + margin * 0.45,
                    outer.width() - margin * 2.0,
                    header_height,
                ),
            )

        map_rect = QRectF(
            outer.left() + margin,
            outer.top()
            + margin
            + header_height,
            outer.width() - margin * 2.0,
            outer.height()
            - margin * 2.0
            - header_height,
        )

        data = (
            self._preview_map()
            if self.edit_mode
            and len(self.map_data.points) < 3
            else self.map_data
        )

        if len(data.points) >= 3:
            projection = self._draw_real_map(
                painter,
                data,
                map_rect,
            )
            self._draw_vehicles_on_map(
                painter,
                projection,
                map_rect,
                data,
            )
        else:
            self._draw_circle_map(
                painter,
                map_rect,
            )

        if self.edit_mode:
            painter.setPen(
                QPen(
                    QColor(
                        colors.get(
                            "edit_border",
                            "#9B5CFF",
                        )
                    ),
                    max(
                        1.0,
                        2.0 * s,
                    ),
                    Qt.PenStyle.DashLine,
                )
            )
            painter.setBrush(
                Qt.BrushStyle.NoBrush
            )
            painter.drawRoundedRect(
                outer,
                radius,
                radius,
            )
            painter.setPen(
                Qt.PenStyle.NoPen
            )
            painter.setBrush(
                QColor("#FFFFFF")
            )
            painter.drawRect(
                self._resize_handle_rect()
            )

    def _draw_header(
        self,
        painter: QPainter,
        rect: QRectF,
    ) -> None:
        data = self.map_data
        colors = self.config.get(
            "colors",
            {},
        )
        s = self._responsive_scale
        title_font = QFont(
            str(
                self.config.get(
                    "font_name",
                    "Arial",
                )
            )
        )
        title_font.setBold(True)
        title_font.setPixelSize(
            max(
                8,
                round(
                    float(
                        self.config.get(
                            "font_size",
                            14,
                        )
                    )
                    * 0.90
                    * s
                ),
            )
        )
        painter.setFont(title_font)
        painter.setPen(
            QColor(
                colors.get(
                    "text",
                    "#FFFFFF",
                )
            )
        )
        title = (
            data.track_name
            or (
                "TRACK MAP PREVIEW"
                if self.edit_mode
                else "TRACK MAP"
            )
        )
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            title,
        )

        if data.complete:
            status = (
                "CACHE"
                if data.loaded_from_cache
                else "MAPA SALVO"
            )
            status_color = colors.get(
                "status_ready",
                "#3EDB91",
            )
        else:
            status = (
                f"GRAVANDO "
                f"{data.coverage * 100:.0f}%"
                if data.points
                else "CÍRCULO TEMPORÁRIO"
            )
            status_color = colors.get(
                "status_recording",
                "#F1B84B",
            )

        painter.setPen(
            QColor(status_color)
        )
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter,
            status,
        )

    def _draw_real_map(
        self,
        painter: QPainter,
        data: TrackMapData,
        rect: QRectF,
    ) -> MapProjection:
        detail = max(
            0,
            int(
                self.config.get(
                    "display_detail_level",
                    1,
                )
            ),
        )
        skip = max(
            1,
            5 - min(4, detail)
        )
        close_threshold = max(
            10.0,
            float(
                self.config.get(
                    "loop_close_distance_m",
                    500.0,
                )
            ),
        )
        cache_key = (
            id(data.points),
            len(data.points),
            round(rect.left(), 2),
            round(rect.top(), 2),
            round(rect.width(), 2),
            round(rect.height(), 2),
            detail,
            round(close_threshold, 2),
        )
        cached = (
            self._map_geometry_cache
            if data.complete and cache_key == self._map_geometry_cache_key
            else None
        )
        if cached is not None:
            projection, path, circular = cached
        else:
            projection = self._projection(
                data.points,
                rect,
            )
            path = QPainterPath()
            screen_points = [
                projection.project(
                    point.world_x,
                    point.world_y,
                )
                for point in data.points
            ]
            path.moveTo(screen_points[0])
            for index, point in enumerate(
                screen_points[1:],
                start=1,
            ):
                if (
                    index == len(screen_points) - 1
                    or index % skip == 0
                ):
                    path.lineTo(point)

            first = data.points[0]
            last = data.points[-1]
            circular = (
                data.complete
                or math.hypot(
                    last.world_x - first.world_x,
                    last.world_y - first.world_y,
                )
                <= close_threshold
            )
            if circular:
                path.closeSubpath()
            if data.complete:
                self._map_geometry_cache_key = cache_key
                self._map_geometry_cache = (
                    projection,
                    path,
                    circular,
                )

        colors = self.config.get(
            "colors",
            {},
        )
        s = self._responsive_scale

        if (
            bool(
                self.config.get(
                    "show_map_background",
                    True,
                )
            )
            and circular
        ):
            fill = QColor(
                colors.get(
                    "map_background",
                    "#121821",
                )
            )
            fill.setAlpha(
                max(
                    0,
                    min(
                        255,
                        int(
                            float(
                                self.config.get(
                                    "map_background_opacity",
                                    0.58,
                                )
                            )
                            * 255
                        ),
                    ),
                )
            )
            painter.setPen(
                Qt.PenStyle.NoPen
            )
            painter.setBrush(fill)
            painter.drawPath(path)

        outline_width = max(
            0.0,
            float(
                self.config.get(
                    "map_outline_width",
                    5.0,
                )
            )
            * s,
        )
        map_width = max(
            1.0,
            float(
                self.config.get(
                    "map_width",
                    3.0,
                )
            )
            * s,
        )

        if outline_width > 0:
            pen = QPen(
                QColor(
                    colors.get(
                        "map_outline",
                        "#05070B",
                    )
                ),
                map_width + outline_width,
            )
            pen.setJoinStyle(
                Qt.PenJoinStyle.RoundJoin
            )
            pen.setCapStyle(
                Qt.PenCapStyle.RoundCap
            )
            painter.setPen(pen)
            painter.setBrush(
                Qt.BrushStyle.NoBrush
            )
            painter.drawPath(path)

        pen = QPen(
            QColor(
                colors.get(
                    "map",
                    "#D6DEE9",
                )
            ),
            map_width,
        )
        pen.setJoinStyle(
            Qt.PenJoinStyle.RoundJoin
        )
        pen.setCapStyle(
            Qt.PenCapStyle.RoundCap
        )
        painter.setPen(pen)
        painter.setBrush(
            Qt.BrushStyle.NoBrush
        )
        painter.drawPath(path)

        if bool(
            self.config.get(
                "show_start_line",
                True,
            )
        ):
            self._draw_cross_line(
                painter,
                data.points,
                0,
                projection,
                colors.get(
                    "start_line",
                    "#FFFFFF",
                ),
                float(
                    self.config.get(
                        "start_line_width",
                        2.0,
                    )
                )
                * s,
                float(
                    self.config.get(
                        "start_line_length",
                        18.0,
                    )
                )
                * s,
            )

        if bool(
            self.config.get(
                "show_sector_lines",
                True,
            )
        ):
            for sector_point in data.sector_points:
                index = self._nearest_point_index(
                    data.points,
                    sector_point.distance_m,
                )
                self._draw_cross_line(
                    painter,
                    data.points,
                    index,
                    projection,
                    colors.get(
                        "sector_line",
                        "#FFC42E",
                    ),
                    float(
                        self.config.get(
                            "sector_line_width",
                            2.0,
                        )
                    )
                    * s,
                    float(
                        self.config.get(
                            "sector_line_length",
                            14.0,
                        )
                    )
                    * s,
                )

        return projection

    def _draw_cross_line(
        self,
        painter: QPainter,
        points: list[MapPoint],
        index: int,
        projection: MapProjection,
        color: str,
        width: float,
        length: float,
    ) -> None:
        if len(points) < 2:
            return

        index = max(
            0,
            min(
                len(points) - 1,
                index,
            ),
        )
        other = (
            index + 1
            if index < len(points) - 1
            else index - 1
        )
        p0 = projection.project(
            points[index].world_x,
            points[index].world_y,
        )
        p1 = projection.project(
            points[other].world_x,
            points[other].world_y,
        )
        dx = p1.x() - p0.x()
        dy = p1.y() - p0.y()
        norm = math.hypot(dx, dy)

        if norm <= 0.001:
            return

        px = -dy / norm
        py = dx / norm
        half = length / 2.0
        painter.setPen(
            QPen(
                QColor(color),
                max(1.0, width),
            )
        )
        painter.drawLine(
            QLineF(
                p0.x() - px * half,
                p0.y() - py * half,
                p0.x() + px * half,
                p0.y() + py * half,
            )
        )

    def _draw_vehicles_on_map(
        self,
        painter: QPainter,
        projection: MapProjection,
        map_rect: QRectF,
        data: TrackMapData | None = None,
    ) -> None:
        for driver in self._render_drivers:
            world_x, world_z, distance = (
                self._interpolated_driver_position(driver)
            )
            if data is not None and data.complete and bool(
                self.config.get("use_track_distance_positions", True)
            ):
                track_position = self._track_position_at_distance(
                    data.points,
                    distance,
                    data.track_length_m,
                )
                if track_position is not None:
                    world_x, track_y = track_position
                    world_z = -track_y
            point = projection.project(
                world_x,
                -world_z,
            )

            if not map_rect.adjusted(
                -20,
                -20,
                20,
                20,
            ).contains(point):
                continue

            self._draw_vehicle(
                painter,
                point,
                driver,
                self._player_driver,
            )

    def _track_position_at_distance(
        self,
        points: list[MapPoint],
        distance_m: float,
        track_length_m: float,
    ) -> tuple[float, float] | None:
        """Interpolate a marker on the recorded centerline.

        LMU world coordinates can move by a few centimetres between shared
        memory reads, especially in corners. Lap distance is monotonic and
        is a more stable key for a map marker when a complete map exists.
        """
        if len(points) < 2:
            return None
        try:
            distance = float(distance_m)
            track_length = float(track_length_m)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(distance) or not math.isfinite(track_length):
            return None

        cache_key = id(points)
        if cache_key != self._track_distance_cache_key:
            self._track_distance_cache_key = cache_key
            self._track_distances_cache = [
                point.distance_m for point in points
            ]
        distances = self._track_distances_cache
        if track_length > 0.0:
            distance %= track_length
        index = bisect_right(distances, distance)

        if index <= 0:
            first, second = points[0], points[1]
            sample_distance = distance
        elif index >= len(points):
            first, second = points[-1], points[0]
            sample_distance = distance
            if sample_distance < first.distance_m:
                sample_distance += track_length
            span = max(0.001, track_length + second.distance_m - first.distance_m)
            ratio = max(0.0, min(1.0, (sample_distance - first.distance_m) / span))
            return (
                first.world_x + (second.world_x - first.world_x) * ratio,
                first.world_y + (second.world_y - first.world_y) * ratio,
            )
        else:
            first, second = points[index - 1], points[index]
            sample_distance = distance

        span = max(0.001, second.distance_m - first.distance_m)
        ratio = max(0.0, min(1.0, (sample_distance - first.distance_m) / span))
        return (
            first.world_x + (second.world_x - first.world_x) * ratio,
            first.world_y + (second.world_y - first.world_y) * ratio,
        )

    def _draw_circle_map(
        self,
        painter: QPainter,
        rect: QRectF,
    ) -> None:
        colors = self.config.get(
            "colors",
            {},
        )
        s = self._responsive_scale
        circle = QRectF(
            rect.center().x()
            - min(
                rect.width(),
                rect.height(),
            )
            * 0.42,
            rect.center().y()
            - min(
                rect.width(),
                rect.height(),
            )
            * 0.42,
            min(
                rect.width(),
                rect.height(),
            )
            * 0.84,
            min(
                rect.width(),
                rect.height(),
            )
            * 0.84,
        )
        painter.setBrush(
            QBrush(
                QColor(
                    colors.get(
                        "map_background",
                        "#121821",
                    )
                )
            )
        )
        painter.setPen(
            QPen(
                QColor(
                    colors.get(
                        "map_outline",
                        "#05070B",
                    )
                ),
                max(
                    2.0,
                    (
                        float(
                            self.config.get(
                                "map_width",
                                3.0,
                            )
                        )
                        + float(
                            self.config.get(
                                "map_outline_width",
                                5.0,
                            )
                        )
                    )
                    * s,
                ),
            )
        )
        painter.drawEllipse(circle)
        painter.setBrush(
            Qt.BrushStyle.NoBrush
        )
        painter.setPen(
            QPen(
                QColor(
                    colors.get(
                        "map",
                        "#D6DEE9",
                    )
                ),
                max(
                    1.0,
                    float(
                        self.config.get(
                            "map_width",
                            3.0,
                        )
                    )
                    * s,
                ),
            )
        )
        painter.drawEllipse(circle)

        if bool(
            self.config.get(
                "show_start_line",
                True,
            )
        ):
            center_y = circle.center().y()
            painter.setPen(
                QPen(
                    QColor(
                        colors.get(
                            "start_line",
                            "#FFFFFF",
                        )
                    ),
                    max(
                        1.0,
                        float(
                            self.config.get(
                                "start_line_width",
                                2.0,
                            )
                        )
                        * s,
                    ),
                )
            )
            painter.drawLine(
                QLineF(
                    circle.left()
                    - 7.0 * s,
                    center_y,
                    circle.left()
                    + 7.0 * s,
                    center_y,
                )
            )

        if self.edit_mode and self.session is None:
            track_length = 13626.0
        else:
            track_length = max(
                1.0,
                float(
                    getattr(
                        self.session,
                        "track_length_m",
                        1.0,
                    )
                    or 1.0
                ),
            )

        for driver in self._render_drivers:
            _world_x, _world_z, lap_distance = (
                self._interpolated_driver_position(driver)
            )
            progress = (
                lap_distance / track_length
            ) % 1.0
            angle = (
                -math.pi
                + progress * math.tau
            )
            point = QPointF(
                circle.center().x()
                + math.cos(angle)
                * circle.width()
                * 0.5,
                circle.center().y()
                + math.sin(angle)
                * circle.height()
                * 0.5,
            )
            self._draw_vehicle(
                painter,
                point,
                driver,
                self._player_driver,
            )

    def _draw_vehicle(
        self,
        painter: QPainter,
        point: QPointF,
        driver: Any,
        player: Any | None,
    ) -> None:
        colors = self.config.get(
            "colors",
            {},
        )
        s = self._responsive_scale
        is_player = bool(
            getattr(
                driver,
                "is_player",
                False,
            )
        )
        size = map_vehicle_marker_size(
            float(self.config.get("vehicle_size", 18.0)),
            s,
            is_player,
            float(self.config.get("player_marker_scale", 1.10)),
        )
        fill = self._vehicle_color(
            driver,
            player,
        )
        outline_color = colors.get(
            "vehicle_outline",
            "#0A0A0A",
        )
        outline_width = max(
            0.0,
            float(
                self.config.get(
                    "vehicle_outline_width",
                    2.0,
                )
            )
            * s,
        )

        if is_player:
            outline_color = colors.get(
                "vehicle_outline_player",
                "#FFFFFF",
            )
            outline_width = max(
                outline_width,
                float(
                    self.config.get(
                        "vehicle_outline_player_width",
                        3.0,
                    )
                )
                * s,
            )
        elif player is not None and bool(
            self.config.get(
                "show_lap_difference_outline",
                True,
            )
        ):
            lap_difference = int(
                getattr(driver, "laps", 0)
                or 0
            ) - int(
                getattr(player, "laps", 0)
                or 0
            )

            if lap_difference > 0:
                outline_color = colors.get(
                    "vehicle_outline_laps_ahead",
                    "#8B4DFF",
                )
            elif lap_difference < 0:
                outline_color = colors.get(
                    "vehicle_outline_laps_behind",
                    "#757575",
                )

        # O marcador do jogador possui uma cor de identificação
        # independente da categoria e da imagem personalizada.
        if is_player:
            outline_color = colors.get(
                "vehicle_player_marker",
                "#FF54B8",
            )
            outline_width = max(
                outline_width,
                float(
                    self.config.get(
                        "vehicle_outline_player_width",
                        3.0,
                    )
                )
                * s,
            )
        else:
            # Os demais carros mantêm o contorno na cor da categoria.
            outline_color = fill

        rect = QRectF(
            point.x() - size / 2.0,
            point.y() - size / 2.0,
            size,
            size,
        )
        player_image = (
            self._cached_marker_pixmap(
                str(self.config.get("player_marker_image", "") or ""),
                size,
            )
            if is_player
            else None
        )
        painter.save()
        painter.setPen(
            QPen(QColor(outline_color), outline_width)
            if outline_width > 0
            else Qt.PenStyle.NoPen
        )
        if player_image is not None:
            clip = QPainterPath()
            clip.addEllipse(rect)
            painter.setClipPath(clip)
            painter.drawPixmap(
                rect,
                player_image,
                QRectF(player_image.rect()),
            )
            painter.setClipping(False)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)
        else:
            painter.setBrush(QBrush(fill))
            painter.drawEllipse(rect)

        # Desenha o anel depois da imagem/preenchimento para que o destaque
        # do jogador nunca seja encoberto por um marcador personalizado.
        if is_player:
            ring_rect = rect.adjusted(
                -outline_width / 2.0,
                -outline_width / 2.0,
                outline_width / 2.0,
                outline_width / 2.0,
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(
                QPen(
                    QColor(
                        colors.get(
                            "vehicle_player_marker",
                            "#FF54B8",
                        )
                    ),
                    max(1.0, outline_width),
                )
            )
            painter.drawEllipse(ring_rect)

        painter.restore()

        if bool(
            self.config.get(
                "show_vehicle_standings",
                True,
            )
        ):
            if (
                bool(
                    self.config.get(
                        "enable_multi_class_styling",
                        True,
                    )
                )
                and bool(
                    self.config.get(
                        "show_position_in_class",
                        True,
                    )
                )
            ):
                position = int(
                    getattr(
                        driver,
                        "position_in_class",
                        0,
                    )
                    or 0
                )
            else:
                position = int(
                    getattr(
                        driver,
                        "position",
                        0,
                    )
                    or 0
                )

            font_name = str(self.config.get("font_name", "Arial"))
            font_size = max(
                6,
                round(
                    float(
                        self.config.get(
                            "vehicle_number_font_size",
                            10.0,
                        )
                    )
                    * s
                ),
            )
            font_key = (font_name, font_size)
            font = self._vehicle_font_cache.get(font_key)
            if font is None:
                font = QFont(font_name)
                font.setBold(True)
                font.setPixelSize(font_size)
                self._vehicle_font_cache[font_key] = font
            painter.setFont(font)
            painter.setPen(
                QColor(
                    colors.get(
                        "vehicle_text_player"
                        if is_player
                        else "vehicle_text",
                        "#FFFFFF",
                    )
                )
            )
            painter.drawText(
                rect,
                Qt.AlignmentFlag.AlignCenter,
                str(position)
                if position > 0
                else "",
            )

        self._draw_leader_markers(
            painter,
            point,
            driver,
        )

    def _cached_marker_pixmap(
        self,
        path: str,
        size: float,
    ) -> QPixmap | None:
        path = path.strip()
        if not path:
            return None
        pixels = max(2, round(float(size) * 2.0))
        key = (path, pixels)
        if key not in self._marker_pixmap_cache:
            source = QPixmap(path)
            if source.isNull():
                self._marker_pixmap_cache[key] = None
            else:
                scaled = source.scaled(
                    pixels,
                    pixels,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                left = (scaled.width() - pixels) // 2
                top = (scaled.height() - pixels) // 2
                cropped = scaled.copy(left, top, pixels, pixels)
                cropped.setDevicePixelRatio(2.0)
                self._marker_pixmap_cache[key] = cropped
        return self._marker_pixmap_cache[key]

    def _draw_leader_markers(
        self,
        painter: QPainter,
        point: QPointF,
        driver: Any,
    ) -> None:
        roles = map_leader_roles(driver, self.config)
        if not roles:
            return

        icon_text = str(self.config.get("leader_marker_text", "♛") or "")
        image_path = str(self.config.get("leader_marker_image", "") or "")
        s = self._responsive_scale
        badge_size = max(
            8.0,
            float(self.config.get("leader_marker_size", 14.0)) * s,
        )
        gap = badge_size * 0.82
        count = len(roles)
        vehicle_class = str(
            getattr(driver, "vehicle_class", "UNKNOWN") or "UNKNOWN"
        )
        for index, role in enumerate(roles):
            color = (
                QColor(
                    self.config.get("colors", {}).get(
                        "leader_marker_overall",
                        "#C0C0C0",
                    )
                )
                if role == "overall"
                else self._class_color(vehicle_class)
            )
            center_x = point.x() + (index - (count - 1) / 2.0) * gap
            badge = QRectF(
                center_x - badge_size / 2.0,
                point.y() - badge_size * 1.45,
                badge_size,
                badge_size,
            )
            image = self._cached_marker_pixmap(
                image_path,
                badge_size * 0.72,
            )
            painter.save()
            if image is not None:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(badge)
                inner = badge.adjusted(
                    badge_size * 0.18,
                    badge_size * 0.18,
                    -badge_size * 0.18,
                    -badge_size * 0.18,
                )
                clip = QPainterPath()
                clip.addEllipse(inner)
                painter.setClipPath(clip)
                painter.drawPixmap(
                    inner,
                    image,
                    QRectF(image.rect()),
                )
            elif icon_text:
                font = QFont("Segoe UI Emoji")
                font.setBold(True)
                font.setPixelSize(max(8, round(badge_size * 0.92)))
                painter.setFont(font)
                painter.setPen(color)
                painter.drawText(
                    badge,
                    Qt.AlignmentFlag.AlignCenter,
                    icon_text,
                )
            painter.restore()

    def _vehicle_color(
        self,
        driver: Any,
        player: Any | None,
    ) -> QColor:
        colors = self.config.get(
            "colors",
            {},
        )
        in_pit = (
            bool(
                getattr(
                    driver,
                    "in_pits",
                    False,
                )
            )
            or bool(
                getattr(
                    driver,
                    "in_garage",
                    False,
                )
            )
        )

        if bool(getattr(driver, "is_player", False)):
            return QColor(
                colors.get(
                    "vehicle_player",
                    "#FF54B8",
                )
            )

        if (
            (
                bool(
                    getattr(
                        driver,
                        "under_yellow",
                        False,
                    )
                )
                or int(
                    getattr(
                        driver,
                        "flag",
                        0,
                    )
                    or 0
                )
                == 2
            )
            and not in_pit
        ):
            return QColor(
                colors.get(
                    "vehicle_yellow",
                    "#FFC400",
                )
            )

        if in_pit:
            return QColor(
                colors.get(
                    "vehicle_in_pit",
                    "#616A75",
                )
            )

        if bool(
            self.config.get(
                "enable_multi_class_styling",
                True,
            )
        ):
            return self._class_color(
                str(
                    getattr(
                        driver,
                        "vehicle_class",
                        "UNKNOWN",
                    )
                    or "UNKNOWN"
                )
            )

        if int(
            getattr(
                driver,
                "position",
                0,
            )
            or 0
        ) == 1:
            return QColor(
                colors.get(
                    "vehicle_leader",
                    "#E040FB",
                )
            )

        if player is not None:
            lap_difference = int(
                getattr(driver, "laps", 0)
                or 0
            ) - int(
                getattr(player, "laps", 0)
                or 0
            )

            if lap_difference > 0:
                return QColor(
                    colors.get(
                        "vehicle_laps_ahead",
                        "#8B4DFF",
                    )
                )
            if lap_difference < 0:
                return QColor(
                    colors.get(
                        "vehicle_laps_behind",
                        "#455A64",
                    )
                )

        return QColor(
            colors.get(
                "vehicle_same_lap",
                "#2196F3",
            )
        )

    def _class_color(
        self,
        class_name: str,
    ) -> QColor:
        cache_key = class_name.strip().casefold()
        cached = self._class_color_cache.get(cache_key)
        if cached is not None:
            return QColor(cached)
        user_colors = self.config.get(
            "class_colors",
            {},
        )

        normalized = class_name.strip().upper()
        aliases = {
            "HYPER": "HYPERCAR",
            "HYPERCAR": "HYPERCAR",
            "LMP2": "LMP2",
            "LMP3": "LMP3",
            "LMGT3": "LMGT3",
            "GT3": "LMGT3",
            "GTE": "GTE",
        }
        category = aliases.get(
            normalized,
            next(
                (
                    target
                    for marker, target in aliases.items()
                    if marker in normalized
                ),
                normalized,
            ),
        )

        if category in user_colors:
            color = QColor(
                user_colors[category]
            )
            self._class_color_cache[cache_key] = color
            return QColor(color)

        digest = hashlib.sha1(
            class_name.encode(
                "utf-8",
                errors="ignore",
            )
        ).digest()
        hue = int.from_bytes(
            digest[:2],
            "little",
        ) % 360
        color = QColor.fromHsl(
            hue,
            185,
            128,
        )
        self._class_color_cache[cache_key] = color
        return QColor(color)

    def _filter_drivers(
        self,
        drivers: list[Any],
        player: Any | None,
    ) -> list[Any]:
        same_class_only = bool(
            self.config.get(
                "show_only_same_class",
                False,
            )
        )
        maximum_lap_difference = max(
            0,
            int(
                self.config.get(
                    "maximum_visible_lap_difference",
                    99,
                )
            ),
        )
        result: list[Any] = []

        for driver in drivers:
            if same_class_only and player is not None:
                if str(
                    getattr(
                        driver,
                        "vehicle_class",
                        "",
                    )
                    or ""
                ) != str(
                    getattr(
                        player,
                        "vehicle_class",
                        "",
                    )
                    or ""
                ):
                    continue

            if (
                player is not None
                and maximum_lap_difference < 99
            ):
                lap_difference = abs(
                    int(
                        getattr(
                            driver,
                            "laps",
                            0,
                        )
                        or 0
                    )
                    - int(
                        getattr(
                            player,
                            "laps",
                            0,
                        )
                        or 0
                    )
                )

                if lap_difference > maximum_lap_difference:
                    continue

            result.append(driver)

        return result

    def _projection(
        self,
        points: list[MapPoint],
        rect: QRectF,
    ) -> MapProjection:
        angle = math.radians(
            float(
                self.config.get(
                    "display_orientation",
                    0.0,
                )
            )
            % 360.0
        )
        cosine = math.cos(angle)
        sine = math.sin(angle)
        rotated: list[
            tuple[float, float]
        ] = []

        for point in points:
            rotated.append(
                (
                    cosine * point.world_x
                    - sine * point.world_y,
                    sine * point.world_x
                    + cosine * point.world_y,
                )
            )

        min_x = min(
            item[0]
            for item in rotated
        )
        max_x = max(
            item[0]
            for item in rotated
        )
        min_y = min(
            item[1]
            for item in rotated
        )
        max_y = max(
            item[1]
            for item in rotated
        )
        width = max(
            1.0,
            max_x - min_x,
        )
        height = max(
            1.0,
            max_y - min_y,
        )
        scale = min(
            rect.width() / width,
            rect.height() / height,
        )
        center_x = (
            min_x + max_x
        ) / 2.0
        center_y = (
            min_y + max_y
        ) / 2.0
        flip_vertical = bool(
            self.config.get(
                "flip_vertical",
                True,
            )
        )

        def project(
            world_x: float,
            world_y: float,
        ) -> QPointF:
            rotated_x = (
                cosine * world_x
                - sine * world_y
            )
            rotated_y = (
                sine * world_x
                + cosine * world_y
            )
            screen_x = (
                rect.center().x()
                + (
                    rotated_x - center_x
                )
                * scale
            )
            screen_y = (
                rect.center().y()
                + (
                    (-1.0 if flip_vertical else 1.0)
                    * (
                        rotated_y - center_y
                    )
                    * scale
                )
            )
            return QPointF(
                screen_x,
                screen_y,
            )

        return MapProjection(
            project=project,
            scale=scale,
            world_center_x=center_x,
            world_center_y=center_y,
        )

    @staticmethod
    def _nearest_point_index(
        points: list[MapPoint],
        distance_m: float,
    ) -> int:
        return min(
            range(len(points)),
            key=lambda index: abs(
                points[index].distance_m
                - distance_m
            ),
        )

    def _preview_map(self) -> TrackMapData:
        if self._preview_map_data is None:
            self._preview_map_data = self.builder.preview()
        return self._preview_map_data

    def _preview_drivers(
        self,
    ) -> list[Any]:
        if self._preview_driver_cache is not None:
            return self._preview_driver_cache

        data = self._preview_map()
        indexes = [
            8,
            34,
            71,
            104,
            143,
            188,
            220,
        ]
        classes = [
            "HYPERCAR",
            "LMGT3",
            "HYPERCAR",
            "LMP2",
            "LMGT3",
            "LMP2",
            "HYPERCAR",
        ]
        drivers: list[Any] = []

        for index, point_index in enumerate(
            indexes,
        ):
            point = data.points[
                point_index
            ]
            drivers.append(
                SimpleNamespace(
                    world_x=point.world_x,
                    world_z=-point.world_y,
                    lap_distance_m=point.distance_m,
                    vehicle_class=classes[index],
                    position=index + 1,
                    position_in_class=(
                        1
                        + sum(
                            1
                            for previous
                            in classes[:index]
                            if previous
                            == classes[index]
                        )
                    ),
                    laps=8,
                    is_player=index == 3,
                    in_pits=index == 5,
                    in_garage=False,
                    under_yellow=index == 1,
                    flag=2 if index == 1 else 0,
                )
            )

        self._preview_driver_cache = drivers
        return drivers

    def mousePressEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if (
            not self.edit_mode
            or event.button()
            != Qt.MouseButton.LeftButton
        ):
            event.ignore()
            return

        self.selected.emit(
            self.widget_id
        )

        if self._resize_handle_rect().contains(
            event.position()
        ):
            self._resizing = True
            self._resize_start_global = (
                event.globalPosition().toPoint()
            )
            self._resize_start_size = (
                max(
                    self.width(),
                    self.height(),
                )
            )
            self.setCursor(
                Qt.CursorShape.SizeFDiagCursor
            )
        else:
            self._dragging = True
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self.frameGeometry().topLeft()
            )
            self.setCursor(
                Qt.CursorShape.ClosedHandCursor
            )

        event.accept()

    def mouseMoveEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if not self.edit_mode:
            event.ignore()
            return

        if self._resizing:
            delta = (
                event.globalPosition().toPoint()
                - self._resize_start_global
            )
            size = max(
                self.minimumWidth(),
                self._resize_start_size
                + max(
                    delta.x(),
                    delta.y(),
                ),
            )

            if bool(
                self.config.get(
                    "lock_aspect_ratio",
                    True,
                )
            ):
                self.resize(
                    size,
                    size,
                )
            else:
                self.resize(
                    max(
                        self.minimumWidth(),
                        self.width()
                        + delta.x(),
                    ),
                    max(
                        self.minimumHeight(),
                        self.height()
                        + delta.y(),
                    ),
                )
                self._resize_start_global = (
                    event.globalPosition().toPoint()
                )

            event.accept()
            return

        if self._dragging:
            self.move(
                event.globalPosition().toPoint()
                - self._drag_offset
            )
            event.accept()
            return

        self.setCursor(
            Qt.CursorShape.SizeFDiagCursor
            if self._resize_handle_rect().contains(
                event.position()
            )
            else Qt.CursorShape.SizeAllCursor
        )

    def mouseReleaseEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if (
            event.button()
            != Qt.MouseButton.LeftButton
        ):
            event.ignore()
            return

        changed = (
            self._dragging
            or self._resizing
        )
        self._dragging = False
        self._resizing = False
        self.setCursor(
            Qt.CursorShape.SizeAllCursor
            if self.edit_mode
            else Qt.CursorShape.ArrowCursor
        )

        if changed:
            self._emit_geometry()
            event.accept()
        else:
            event.ignore()

    def _resize_handle_rect(
        self,
    ) -> QRectF:
        size = max(
            8,
            round(
                12
                * self._responsive_scale
            ),
        )
        return QRectF(
            self.width() - size - 4,
            self.height() - size - 4,
            size,
            size,
        )

    def _emit_geometry(self) -> None:
        screen = self.screen()

        if screen is None:
            return

        rect = screen.geometry()
        self.geometry_changed.emit(
            self.widget_id,
            (
                self.x() - rect.left()
            )
            / rect.width(),
            (
                self.y() - rect.top()
            )
            / rect.height(),
            self.width()
            / rect.width(),
            self.height()
            / rect.height(),
        )
