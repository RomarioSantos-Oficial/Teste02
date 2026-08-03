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
        self.update()

    def set_edit_mode(
        self,
        enabled: bool,
    ) -> None:
        self.edit_mode = bool(enabled)

        if self.edit_mode:
            self.show()

        self.setCursor(
            Qt.CursorShape.SizeAllCursor
            if self.edit_mode
            else Qt.CursorShape.ArrowCursor
        )
        self.update()

    def reset_session_state(self) -> None:
        self.builder.reset()
        self.map_data = TrackMapData()
        self.session = None
        self.update()

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
            self.builder.preview()
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

        path.moveTo(
            screen_points[0]
        )
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

        for index, point in enumerate(
            screen_points[1:],
            start=1,
        ):
            if (
                index == len(screen_points) - 1
                or index % skip == 0
            ):
                path.lineTo(point)

        close_threshold = max(
            10.0,
            float(
                self.config.get(
                    "loop_close_distance_m",
                    500.0,
                )
            ),
        )
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
    ) -> None:
        if self.edit_mode and self.session is None:
            drivers = self._preview_drivers()
        else:
            drivers = list(
                getattr(
                    self.session,
                    "drivers",
                    [],
                )
                or []
            )

        player = next(
            (
                driver
                for driver in drivers
                if bool(
                    getattr(
                        driver,
                        "is_player",
                        False,
                    )
                )
            ),
            None,
        )
        drivers = self._filter_drivers(
            drivers,
            player,
        )
        drivers.sort(
            key=lambda driver: (
                bool(
                    getattr(
                        driver,
                        "is_player",
                        False,
                    )
                ),
                int(
                    getattr(
                        driver,
                        "position",
                        999,
                    )
                    or 999
                )
                == 1,
            )
        )

        for driver in drivers:
            point = projection.project(
                float(
                    getattr(
                        driver,
                        "world_x",
                        0.0,
                    )
                    or 0.0
                ),
                -float(
                    getattr(
                        driver,
                        "world_z",
                        0.0,
                    )
                    or 0.0
                ),
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
                player,
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
            drivers = self._preview_drivers()
            track_length = 13626.0
        else:
            drivers = list(
                getattr(
                    self.session,
                    "drivers",
                    [],
                )
                or []
            )
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

        player = next(
            (
                driver
                for driver in drivers
                if bool(
                    getattr(
                        driver,
                        "is_player",
                        False,
                    )
                )
            ),
            None,
        )

        for driver in self._filter_drivers(
            drivers,
            player,
        ):
            progress = (
                float(
                    getattr(
                        driver,
                        "lap_distance_m",
                        0.0,
                    )
                    or 0.0
                )
                / track_length
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
                player,
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
        size = max(
            7.0,
            float(
                self.config.get(
                    "vehicle_size",
                    18.0,
                )
            )
            * s,
        )
        is_player = bool(
            getattr(
                driver,
                "is_player",
                False,
            )
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

        # O contorno acompanha a cor oficial da categoria, sem criar
        # uma borda visual de outra cor ao redor da bolinha.
        outline_color = fill

        painter.setPen(
            (
                QPen(
                    QColor(outline_color),
                    outline_width,
                )
                if outline_width > 0
                else Qt.PenStyle.NoPen
            )
        )
        painter.setBrush(
            QBrush(fill)
        )
        rect = QRectF(
            point.x() - size / 2.0,
            point.y() - size / 2.0,
            size,
            size,
        )
        painter.drawEllipse(rect)

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

            font = QFont(
                str(
                    self.config.get(
                        "font_name",
                        "Arial",
                    )
                )
            )
            font.setBold(True)
            font.setPixelSize(
                max(
                    6,
                    round(
                        float(
                            self.config.get(
                                "font_size",
                                14,
                            )
                        )
                        * 0.62
                        * s
                    ),
                )
            )
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

        if bool(
            getattr(
                driver,
                "is_player",
                False,
            )
        ):
            return QColor(
                colors.get(
                    "vehicle_player",
                    "#00D084",
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
            return QColor(
                user_colors[category]
            )

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
        return QColor.fromHsl(
            hue,
            185,
            128,
        )

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

    def _preview_drivers(
        self,
    ) -> list[Any]:
        data = self.builder.preview()
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
