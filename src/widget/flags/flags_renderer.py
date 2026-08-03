from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPen,
)

from .flags_models import FlagState, FlagTarget


class FlagsRenderer:
    def preferred_height(
        self,
        width: int,
        config: dict[str, Any],
        state: FlagState | None = None,
    ) -> int:
        show_radar = bool(
            config.get("show_radar", True)
        )
        show_details = bool(
            config.get(
                "show_target_details",
                True,
            )
        )
        ratio = 0.27 if (
            show_radar or show_details
        ) else 0.20
        return max(
            94,
            min(220, int(width * ratio)),
        )

    def draw(
        self,
        painter: QPainter,
        bounds: QRectF,
        state: FlagState,
        config: dict[str, Any],
        edit_mode: bool = False,
    ) -> None:
        painter.save()
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True,
        )

        accent, accent_light = self._colors(
            state.kind,
            config,
        )
        colors = config.get("colors", {})
        background = QColor(
            colors.get("background", "#0A0F17")
        )
        background.setAlphaF(
            max(
                0.05,
                min(
                    1.0,
                    float(
                        config.get(
                            "background_opacity",
                            0.94,
                        )
                    ),
                ),
            )
        )
        border = QColor(
            colors.get("border", "#344155")
        )
        text = QColor(
            colors.get("text", "#FFFFFF")
        )
        muted = QColor(
            colors.get("muted", "#AAB5C5")
        )

        scale = max(
            0.42,
            min(2.0, bounds.width() / 600.0),
        )
        radius = max(
            7.0,
            float(
                config.get(
                    "border_radius",
                    14,
                )
            )
            * scale,
        )
        margin = max(5.0, 10.0 * scale)
        card = bounds.adjusted(
            1,
            1,
            -1,
            -1,
        )

        painter.setPen(
            QPen(
                border,
                max(1.0, 1.2 * scale),
            )
        )
        painter.setBrush(background)
        painter.drawRoundedRect(
            card,
            radius,
            radius,
        )

        accent_width = max(
            7.0,
            12.0 * scale,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        accent_rect = QRectF(
            card.left(),
            card.top(),
            accent_width,
            card.height(),
        )
        painter.drawRoundedRect(
            accent_rect,
            radius,
            radius,
        )
        painter.drawRect(
            QRectF(
                accent_rect.center().x(),
                accent_rect.top(),
                accent_rect.width() / 2,
                accent_rect.height(),
            )
        )

        if state.kind == "checkered":
            self._draw_checkered_strip(
                painter,
                QRectF(
                    card.left(),
                    card.top(),
                    card.width(),
                    max(8.0, 13.0 * scale),
                ),
                scale,
            )

        content = card.adjusted(
            accent_width + margin,
            margin,
            -margin,
            -margin,
        )
        radar_width = (
            content.width() * 0.29
            if (
                bool(
                    config.get(
                        "show_radar",
                        True,
                    )
                )
                and bool(state.radar_targets)
            )
            else 0.0
        )
        gap = max(5.0, 10.0 * scale)
        text_rect = QRectF(
            content.left(),
            content.top(),
            content.width()
            - radar_width
            - (gap if radar_width else 0),
            content.height(),
        )
        radar_rect = (
            QRectF(
                text_rect.right() + gap,
                content.top(),
                radar_width,
                content.height(),
            )
            if radar_width
            else None
        )

        title_h = text_rect.height() * 0.36
        title_rect = QRectF(
            text_rect.left(),
            text_rect.top(),
            text_rect.width(),
            title_h,
        )
        subtitle_rect = QRectF(
            text_rect.left(),
            title_rect.bottom(),
            text_rect.width(),
            text_rect.height() * 0.22,
        )
        details_rect = QRectF(
            text_rect.left(),
            subtitle_rect.bottom(),
            text_rect.width(),
            text_rect.bottom()
            - subtitle_rect.bottom(),
        )

        painter.setPen(accent)
        painter.setFont(
            self._fit_font(
                config,
                title_rect,
                state.title or "FLAGS",
                title_rect.height() * 0.67,
                10,
                True,
            )
        )
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            state.title or "FLAGS",
        )

        subtitle = state.subtitle
        if state.sector_text:
            subtitle = (
                f"{subtitle}  ·  {state.sector_text}"
                if subtitle
                else state.sector_text
            )

        painter.setPen(muted)
        painter.setFont(
            self._fit_font(
                config,
                subtitle_rect,
                subtitle,
                subtitle_rect.height() * 0.54,
                8,
                True,
            )
        )
        painter.drawText(
            subtitle_rect,
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            subtitle,
        )

        if (
            bool(
                config.get(
                    "show_target_details",
                    True,
                )
            )
            and state.target is not None
        ):
            self._draw_target(
                painter,
                details_rect,
                state.target,
                accent,
                accent_light,
                text,
                muted,
                config,
                scale,
            )

        if radar_rect is not None:
            self._draw_radar(
                painter,
                radar_rect,
                state,
                accent,
                accent_light,
                colors,
                scale,
            )

        self._draw_secondary_flags(
            painter,
            content,
            state.secondary_flags,
            config,
            scale,
        )

        if edit_mode:
            edit = QColor(
                colors.get(
                    "edit_border",
                    "#9B5CFF",
                )
            )
            pen = QPen(
                edit,
                max(1.2, 2.0 * scale),
            )
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                card.adjusted(
                    2,
                    2,
                    -2,
                    -2,
                ),
                radius,
                radius,
            )

        painter.restore()

    def _draw_target(
        self,
        painter: QPainter,
        rect: QRectF,
        target: FlagTarget,
        accent: QColor,
        accent_light: QColor,
        text: QColor,
        muted: QColor,
        config: dict[str, Any],
        scale: float,
    ) -> None:
        top = QRectF(
            rect.left(),
            rect.top(),
            rect.width(),
            rect.height() * 0.50,
        )
        bottom = QRectF(
            rect.left(),
            top.bottom(),
            rect.width(),
            rect.bottom() - top.bottom(),
        )

        position = (
            f"P{target.position}"
            if target.position > 0
            else "P--"
        )
        info = (
            f"{target.vehicle_class}  ·  "
            f"{target.driver_name}  ·  {position}"
        )
        painter.setPen(text)
        painter.setFont(
            self._fit_font(
                config,
                top,
                info,
                top.height() * 0.54,
                8,
                True,
            )
        )
        painter.drawText(
            top,
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            info,
        )

        direction = (
            "AHEAD"
            if target.distance_m >= 0
            else "BEHIND"
        )
        distance = abs(target.distance_m)

        if distance <= 350:
            distance_text = f"{direction}  {distance:.0f} m"
        else:
            distance_text = (
                f"{direction}  {target.time_gap_s:.1f} s"
            )

        speed_text = (
            f"  ·  {target.speed_kmh:.0f} km/h"
            if target.speed_kmh > 0
            else ""
        )
        value = distance_text + speed_text

        painter.setPen(accent_light)
        painter.setFont(
            self._fit_font(
                config,
                bottom,
                value,
                bottom.height() * 0.56,
                8,
                True,
            )
        )
        painter.drawText(
            bottom,
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            value,
        )

    def _draw_radar(
        self,
        painter: QPainter,
        rect: QRectF,
        state: FlagState,
        accent: QColor,
        accent_light: QColor,
        colors: dict[str, Any],
        scale: float,
    ) -> None:
        panel = QColor(
            colors.get(
                "panel",
                "#111923",
            )
        )
        lane = QColor(
            colors.get(
                "radar_lane",
                "#344153",
            )
        )
        player_color = QColor(
            colors.get(
                "radar_player",
                "#FFFFFF",
            )
        )

        painter.setPen(
            QPen(
                accent.darker(150),
                max(1.0, scale),
            )
        )
        painter.setBrush(panel)
        painter.drawRoundedRect(
            rect,
            max(4.0, 9.0 * scale),
            max(4.0, 9.0 * scale),
        )

        inner = rect.adjusted(
            10 * scale,
            8 * scale,
            -10 * scale,
            -8 * scale,
        )
        center_x = inner.center().x()
        center_y = inner.center().y()
        lane_half = inner.width() * 0.26

        painter.setPen(
            QPen(
                lane,
                max(1.0, 2.0 * scale),
            )
        )
        painter.drawLine(
            QPointF(
                center_x - lane_half,
                inner.top(),
            ),
            QPointF(
                center_x - lane_half,
                inner.bottom(),
            ),
        )
        painter.drawLine(
            QPointF(
                center_x + lane_half,
                inner.top(),
            ),
            QPointF(
                center_x + lane_half,
                inner.bottom(),
            ),
        )

        dash_pen = QPen(
            lane.lighter(130),
            max(1.0, scale),
        )
        dash_pen.setStyle(
            Qt.PenStyle.DashLine
        )
        painter.setPen(dash_pen)
        painter.drawLine(
            QPointF(center_x, inner.top()),
            QPointF(center_x, inner.bottom()),
        )

        player_w = max(5.0, 8.0 * scale)
        player_h = max(11.0, 18.0 * scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(player_color)
        painter.drawRoundedRect(
            QRectF(
                center_x - player_w / 2,
                center_y - player_h / 2,
                player_w,
                player_h,
            ),
            2 * scale,
            2 * scale,
        )

        max_distance = max(
            50.0,
            float(
                250.0
                if state.kind == "blue"
                else 140.0
            ),
        )

        for target in state.radar_targets:
            y = center_y - (
                target.distance_m / max_distance
            ) * (inner.height() / 2)
            y = max(
                inner.top() + 5 * scale,
                min(
                    inner.bottom() - 5 * scale,
                    y,
                ),
            )
            lateral_ratio = max(
                -1.0,
                min(
                    1.0,
                    target.lateral_m / 5.0,
                ),
            )
            x = center_x + lateral_ratio * (
                lane_half * 0.72
            )

            painter.setBrush(
                accent_light
                if target.is_blue_context
                else accent
            )
            painter.drawRoundedRect(
                QRectF(
                    x - player_w / 2,
                    y - player_h / 2,
                    player_w,
                    player_h,
                ),
                2 * scale,
                2 * scale,
            )

    def _draw_secondary_flags(
        self,
        painter: QPainter,
        content: QRectF,
        flags: tuple[str, ...],
        config: dict[str, Any],
        scale: float,
    ) -> None:
        if not flags:
            return

        colors = config.get("colors", {})
        right = content.right()
        top = content.top()
        height = max(14.0, 22.0 * scale)

        for value in reversed(flags):
            if value == "BLUE":
                color = QColor(
                    colors.get(
                        "blue",
                        "#2787FF",
                    )
                )
            else:
                color = QColor("#FFFFFF")

            width = max(
                45.0,
                70.0 * scale,
            )
            box = QRectF(
                right - width,
                top,
                width,
                height,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(
                box,
                height / 2,
                height / 2,
            )
            painter.setPen(
                QColor("#FFFFFF")
            )
            painter.setFont(
                self._font(
                    config,
                    height * 0.44,
                    True,
                )
            )
            painter.drawText(
                box,
                Qt.AlignmentFlag.AlignCenter,
                value,
            )
            right = box.left() - 4 * scale

    @staticmethod
    def _draw_checkered_strip(
        painter: QPainter,
        rect: QRectF,
        scale: float,
    ) -> None:
        cell = max(5.0, 9.0 * scale)
        columns = int(rect.width() / cell) + 1
        rows = 2

        for row in range(rows):
            for column in range(columns):
                color = (
                    QColor("#F3F3F3")
                    if (row + column) % 2 == 0
                    else QColor("#111111")
                )
                painter.fillRect(
                    QRectF(
                        rect.left() + column * cell,
                        rect.top() + row * cell,
                        cell,
                        cell,
                    ),
                    color,
                )

    @staticmethod
    def _colors(
        kind: str,
        config: dict[str, Any],
    ) -> tuple[QColor, QColor]:
        colors = config.get("colors", {})
        mapping = {
            "yellow": (
                colors.get("yellow", "#FFD400"),
                colors.get(
                    "yellow_light",
                    "#FFF1A6",
                ),
            ),
            "fcy": (
                colors.get("yellow", "#FFD400"),
                colors.get(
                    "yellow_light",
                    "#FFF1A6",
                ),
            ),
            "blue": (
                colors.get("blue", "#2787FF"),
                colors.get(
                    "blue_light",
                    "#8CC6FF",
                ),
            ),
            "green": (
                colors.get("green", "#20C763"),
                colors.get(
                    "green_light",
                    "#89E8AD",
                ),
            ),
            "red": (
                colors.get("red", "#EF3340"),
                colors.get(
                    "red_light",
                    "#FF9AA2",
                ),
            ),
            "checkered": (
                colors.get(
                    "checkered",
                    "#F2F2F2",
                ),
                QColor("#FFFFFF"),
            ),
        }
        primary, secondary = mapping.get(
            kind,
            (
                colors.get("muted", "#AAB5C5"),
                colors.get("text", "#FFFFFF"),
            ),
        )
        return QColor(primary), QColor(secondary)

    @staticmethod
    def _font(
        config: dict[str, Any],
        pixel_size: float,
        bold: bool = False,
    ) -> QFont:
        font = QFont(
            str(
                config.get(
                    "font",
                    {},
                ).get(
                    "family",
                    "Arial",
                )
            )
        )
        font.setPixelSize(
            max(7, int(pixel_size))
        )
        font.setBold(bold)
        return font

    def _fit_font(
        self,
        config: dict[str, Any],
        rect: QRectF,
        value: str,
        preferred: float,
        minimum: float,
        bold: bool = False,
    ) -> QFont:
        size = max(minimum, preferred)

        while size > minimum:
            font = self._font(
                config,
                size,
                bold,
            )
            metrics = QFontMetricsF(font)

            if (
                metrics.horizontalAdvance(value)
                <= rect.width() * 0.96
                and metrics.height()
                <= rect.height() * 0.95
            ):
                return font

            size -= 1

        return self._font(
            config,
            minimum,
            bold,
        )
