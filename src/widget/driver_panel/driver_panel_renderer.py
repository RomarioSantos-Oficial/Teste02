from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen


@dataclass(slots=True)
class DriverPanelViewData:
    speed_kmh: float = 0.0
    rpm: float = 0.0
    max_rpm: float = 9000.0
    gear: int = 0
    throttle: float = 0.0
    brake: float = 0.0
    steering: float = 0.0


class DriverPanelRenderer:
    """
    Renderiza o painel de telemetria de forma responsiva.

    Toda medida visual é calculada proporcionalmente ao tamanho atual
    do widget. Assim, ao reduzir o overlay, textos, volante, barras,
    bordas e gráfico também diminuem.
    """

    def draw(
        self,
        painter: QPainter,
        bounds: QRectF,
        data: DriverPanelViewData,
        throttle_history: Sequence[float],
        brake_history: Sequence[float],
        config: dict[str, Any],
        edit_mode: bool = False,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        colors = config.get("colors", {})
        layout_cfg = config.get("layout", {})

        text = QColor(colors.get("text", "#FFFFFF"))
        muted = QColor(colors.get("muted", "#AAB2BD"))
        background = QColor(colors.get("background", "#10151D"))
        panel = QColor(colors.get("panel", "#080C12"))
        grid = QColor(colors.get("grid", "#27313E"))
        blue = QColor(colors.get("rpm_low", "#1769E0"))
        yellow = QColor(colors.get("rpm_shift", "#FFC400"))
        red = QColor(colors.get("rpm_high", "#FF2438"))
        throttle_color = QColor(colors.get("throttle", "#50DF42"))
        brake_color = QColor(colors.get("brake", "#FF2438"))
        wheel_color = QColor(colors.get("wheel", "#445466"))
        center_color = QColor(colors.get("steering_center", "#FFFFFF"))
        border = QColor(colors.get("border", "#424B56"))

        scale = self._ui_scale(bounds, config)
        border_width = max(1.0, 1.6 * scale)
        radius = max(4.0, float(config.get("border_radius", 12)) * scale)

        background.setAlphaF(float(config.get("background_opacity", 0.88)))

        painter.setPen(QPen(border, border_width))
        painter.setBrush(background)
        painter.drawRoundedRect(bounds.adjusted(1, 1, -1, -1), radius, radius)

        margin = max(5.0, 14.0 * scale)
        content = bounds.adjusted(margin, margin, -margin, -margin)

        rpm_height = content.height() * 0.20
        body_top = content.top() + rpm_height + max(3.0, 6.0 * scale)
        body_height = max(1.0, content.bottom() - body_top)

        rpm_rect = QRectF(content.left(), content.top(), content.width(), rpm_height)

        graph_width = content.width() * 0.47
        wheel_width = content.width() * 0.20
        pedal_width = content.width() * 0.11
        info_width = content.width() - graph_width - wheel_width - pedal_width

        graph_rect = QRectF(content.left(), body_top, graph_width, body_height)
        wheel_rect = QRectF(graph_rect.right(), body_top, wheel_width, body_height)
        pedal_rect = QRectF(wheel_rect.right(), body_top, pedal_width, body_height)
        info_rect = QRectF(pedal_rect.right(), body_top, info_width, body_height)

        self._draw_segmented_rpm(
            painter,
            rpm_rect,
            data,
            config,
            text,
            blue,
            yellow,
            red,
            panel,
            layout_cfg,
            scale,
        )
        self._draw_input_graph_same_axis(
            painter,
            graph_rect,
            throttle_history,
            brake_history,
            throttle_color,
            brake_color,
            text,
            muted,
            panel,
            grid,
            config,
            scale,
        )
        self._draw_steering_wheel(
            painter,
            wheel_rect,
            data.steering,
            wheel_color,
            center_color,
            text,
            panel,
            config,
            scale,
        )
        self._draw_pedals(
            painter,
            pedal_rect,
            data.throttle,
            data.brake,
            throttle_color,
            brake_color,
            text,
            panel,
            scale,
        )
        self._draw_gear_speed(
            painter,
            info_rect,
            data.gear,
            data.speed_kmh,
            text,
            blue,
            panel,
            config,
            scale,
        )

        if edit_mode:
            edit_pen = QPen(
                QColor(colors.get("edit_border", "#8B5CF6")),
                max(1.2, 2.0 * scale),
            )
            edit_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(edit_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                bounds.adjusted(2, 2, -2, -2),
                radius,
                radius,
            )

        painter.restore()

    @staticmethod
    def _ui_scale(bounds: QRectF, config: dict[str, Any]) -> float:
        """
        Escala baseada no menor eixo do widget.

        O design-base foi pensado para aproximadamente 1380x420.
        Em tamanhos menores, tudo reduz proporcionalmente.
        """
        base_width = float(config.get("design_base_width", 1380))
        base_height = float(config.get("design_base_height", 420))

        width_scale = bounds.width() / max(1.0, base_width)
        height_scale = bounds.height() / max(1.0, base_height)

        return max(0.28, min(2.50, min(width_scale, height_scale)))

    @staticmethod
    def _font(
        config: dict[str, Any],
        pixel_size: float,
        bold: bool = False,
    ) -> QFont:
        family = str(config.get("font", {}).get("family", "Arial"))
        font = QFont(family)
        font.setPixelSize(max(7, int(pixel_size)))
        font.setBold(bold)
        return font

    def _fit_font(
        self,
        config: dict[str, Any],
        rect: QRectF,
        text: str,
        preferred_px: float,
        minimum_px: float,
        bold: bool = False,
    ) -> QFont:
        size = max(minimum_px, preferred_px)

        while size > minimum_px:
            font = self._font(config, size, bold)
            metrics = QFontMetricsF(font)

            if metrics.horizontalAdvance(text) <= rect.width() * 0.92:
                return font

            size -= 1

        return self._font(config, minimum_px, bold)

    def _draw_segmented_rpm(
        self,
        painter: QPainter,
        rect: QRectF,
        data: DriverPanelViewData,
        config: dict[str, Any],
        text: QColor,
        blue: QColor,
        yellow: QColor,
        red: QColor,
        panel: QColor,
        layout_cfg: dict[str, Any],
        scale: float,
    ) -> None:
        segments = max(10, int(layout_cfg.get("rpm_segments", 28)))
        shift_start = float(layout_cfg.get("shift_start", 0.78))
        red_start = float(layout_cfg.get("red_start", 0.92))
        ratio = (
            0.0
            if data.max_rpm <= 0
            else max(0.0, min(1.0, data.rpm / data.max_rpm))
        )

        label_width = rect.width() * 0.075
        number_width = rect.width() * 0.10

        bars_rect = QRectF(
            rect.left() + label_width,
            rect.top() + rect.height() * 0.18,
            rect.width() - label_width - number_width,
            rect.height() * 0.56,
        )

        label_font = self._fit_font(
            config,
            QRectF(rect.left(), rect.top(), label_width, rect.height()),
            "RPM",
            24 * scale,
            8,
            True,
        )
        painter.setFont(label_font)
        painter.setPen(text)
        painter.drawText(
            QRectF(rect.left(), rect.top(), label_width, rect.height()),
            Qt.AlignmentFlag.AlignCenter,
            "RPM",
        )

        rpm_text = f"{data.rpm:.0f}"
        rpm_font = self._fit_font(
            config,
            QRectF(rect.right() - number_width, rect.top(), number_width, rect.height()),
            rpm_text,
            22 * scale,
            8,
            True,
        )
        painter.setFont(rpm_font)
        painter.drawText(
            QRectF(rect.right() - number_width, rect.top(), number_width, rect.height()),
            Qt.AlignmentFlag.AlignCenter,
            rpm_text,
        )

        gap = max(1.0, 4.0 * scale)
        segment_width = max(
            1.0,
            (bars_rect.width() - gap * (segments - 1)) / segments,
        )
        active_count = round(ratio * segments)

        for index in range(segments):
            segment_ratio = (index + 1) / segments

            if segment_ratio >= red_start:
                active_color = red
            elif segment_ratio >= shift_start:
                active_color = yellow
            else:
                active_color = blue

            inactive = QColor(panel)
            inactive = inactive.lighter(145)
            inactive.setAlpha(150)

            color = active_color if index < active_count else inactive

            segment = QRectF(
                bars_rect.left() + index * (segment_width + gap),
                bars_rect.top(),
                segment_width,
                bars_rect.height(),
            )

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(
                segment,
                max(1.0, 2.0 * scale),
                max(1.0, 2.0 * scale),
            )

    def _draw_input_graph_same_axis(
        self,
        painter: QPainter,
        rect: QRectF,
        throttle_history: Sequence[float],
        brake_history: Sequence[float],
        throttle_color: QColor,
        brake_color: QColor,
        text: QColor,
        muted: QColor,
        panel: QColor,
        grid: QColor,
        config: dict[str, Any],
        scale: float,
    ) -> None:
        radius = max(3.0, 8.0 * scale)
        painter.setPen(QPen(grid.lighter(135), max(1.0, scale)))
        painter.setBrush(panel)
        painter.drawRoundedRect(rect, radius, radius)

        label_width = rect.width() * 0.18
        graph = rect.adjusted(
            label_width,
            max(4.0, 8.0 * scale),
            -max(4.0, 8.0 * scale),
            -max(4.0, 8.0 * scale),
        )

        painter.setPen(QPen(grid, max(0.8, scale)))
        vertical_lines = int(config.get("graph_vertical_lines", 8))

        for index in range(vertical_lines + 1):
            x = graph.left() + graph.width() * index / max(1, vertical_lines)
            painter.drawLine(
                QPointF(x, graph.top()),
                QPointF(x, graph.bottom()),
            )

        for fraction in (0.0, 0.25, 0.50, 0.75, 1.0):
            y = graph.top() + graph.height() * fraction
            painter.drawLine(
                QPointF(graph.left(), y),
                QPointF(graph.right(), y),
            )

        # Ambos usam a mesma escala vertical: 0% embaixo e 100% em cima.
        self._draw_history_path_same_axis(
            painter,
            graph,
            throttle_history,
            throttle_color,
            max(1.2, 2.2 * scale),
        )
        self._draw_history_path_same_axis(
            painter,
            graph,
            brake_history,
            brake_color,
            max(1.2, 2.2 * scale),
        )

        accel_label_rect = QRectF(
            rect.left() + max(3.0, 5.0 * scale),
            graph.top(),
            label_width - max(6.0, 10.0 * scale),
            graph.height() * 0.28,
        )
        brake_label_rect = QRectF(
            rect.left() + max(3.0, 5.0 * scale),
            graph.top() + graph.height() * 0.28,
            label_width - max(6.0, 10.0 * scale),
            graph.height() * 0.28,
        )

        label_font = self._fit_font(
            config,
            accel_label_rect,
            "ACCEL",
            18 * scale,
            7,
            True,
        )
        painter.setFont(label_font)
        painter.setPen(throttle_color)
        painter.drawText(
            accel_label_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "ACCEL",
        )

        painter.setPen(brake_color)
        painter.drawText(
            brake_label_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "BRAKE",
        )

        percent_font = self._font(config, max(7.0, 13 * scale), False)
        painter.setFont(percent_font)
        painter.setPen(muted)

        for value, fraction in (("100%", 0.0), ("50%", 0.5), ("0%", 1.0)):
            y = graph.top() + graph.height() * fraction - 8 * scale
            painter.drawText(
                QRectF(
                    rect.left(),
                    y,
                    label_width - max(5.0, 8.0 * scale),
                    max(14.0, 18.0 * scale),
                ),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                value,
            )

        legend_height = max(14.0, 20.0 * scale)
        legend = QRectF(
            graph.left(),
            graph.bottom() - legend_height,
            graph.width(),
            legend_height,
        )

        legend_font = self._font(config, max(7.0, 12.0 * scale), True)
        painter.setFont(legend_font)

        painter.setPen(throttle_color)
        painter.drawText(
            QRectF(legend.left(), legend.top(), legend.width() / 2, legend.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "ACCEL",
        )

        painter.setPen(brake_color)
        painter.drawText(
            QRectF(
                legend.center().x(),
                legend.top(),
                legend.width() / 2,
                legend.height(),
            ),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "BRAKE",
        )

    @staticmethod
    def _draw_history_path_same_axis(
        painter: QPainter,
        graph: QRectF,
        values: Sequence[float],
        color: QColor,
        width: float,
    ) -> None:
        if len(values) < 2:
            return

        path = QPainterPath()
        count = len(values)

        for index, raw_value in enumerate(values):
            value = max(0.0, min(1.0, float(raw_value)))
            x = graph.left() + graph.width() * index / max(1, count - 1)
            y = graph.bottom() - value * graph.height()

            if index == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        pen = QPen(color, width)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def _draw_steering_wheel(
        self,
        painter: QPainter,
        rect: QRectF,
        steering: float,
        wheel_color: QColor,
        center_color: QColor,
        text: QColor,
        panel: QColor,
        config: dict[str, Any],
        scale: float,
    ) -> None:
        inner = rect.adjusted(
            max(2.0, 5.0 * scale),
            max(2.0, 5.0 * scale),
            -max(2.0, 5.0 * scale),
            -max(2.0, 5.0 * scale),
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(panel)
        painter.drawRoundedRect(
            inner,
            max(3.0, 8.0 * scale),
            max(3.0, 8.0 * scale),
        )

        center = inner.center()
        radius = max(10.0, min(inner.width(), inner.height()) * 0.34)
        max_degrees = float(config.get("steering_visual_degrees", 180))
        angle = max(-1.0, min(1.0, steering)) * max_degrees

        center_pen = QPen(
            center_color,
            max(1.0, radius * 0.035),
        )
        center_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(center_pen)
        painter.drawLine(
            QPointF(center.x(), center.y() - radius * 1.10),
            QPointF(center.x(), center.y() + radius * 1.10),
        )

        painter.save()
        painter.translate(center)
        painter.rotate(angle)

        wheel_pen = QPen(
            wheel_color,
            max(2.0, radius * 0.17),
        )
        painter.setPen(wheel_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), radius, radius)

        spoke_pen = QPen(
            text,
            max(1.5, radius * 0.075),
        )
        painter.setPen(spoke_pen)
        painter.drawLine(QPointF(0, 0), QPointF(0, -radius * 0.82))
        painter.drawLine(
            QPointF(0, 0),
            QPointF(-radius * 0.72, radius * 0.46),
        )
        painter.drawLine(
            QPointF(0, 0),
            QPointF(radius * 0.72, radius * 0.46),
        )

        marker_color = QColor(
            config.get("colors", {}).get("steering_marker", "#4CFF5E")
        )
        marker_pen = QPen(
            marker_color,
            max(2.0, radius * 0.10),
        )
        painter.setPen(marker_pen)
        painter.drawLine(
            QPointF(0, -radius * 1.02),
            QPointF(0, -radius * 0.78),
        )

        painter.setBrush(wheel_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QPointF(0, 0),
            radius * 0.20,
            radius * 0.20,
        )

        painter.restore()

    def _draw_pedals(
        self,
        painter: QPainter,
        rect: QRectF,
        throttle: float,
        brake: float,
        throttle_color: QColor,
        brake_color: QColor,
        text: QColor,
        panel: QColor,
        scale: float,
    ) -> None:
        inner = rect.adjusted(
            max(2.0, 4.0 * scale),
            max(2.0, 5.0 * scale),
            -max(2.0, 4.0 * scale),
            -max(2.0, 5.0 * scale),
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(panel)
        painter.drawRoundedRect(
            inner,
            max(3.0, 8.0 * scale),
            max(3.0, 8.0 * scale),
        )

        bar_width = inner.width() * 0.28
        gap = inner.width() * 0.12
        top = inner.top() + inner.height() * 0.16
        bar_height = inner.height() * 0.70

        brake_rect = QRectF(
            inner.left() + inner.width() * 0.12,
            top,
            bar_width,
            bar_height,
        )
        throttle_rect = QRectF(
            brake_rect.right() + gap,
            top,
            bar_width,
            bar_height,
        )

        self._vertical_bar(
            painter,
            brake_rect,
            brake,
            brake_color,
            scale,
        )
        self._vertical_bar(
            painter,
            throttle_rect,
            throttle,
            throttle_color,
            scale,
        )

        label_font = self._font(
            {"font": {"family": "Arial"}},
            max(7.0, 13.0 * scale),
            True,
        )
        painter.setFont(label_font)

        painter.setPen(brake_color)
        painter.drawText(
            QRectF(
                brake_rect.left() - 6 * scale,
                inner.top(),
                brake_rect.width() + 12 * scale,
                max(16.0, 22.0 * scale),
            ),
            Qt.AlignmentFlag.AlignCenter,
            "BRK",
        )

        painter.setPen(throttle_color)
        painter.drawText(
            QRectF(
                throttle_rect.left() - 6 * scale,
                inner.top(),
                throttle_rect.width() + 12 * scale,
                max(16.0, 22.0 * scale),
            ),
            Qt.AlignmentFlag.AlignCenter,
            "THR",
        )

    @staticmethod
    def _vertical_bar(
        painter: QPainter,
        rect: QRectF,
        ratio: float,
        color: QColor,
        scale: float,
    ) -> None:
        ratio = max(0.0, min(1.0, ratio))
        segments = 7
        gap = max(1.0, 3.0 * scale)
        segment_height = max(
            1.0,
            (rect.height() - gap * (segments - 1)) / segments,
        )
        active = round(ratio * segments)

        for index in range(segments):
            y = rect.bottom() - (index + 1) * segment_height - index * gap
            segment = QRectF(
                rect.left(),
                y,
                rect.width(),
                segment_height,
            )

            painter.setPen(
                QPen(color.darker(130), max(0.8, scale))
            )
            painter.setBrush(
                color if index < active else QColor("#111820")
            )
            painter.drawRoundedRect(
                segment,
                max(1.0, 2.0 * scale),
                max(1.0, 2.0 * scale),
            )

    def _draw_gear_speed(
        self,
        painter: QPainter,
        rect: QRectF,
        gear: int,
        speed_kmh: float,
        text: QColor,
        blue: QColor,
        panel: QColor,
        config: dict[str, Any],
        scale: float,
    ) -> None:
        inner = rect.adjusted(
            max(2.0, 5.0 * scale),
            max(2.0, 5.0 * scale),
            -max(2.0, 5.0 * scale),
            -max(2.0, 5.0 * scale),
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(panel)
        painter.drawRoundedRect(
            inner,
            max(3.0, 8.0 * scale),
            max(3.0, 8.0 * scale),
        )

        gear_rect = QRectF(
            inner.left() + inner.width() * 0.18,
            inner.top() + inner.height() * 0.05,
            inner.width() * 0.64,
            inner.height() * 0.48,
        )

        painter.setBrush(QColor("#07101E"))
        painter.setPen(QPen(blue, max(1.0, 3.0 * scale)))
        painter.drawEllipse(gear_rect)

        gear_text = self._format_gear(gear)
        gear_font = self._fit_font(
            config,
            gear_rect,
            gear_text,
            gear_rect.height() * 0.45,
            9,
            True,
        )
        painter.setFont(gear_font)
        painter.setPen(text)
        painter.drawText(
            gear_rect,
            Qt.AlignmentFlag.AlignCenter,
            gear_text,
        )

        speed_rect = QRectF(
            inner.left() + inner.width() * 0.06,
            inner.top() + inner.height() * 0.62,
            inner.width() * 0.88,
            inner.height() * 0.27,
        )

        painter.setBrush(QColor("#07101E"))
        painter.setPen(QPen(blue, max(1.0, 2.0 * scale)))
        painter.drawRoundedRect(
            speed_rect,
            max(2.0, 6.0 * scale),
            max(2.0, 6.0 * scale),
        )

        speed_text = f"{speed_kmh:.0f} km/h"
        speed_font = self._fit_font(
            config,
            speed_rect,
            speed_text,
            speed_rect.height() * 0.42,
            7,
            True,
        )
        painter.setFont(speed_font)
        painter.setPen(text)
        painter.drawText(
            speed_rect,
            Qt.AlignmentFlag.AlignCenter,
            speed_text,
        )

    @staticmethod
    def _format_gear(gear: int) -> str:
        if gear < 0:
            return "R"
        if gear == 0:
            return "N"
        return str(gear)
