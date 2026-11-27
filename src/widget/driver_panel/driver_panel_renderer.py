from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen
from src.i18n import tr


@dataclass(slots=True)
class DriverPanelViewData:
    speed_kmh: float = 0.0
    rpm: float = 0.0
    max_rpm: float = 9000.0
    gear: int = 0
    throttle: float = 0.0
    brake: float = 0.0
    clutch: float = 0.0
    steering: float = 0.0
    max_rpm_seen: float = 0.0
    max_throttle_seen: float = 0.0
    max_brake_seen: float = 0.0
    max_clutch_seen: float = 0.0
    throttle_abrupt: bool = False
    brake_abrupt: bool = False
    gear_flash: bool = False


class DriverPanelRenderer:
    """Desenha o painel sem modificar ou filtrar os dados da telemetria."""

    def draw(
        self, painter: QPainter, bounds: QRectF, data: DriverPanelViewData,
        throttle_history: Sequence[float], brake_history: Sequence[float],
        clutch_history: Sequence[float], rpm_history: Sequence[float],
        steering_history: Sequence[float], speed_history: Sequence[float],
        config: dict[str, Any], edit_mode: bool = False,
        reference_throttle_history: Sequence[float] = (),
        reference_brake_history: Sequence[float] = (),
    ) -> None:
        del rpm_history, steering_history, speed_history
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        color_cfg = config.get("colors", {})
        outer_bg = QColor(color_cfg.get("background", "#10151D"))
        outer_bg.setAlphaF(max(0.0, min(1.0, float(config.get("background_opacity", 0.88)))))
        outer_border = QColor(color_cfg.get("border", "#424B56"))
        text = QColor(color_cfg.get("text", "#FFFFFF"))
        muted = QColor(color_cfg.get("muted", "#AAB2BD"))
        colors = {
            "rpm_low": QColor(color_cfg.get("rpm_low", "#1769E0")),
            "rpm_shift": QColor(color_cfg.get("rpm_shift", "#FFC400")),
            "rpm_high": QColor(color_cfg.get("rpm_high", "#FF2438")),
            "throttle": QColor(color_cfg.get("throttle", "#50DF42")),
            "brake": QColor(color_cfg.get("brake", "#FF2438")),
            "clutch": QColor(color_cfg.get("clutch", "#29A8FF")),
            "speed": QColor(color_cfg.get("speed", "#22D3EE")),
            "steering": QColor(color_cfg.get("steering_graph", "#C084FC")),
            "throttle_reference": QColor(color_cfg.get("personal_best_throttle", "#37B9FF")),
            "brake_reference": QColor(color_cfg.get("personal_best_brake", "#FFB547")),
        }

        scale = max(0.12, min(2.5, min(bounds.width() / 1600.0, bounds.height() / 650.0)))
        radius = max(5.0, float(config.get("border_radius", 12.0)) * scale)
        self._surface(painter, bounds.adjusted(1, 1, -1, -1), outer_bg, outer_border, scale, radius)

        content = bounds.adjusted(max(7.0, 16.0 * scale), max(7.0, 16.0 * scale),
                                  -max(7.0, 16.0 * scale), -max(7.0, 16.0 * scale))
        elements = config.get("elements", {})
        show = lambda key: bool(elements.get(key, True))
        pedal_flags = config.get("pedal_elements", {})

        wheel_visible = show("steering") or show("gear") or show("speed")
        wheel_width = content.width() * (0.23 if wheel_visible else 0.0)
        pedal_count = (
            sum(bool(pedal_flags.get(key, True)) for key in ("brake", "throttle", "clutch"))
            if show("pedals") else 0
        )
        pedal_gap = max(3.0, float(config.get("pedal_bar_gap", 10.0)) * scale)
        pedal_bar_width = max(4.0, float(config.get("pedal_bar_width", 42.0)) * scale)
        pedals_width = (
            pedal_count * pedal_bar_width + (pedal_count + 1) * pedal_gap
            if pedal_count else 0.0
        )
        pedals_width = min(content.width() * 0.32, pedals_width)

        rpm_height = content.height() * (0.22 if show("rpm") else 0.0)
        column_gap = 8.0 * scale
        rpm_width = max(0.0, content.width() - wheel_width - pedals_width - column_gap * 2)
        rpm_rect = QRectF(content.left(), content.top(), rpm_width, rpm_height)
        if show("rpm") and rpm_rect.width() > 0 and rpm_rect.height() > 0:
            self._rpm(painter, rpm_rect, data, config, colors, text, muted, scale)

        gap = 8.0 * scale
        body_top = rpm_rect.bottom() + (8.0 * scale if rpm_height else 0.0)
        body = QRectF(content.left(), body_top, content.width(),
                      max(0.0, content.bottom() - body_top))
        graph_width = max(0.0, body.width() - wheel_width - pedals_width - gap * 2)
        graph_rect = QRectF(body.left(), body.top(), graph_width, body.height())
        pedals_rect = QRectF(graph_rect.right() + gap, content.top(), pedals_width, content.height())
        wheel_rect = QRectF(pedals_rect.right() + gap, content.top(), wheel_width, content.height())

        if show("graph") and graph_rect.width() > 0 and graph_rect.height() > 0:
            graph_series = {
                "throttle": throttle_history,
                "brake": brake_history,
                "clutch": clutch_history,
                "throttle_reference": reference_throttle_history,
                "brake_reference": reference_brake_history,
            }
            self._graph(painter, graph_rect, graph_series, colors, text, muted, config, scale)

        if show("pedals") and pedals_rect.width() > 0 and pedals_rect.height() > 0:
            self._pedals(painter, pedals_rect, data, colors, text, muted, config, scale)

        if wheel_visible and wheel_rect.width() > 0 and wheel_rect.height() > 0:
            self._wheel(painter, wheel_rect, data, colors, text, config, scale)

        if edit_mode:
            edit_pen = QPen(QColor(color_cfg.get("edit_border", "#8B5CF6")), max(1.5, 2.5 * scale))
            edit_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(edit_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(bounds.adjusted(3, 3, -3, -3), radius, radius)
        painter.restore()

    @staticmethod
    def _surface(
        painter: QPainter, rect: QRectF, background: QColor,
        border: QColor, scale: float, radius: float = 8.0,
    ) -> None:
        painter.setPen(QPen(border, max(0.8, 1.0 * scale)))
        painter.setBrush(background)
        painter.drawRoundedRect(rect, radius * scale, radius * scale)

    def _rpm(
        self, painter: QPainter, rect: QRectF, data: DriverPanelViewData,
        config: dict[str, Any], colors: dict[str, QColor],
        text: QColor, muted: QColor, scale: float,
    ) -> None:
        color_cfg = config.get("colors", {})
        panel = QColor(color_cfg.get("rpm_background", color_cfg.get("panel", "#080C12")))
        border = QColor(color_cfg.get("rpm_border", color_cfg.get("border", "#424B56")))
        self._surface(painter, rect, panel, border, scale, 8.0)

        ratio = max(0.0, min(1.0, data.rpm / max(1.0, data.max_rpm)))
        layout = config.get("layout", {})
        shift_at = max(0.0, min(1.0, float(layout.get("shift_start", 0.78))))
        red_at = max(shift_at, min(1.0, float(layout.get("red_start", 0.92))))

        label_rect = QRectF(rect.left() + 10 * scale, rect.top() + 2 * scale,
                            rect.width() * 0.22, rect.height() * 0.40)
        value_rect = QRectF(rect.left() + rect.width() * 0.22, rect.top() + 1 * scale,
                            rect.width() * 0.76, rect.height() * 0.43)
        painter.setFont(self._font(config, max(8.0, rect.height() * 0.25), True))
        painter.setPen(muted)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "RPM")
        value = f"{data.rpm:,.0f}".replace(",", ".")
        painter.setFont(self._fit(config, value_rect, value, rect.height() * 0.37, 9.0, True))
        painter.setPen(text)
        painter.drawText(value_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, value)

        bar = QRectF(rect.left() + 10 * scale, rect.top() + rect.height() * 0.53,
                     max(0.0, rect.width() - 20 * scale),
                     max(5.0 * scale, rect.height() * 0.30))
        track = QColor(color_cfg.get("pedal_track", "#0C1720"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(bar, 4 * scale, 4 * scale)

        segments = max(10, min(60, int(layout.get("rpm_segments", 28))))
        segment_gap = max(1.0, 2.0 * scale)
        segment_width = max(0.5, (bar.width() - segment_gap * (segments - 1)) / segments)
        for index in range(segments):
            start_ratio = index / segments
            end_ratio = (index + 1) / segments
            left = bar.left() + index * (segment_width + segment_gap)
            segment = QRectF(left, bar.top(), segment_width, bar.height())
            if end_ratio <= shift_at:
                active_color = colors["rpm_low"]
            elif end_ratio <= red_at:
                active_color = colors["rpm_shift"]
            else:
                active_color = colors["rpm_high"]
            painter.setBrush(track)
            painter.drawRoundedRect(segment, 2 * scale, 2 * scale)
            filled_fraction = max(0.0, min(1.0, (ratio - start_ratio) * segments))
            if filled_fraction > 0.0:
                filled = QRectF(segment.left(), segment.top(),
                                segment.width() * filled_fraction, segment.height())
                painter.setBrush(active_color)
                painter.drawRoundedRect(filled, 2 * scale, 2 * scale)

        for threshold, threshold_color in (
            (shift_at, colors["rpm_shift"]),
            (red_at, colors["rpm_high"]),
        ):
            x = bar.left() + bar.width() * threshold
            painter.setPen(QPen(threshold_color, max(1.0, 1.4 * scale)))
            painter.drawLine(QPointF(x, bar.top() - 2 * scale),
                             QPointF(x, bar.bottom() + 2 * scale))

    def _graph(
        self, painter: QPainter, rect: QRectF,
        series: dict[str, Sequence[float]], colors: dict[str, QColor],
        text: QColor, muted: QColor, config: dict[str, Any], scale: float,
    ) -> None:
        color_cfg = config.get("colors", {})
        panel = QColor(color_cfg.get("graph_background", color_cfg.get("panel", "#080C12")))
        border = QColor(color_cfg.get("graph_border", color_cfg.get("border", "#424B56")))
        self._surface(painter, rect, panel, border, scale, 8.0)

        title_rect = QRectF(rect.left() + 10 * scale, rect.top() + 3 * scale,
                            rect.width() - 20 * scale, 14 * scale)
        painter.setFont(self._font(config, max(7.0, 9.0 * scale), True))
        painter.setPen(muted)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         tr("PEDAL INPUT"))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         tr("LIVE"))

        graph = rect.adjusted(36 * scale, 21 * scale, -9 * scale, -19 * scale)
        if graph.width() <= 4 or graph.height() <= 4:
            return

        if bool(config.get("graph_show_grid", True)):
            grid = QColor(color_cfg.get("grid", "#27313E"))
            grid_pen = QPen(grid, max(0.6, 0.8 * scale))
            grid_pen.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(grid_pen)
            for index in range(5):
                y = graph.bottom() - graph.height() * index / 4
                painter.drawLine(QPointF(graph.left(), y), QPointF(graph.right(), y))
            vertical_count = max(2, min(20, int(config.get("graph_vertical_lines", 8))))
            for index in range(vertical_count + 1):
                x = graph.left() + graph.width() * index / vertical_count
                painter.drawLine(QPointF(x, graph.top()), QPointF(x, graph.bottom()))

        painter.setFont(self._font(config, max(6.5, 8.0 * scale), False))
        painter.setPen(muted)
        for percent in (100, 75, 50, 25, 0):
            y = graph.bottom() - graph.height() * percent / 100.0
            label_rect = QRectF(rect.left() + 2 * scale, y - 5 * scale,
                                29 * scale, 10 * scale)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             f"{percent}%")

        painter.setFont(self._font(config, max(6.5, 7.5 * scale), False))
        painter.setPen(muted)
        painter.drawText(
            QRectF(graph.left(), graph.bottom() + 2 * scale, graph.width() * 0.5, 12 * scale),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tr("HISTÓRICO"),
        )
        painter.drawText(
            QRectF(graph.left() + graph.width() * 0.5, graph.bottom() + 2 * scale,
                   graph.width() * 0.5, 12 * scale),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, tr("AGORA"),
        )

        enabled = config.get("pedal_elements", {})
        painter.save()
        painter.setClipRect(graph)
        glow = bool(config.get("graph_curve_glow", True))
        for name, values in series.items():
            base_name = name.removesuffix("_reference")
            if not bool(enabled.get(base_name, True)):
                continue
            if name.endswith("_reference"):
                width = float(config.get("reference_line_width", 2.0))
                dashed = True
            else:
                width = float(config.get(
                    f"{base_name}_line_width",
                    config.get("graph_line_width", 3.6),
                ))
                dashed = False
            self._draw_curve(
                painter, graph, values, colors[name],
                max(1.0, min(9.0, width * scale)), dashed, glow and not dashed,
            )
        painter.restore()

        if series.get("throttle_reference") or series.get("brake_reference"):
            legend_rect = QRectF(graph.right() - 88 * scale, graph.top() + 2 * scale,
                                 84 * scale, 12 * scale)
            painter.setFont(self._font(config, max(6.5, 7.0 * scale), False))
            painter.setPen(muted)
            painter.drawText(legend_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             tr("PB tracejada"))

    @staticmethod
    def _draw_curve(
        painter: QPainter, rect: QRectF, values: Sequence[float],
        color: QColor, width: float, dashed: bool = False, glow: bool = False,
    ) -> None:
        if len(values) < 2:
            return
        path = QPainterPath()
        for index, raw in enumerate(values):
            if isinstance(raw, (tuple, list)) and len(raw) >= 2:
                x_ratio, value = float(raw[0]), float(raw[1])
            else:
                x_ratio, value = index / (len(values) - 1), float(raw)
            x_ratio = max(0.0, min(1.0, x_ratio))
            value = max(0.0, min(1.0, value))
            point = QPointF(
                rect.left() + rect.width() * x_ratio,
                rect.bottom() - rect.height() * value,
            )
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)

        if glow and not dashed:
            glow_color = QColor(color)
            glow_color.setAlpha(48)
            glow_pen = QPen(glow_color, width * 2.4)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def _pedals(
        self, painter: QPainter, rect: QRectF, data: DriverPanelViewData,
        colors: dict[str, QColor], text: QColor, muted: QColor,
        config: dict[str, Any], scale: float,
    ) -> None:
        color_cfg = config.get("colors", {})
        panel = QColor(color_cfg.get("pedals_background", color_cfg.get("panel", "#080C12")))
        border = QColor(color_cfg.get("pedals_border", color_cfg.get("border", "#424B56")))
        self._surface(painter, rect, panel, border, scale, 8.0)

        pedal_flags = config.get("pedal_elements", {})
        items = [
            ("BRK", data.brake, data.max_brake_seen, "brake", data.brake_abrupt),
            ("THR", data.throttle, data.max_throttle_seen, "throttle", data.throttle_abrupt),
            ("CLT", data.clutch, data.max_clutch_seen, "clutch", False),
        ]
        items = [item for item in items if bool(pedal_flags.get(item[3], True))]
        if not items:
            return

        gap = max(3.0, float(config.get("pedal_bar_gap", 10.0)) * scale)
        bar_width = min(
            max(4.0, float(config.get("pedal_bar_width", 42.0)) * scale),
            max(4.0, (rect.width() - gap * (len(items) + 1)) / len(items)),
        )
        group_width = len(items) * bar_width + (len(items) - 1) * gap
        start_x = rect.center().x() - group_width / 2
        show_labels = bool(config.get("pedal_show_labels", True))
        show_peaks = bool(config.get("pedal_show_peaks", True))
        label_height = 13.0 * scale if show_labels else 4.0 * scale
        value_height = max(22.0 * scale, rect.height() * 0.16)
        bar_top = rect.top() + value_height + 3.0 * scale
        bar_bottom = rect.bottom() - label_height - 7.0 * scale
        track_color = QColor(color_cfg.get("pedal_track", "#0C1720"))
        tick_color = QColor(color_cfg.get("grid", "#27313E"))

        for index, (short_label, value, maximum, key, alert) in enumerate(items):
            x = start_x + index * (bar_width + gap)
            percent = f"{value * 100:.0f}%"
            percent_rect = QRectF(x - 2 * scale, rect.top() + 2 * scale,
                                  bar_width + 4 * scale, value_height - 3 * scale)
            painter.setFont(self._fit(config, percent_rect, percent,
                                      max(12.0 * scale, value_height * 0.42), 7.5, True))
            painter.setPen(colors[key])
            painter.drawText(percent_rect, Qt.AlignmentFlag.AlignCenter, percent)

            bar = QRectF(x, bar_top, bar_width, max(6.0 * scale, bar_bottom - bar_top))
            painter.setPen(QPen(colors[key].darker(160), max(0.8, 1.0 * scale)))
            painter.setBrush(track_color)
            painter.drawRoundedRect(bar, 4.0 * scale, 4.0 * scale)

            painter.save()
            painter.setClipRect(bar.adjusted(1, 1, -1, -1))
            for tick in (0.25, 0.50, 0.75):
                tick_y = bar.bottom() - bar.height() * tick
                painter.setPen(QPen(tick_color, max(0.6, 0.8 * scale)))
                painter.drawLine(QPointF(bar.left() + 1, tick_y),
                                 QPointF(bar.right() - 1, tick_y))
            fill_height = max(0.0, min(1.0, value)) * bar.height()
            if fill_height > 0.0:
                fill = QRectF(bar.left(), bar.bottom() - fill_height,
                              bar.width(), fill_height)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(colors[key])
                painter.drawRoundedRect(fill, 4.0 * scale, 4.0 * scale)
            if show_peaks and maximum > 0.0:
                peak_y = bar.bottom() - bar.height() * max(0.0, min(1.0, maximum))
                painter.setPen(QPen(text, max(1.0, 1.2 * scale)))
                painter.drawLine(QPointF(bar.left() - 2 * scale, peak_y),
                                 QPointF(bar.right() + 2 * scale, peak_y))
            painter.restore()

            if alert:
                painter.setPen(QPen(colors[key], max(1.0, 1.3 * scale)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(percent_rect.adjusted(1, 1, -1, -1),
                                        3 * scale, 3 * scale)

            if show_labels:
                label_rect = QRectF(x - 2 * scale, rect.bottom() - label_height - 3 * scale,
                                    bar_width + 4 * scale, label_height)
                painter.setFont(self._font(config, max(6.5, 8.0 * scale), True))
                painter.setPen(muted)
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, tr(short_label))

    def _wheel(
        self, painter: QPainter, rect: QRectF, data: DriverPanelViewData,
        colors: dict[str, QColor], text: QColor, config: dict[str, Any], scale: float,
    ) -> None:
        color_cfg = config.get("colors", {})
        panel = QColor(color_cfg.get("steering_background", color_cfg.get("panel", "#080C12")))
        border = QColor(color_cfg.get("steering_border", color_cfg.get("border", "#424B56")))
        self._surface(painter, rect, panel, border, scale, 8.0)

        wheel_scale = max(0.35, min(2.0, float(config.get("steering_size_scale", 1.0))))
        base_radius = max(8.0, min(rect.width() * 0.378, rect.height() * 0.243))
        center = QPointF(rect.center().x(), rect.top() + rect.height() * 0.34)
        radius = base_radius * wheel_scale
        angle = data.steering * float(config.get("steering_visual_degrees", 540))
        elements = config.get("elements", {})
        style = str(config.get("steering_style", "Circular"))
        marker_color = QColor(color_cfg.get("steering_marker", "#4CFF5E"))

        if bool(elements.get("steering", True)):
            custom_image = str(config.get("custom_wheel_image", "")).strip()
            painter.save()
            painter.translate(center)
            painter.rotate(angle)
            if style == "Imagem personalizada" and custom_image and Path(custom_image).is_file():
                painter.drawImage(QRectF(-radius, -radius, radius * 2, radius * 2),
                                  QImage(custom_image))
            elif style != "Somente ângulo":
                wheel_color = QColor(color_cfg.get("wheel", "#445466"))
                painter.setPen(QPen(wheel_color, max(4.0, radius * 0.13)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                if style == "GT":
                    painter.drawRoundedRect(
                        QRectF(-radius, -radius * 0.78, radius * 2, radius * 1.56),
                        radius * 0.28, radius * 0.28,
                    )
                elif style == "Fórmula":
                    painter.drawRoundedRect(
                        QRectF(-radius, -radius * 0.62, radius * 2, radius * 1.24),
                        radius * 0.16, radius * 0.16,
                    )
                else:
                    painter.drawEllipse(QPointF(0, 0), radius, radius)
                    painter.drawLine(QPointF(0, -radius * 0.82), QPointF(0, -radius * 0.32))
                    painter.drawLine(QPointF(-radius * 0.72, radius * 0.42),
                                     QPointF(-radius * 0.22, radius * 0.12))
                    painter.drawLine(QPointF(radius * 0.72, radius * 0.42),
                                     QPointF(radius * 0.22, radius * 0.12))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(color_cfg.get("steering_center", "#FFFFFF")))
                painter.drawEllipse(QPointF(0, 0), max(2.5, radius * 0.07),
                                    max(2.5, radius * 0.07))
            painter.restore()

            if bool(elements.get("steering_marker", True)):
                marker_angle = angle * math.pi / 180.0
                marker = QPointF(
                    center.x() + radius * math.sin(marker_angle),
                    center.y() - radius * math.cos(marker_angle),
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(marker_color)
                painter.drawEllipse(marker, max(4.0, radius * 0.105),
                                    max(4.0, radius * 0.105))

        rpm_ratio = data.rpm / max(1.0, data.max_rpm)
        gear_color = (
            QColor("#FFFFFF") if data.gear_flash
            else QColor(color_cfg.get("rpm_high", "#FF2438"))
            if rpm_ratio >= float(config.get("layout", {}).get("red_start", 0.92))
            else QColor(color_cfg.get("rpm_shift", "#FFC400"))
        )

        if bool(elements.get("gear", True)):
            gear_scale = max(0.35, min(3.0, float(config.get("gear_font_scale", 1.0))))
            gear = self._format_gear(data.gear)
            gear_rect = QRectF(
                rect.left(), center.y() + radius * 1.12, rect.width(),
                max(base_radius * 1.02, 42.0 * scale * gear_scale),
            )
            painter.setFont(self._fit(config, gear_rect, gear,
                                      base_radius * 0.92 * gear_scale, 8.0, True))
            painter.setPen(gear_color)
            painter.drawText(gear_rect, Qt.AlignmentFlag.AlignCenter, gear)

        if bool(elements.get("speed", True)):
            speed_scale = max(0.35, min(3.0, float(config.get("speed_font_scale", 1.0))))
            unit = str(config.get("speed_unit", "km/h"))
            speed_value = data.speed_kmh * 0.621371 if unit == "mph" else data.speed_kmh
            speed_text = f"{speed_value:.0f}"
            if str(config.get("speed_position", "inside")) == "beside_gear":
                speed_rect = QRectF(
                    center.x() + radius * 0.38, center.y() + radius * 1.12,
                    max(1.0, rect.right() - center.x() - radius * 0.38), radius * 1.02,
                )
                alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            else:
                speed_rect = QRectF(
                    center.x() - radius * 0.90, center.y() - radius * 0.52,
                    radius * 1.80, radius * 1.04,
                )
                alignment = Qt.AlignmentFlag.AlignCenter
            painter.setFont(self._fit(config, speed_rect, speed_text,
                                      base_radius * 0.59 * speed_scale, 7.0, True))
            painter.setPen(text)
            painter.drawText(speed_rect, alignment, speed_text)

    @staticmethod
    def _font(config: dict[str, Any], pixels: float, bold: bool = False) -> QFont:
        font_config = config.get("font", {})
        family = str(font_config.get("family", "Bahnschrift Light"))
        font_scale = max(0.65, min(1.8, float(font_config.get("scale", 1.0))))
        font = QFont(family)
        font.setPixelSize(max(7, int(pixels * font_scale)))
        font.setBold(bold)
        return font

    def _fit(
        self, config: dict[str, Any], rect: QRectF, value: str,
        preferred: float, minimum: float, bold: bool = False,
    ) -> QFont:
        size = max(minimum, preferred)
        while size > minimum:
            font = self._font(config, size, bold)
            if QFontMetricsF(font).horizontalAdvance(value) <= rect.width() * 0.88:
                return font
            size -= 1
        return self._font(config, minimum, bold)

    @staticmethod
    def _format_gear(gear: int) -> str:
        return "R" if gear < 0 else "N" if gear == 0 else str(gear)
