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
    rpm_flash_phase: bool = False


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
            "rpm_low": QColor(color_cfg.get("rpm_low", "#258DFF")),
            "rpm_shift": QColor(color_cfg.get("rpm_shift", "#FFC400")),
            "rpm_high": QColor(color_cfg.get("rpm_high", "#FF2438")),
            "rpm_green": QColor(color_cfg.get("rpm_green", "#2BD158")),
            "rpm_blue": QColor(color_cfg.get("rpm_blue", "#258DFF")),
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

        wheel_visible = show("steering") or show("speed")
        pedal_count = (
            sum(bool(pedal_flags.get(key, True)) for key in ("brake", "throttle", "clutch"))
            if show("pedals") else 0
        )

        rpm_height = content.height() * (0.25 if show("rpm") else 0.0)
        rpm_rect = QRectF(content.left(), content.top(), content.width(), rpm_height)
        if show("rpm") and rpm_rect.width() > 0 and rpm_rect.height() > 0:
            self._rpm(painter, rpm_rect, data, config, colors, text, muted, scale)

        gap = max(4.0, 8.0 * scale)
        body_top = rpm_rect.bottom() + (gap if rpm_height else 0.0)
        body = QRectF(
            content.left(), body_top, content.width(),
            max(0.0, content.bottom() - body_top),
        )

        # Proporções da referência: gráfico, pedais, marcha e velocímetro.
        sections: list[tuple[str, float]] = []
        if show("graph"):
            sections.append(("graph", 0.42))
        if show("pedals") and pedal_count:
            sections.append(("pedals", 0.18))
        if show("gear"):
            sections.append(("gear", 0.14))
        if wheel_visible:
            sections.append(("wheel", 0.22))

        section_rects: dict[str, QRectF] = {}
        if sections and body.width() > 0:
            available_width = max(0.0, body.width() - gap * (len(sections) - 1))
            total_weight = sum(weight for _, weight in sections)
            cursor_x = body.left()
            for name, weight in sections:
                section_width = available_width * weight / total_weight
                section_rects[name] = QRectF(
                    cursor_x, body.top(), section_width, body.height()
                )
                cursor_x += section_width + gap

        if "graph" in section_rects:
            graph_series = {
                "throttle": throttle_history,
                "brake": brake_history,
                "clutch": clutch_history,
                "throttle_reference": reference_throttle_history,
                "brake_reference": reference_brake_history,
            }
            self._graph(
                painter, section_rects["graph"], graph_series, colors,
                text, muted, config, scale,
            )

        if "pedals" in section_rects:
            self._pedals(
                painter, section_rects["pedals"], data, colors,
                text, muted, config, scale,
            )

        if "gear" in section_rects:
            self._gear(
                painter, section_rects["gear"], data, config, scale
            )

        if "wheel" in section_rects:
            self._wheel(
                painter, section_rects["wheel"], data, colors,
                text, config, scale,
            )

        if edit_mode:
            edit_pen = QPen(QColor(color_cfg.get("edit_border", "#8B5CF6")), max(1.5, 2.5 * scale))
            edit_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(edit_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(bounds.adjusted(3, 3, -3, -3))
        painter.restore()

    @staticmethod
    def _surface(
        painter: QPainter, rect: QRectF, background: QColor,
        border: QColor, scale: float, radius: float = 8.0,
    ) -> None:
        painter.setPen(QPen(border, max(0.8, 1.0 * scale)))
        painter.setBrush(background)
        painter.drawRect(rect)

    def _rpm(
        self, painter: QPainter, rect: QRectF, data: DriverPanelViewData,
        config: dict[str, Any], colors: dict[str, QColor],
        text: QColor, muted: QColor, scale: float,
    ) -> None:
        del muted
        color_cfg = config.get("colors", {})
        panel = QColor(color_cfg.get("rpm_background", "#000000"))
        border = QColor(color_cfg.get("rpm_border", "#000000"))
        self._surface(painter, rect, panel, border, scale, 0.0)

        ratio = max(0.0, min(1.0, data.rpm / max(1.0, data.max_rpm)))
        layout = config.get("layout", {})
        shift_at = max(0.0, min(1.0, float(layout.get("shift_start", 0.78))))
        red_at = max(shift_at, min(1.0, float(layout.get("red_start", 0.92))))

        bar = QRectF(
            rect.left() + 10.0 * scale,
            rect.top() + rect.height() * 0.70,
            max(0.0, rect.width() - 20.0 * scale),
            max(5.0 * scale, rect.height() * 0.20),
        )
        green = QColor(color_cfg.get("rpm_green", "#2BD158"))
        yellow = QColor(color_cfg.get("rpm_yellow", color_cfg.get("rpm_shift", "#FFC400")))
        blue = QColor(color_cfg.get("rpm_blue", color_cfg.get("rpm_low", "#258DFF")))
        red = QColor(color_cfg.get("rpm_high", "#FF2438"))
        purple = QColor(color_cfg.get("rpm_flash", "#9B5CFF"))
        flash_color = purple if data.rpm_flash_phase else red

        # A sequência espelhada é fixa: verde nas pontas, amarelo no meio
        # externo e azul no centro. O preenchimento cresce do centro para fora.
        cell_colors = [
            green, green, yellow, yellow, blue,
            blue, yellow, yellow, green, green,
        ]
        block_count = 10
        block_gap = max(2.0, 4.0 * scale)
        block_width = max(
            1.0,
            (bar.width() - block_gap * (block_count - 1)) / block_count,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        for index, base_color in enumerate(cell_colors):
            cell = QRectF(
                bar.left() + index * (block_width + block_gap),
                bar.top(), block_width, bar.height(),
            )
            pair_level = 5 - min(index, block_count - 1 - index)
            active = ratio + 1e-9 >= pair_level / 5.0
            painter.setBrush(flash_color if ratio >= red_at and active else base_color if active else QColor("#171717"))
            painter.drawRect(cell)

        # Pequena aba central para as três shift lights.
        cap_width = min(132.0 * scale, rect.width() * 0.25)
        cap_height = max(18.0 * scale, rect.height() * 0.31)
        cap = QRectF(
            rect.center().x() - cap_width / 2.0,
            rect.top() + 1.0 * scale,
            cap_width, cap_height,
        )
        cap_bg = QColor(color_cfg.get("rpm_value_background", "#050505"))
        cap_border = QColor(color_cfg.get("rpm_value_border", "#292929"))
        painter.setPen(QPen(cap_border, max(0.8, 1.0 * scale)))
        painter.setBrush(cap_bg)
        painter.drawRect(cap)

        light_width = max(8.0 * scale, min(18.0 * scale, cap_width * 0.16))
        light_height = max(2.5 * scale, rect.height() * 0.045)
        light_gap = max(2.0 * scale, 3.0 * scale)
        lights_width = light_width * 3 + light_gap * 2
        light_start = cap.center().x() - lights_width / 2.0
        light_y = cap.top() + max(3.0 * scale, cap.height() * 0.16)
        light_thresholds = (
            shift_at,
            shift_at + (red_at - shift_at) * 0.35,
            shift_at + (red_at - shift_at) * 0.70,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        for index, threshold in enumerate(light_thresholds):
            light = QRectF(
                light_start + index * (light_width + light_gap),
                light_y, light_width, light_height,
            )
            painter.setBrush(red if ratio >= threshold else QColor("#3A1014"))
            painter.drawRect(light)

        # Caixa numérica independente que acompanha a posição atual do RPM.
        value = f"{data.rpm:,.0f} RPM".replace(",", ".")
        value_font = self._font(config, max(8.0, rect.height() * 0.24), True)
        metrics = QFontMetricsF(value_font)
        badge_height = max(12.0 * scale, rect.height() * 0.22)
        badge_width = min(
            max(58.0 * scale, metrics.horizontalAdvance(value) + 12.0 * scale),
            max(1.0, rect.width() - 12.0 * scale),
        )
        marker_x = bar.left() + bar.width() * ratio
        badge_x = max(
            rect.left() + 6.0 * scale,
            min(rect.right() - badge_width - 6.0 * scale, marker_x - badge_width / 2.0),
        )
        badge = QRectF(
            badge_x,
            rect.top() + rect.height() * 0.39,
            badge_width,
            badge_height,
        )
        self._surface(painter, badge, cap_bg, cap_border, scale, 3.0)
        painter.setFont(self._fit(config, badge, value, rect.height() * 0.22, 7.0, True))
        painter.setPen(text)
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, value)

    def _graph(
        self, painter: QPainter, rect: QRectF,
        series: dict[str, Sequence[float]], colors: dict[str, QColor],
        text: QColor, muted: QColor, config: dict[str, Any], scale: float,
    ) -> None:
        color_cfg = config.get("colors", {})
        panel = QColor(color_cfg.get("graph_background", "#000000"))
        border = QColor(color_cfg.get("graph_border", "#000000"))
        self._surface(painter, rect, panel, border, scale, 0.0)

        graph = rect.adjusted(5.0 * scale, 7.0 * scale, -5.0 * scale, -7.0 * scale)
        if graph.width() <= 4 or graph.height() <= 4:
            return

        if bool(config.get("graph_show_grid", False)):
            grid = QColor(color_cfg.get("grid", "#242424"))
            grid_pen = QPen(grid, max(0.5, 0.65 * scale))
            grid_pen.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(grid_pen)
            for index in range(1, 4):
                y = graph.bottom() - graph.height() * index / 4
                painter.drawLine(QPointF(graph.left(), y), QPointF(graph.right(), y))
            vertical_count = max(2, min(20, int(config.get("graph_vertical_lines", 8))))
            for index in range(1, vertical_count):
                x = graph.left() + graph.width() * index / vertical_count
                painter.drawLine(QPointF(x, graph.top()), QPointF(x, graph.bottom()))

        # Linha horizontal fina que representa o topo da escala (100%).
        reference = QColor(color_cfg.get("graph_reference", "#AAB2BD"))
        painter.setPen(QPen(reference, max(0.6, 0.8 * scale)))
        painter.drawLine(QPointF(graph.left(), graph.top()), QPointF(graph.right(), graph.top()))

        if bool(config.get("graph_show_scale_labels", False)):
            painter.setFont(self._font(config, max(6.5, 8.0 * scale), False))
            painter.setPen(muted)
            for percent in (100, 75, 50, 25, 0):
                y = graph.bottom() - graph.height() * percent / 100.0
                label_rect = QRectF(rect.left(), y - 5 * scale, 25 * scale, 10 * scale)
                painter.drawText(
                    label_rect,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    f"{percent}",
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

        # Dois pequenos pontos amarelos assinalam os extremos recentes do acelerador.
        throttle_values = series.get("throttle", ())
        if bool(config.get("graph_extrema_markers", True)) and len(throttle_values) >= 2:
            normalized: list[tuple[float, float]] = []
            for index, raw in enumerate(throttle_values):
                if isinstance(raw, (tuple, list)) and len(raw) >= 2:
                    x_ratio, value = float(raw[0]), float(raw[1])
                else:
                    x_ratio, value = index / (len(throttle_values) - 1), float(raw)
                normalized.append((
                    max(0.0, min(1.0, x_ratio)),
                    max(0.0, min(1.0, value)),
                ))
            min_index = min(range(len(normalized)), key=lambda i: normalized[i][1])
            max_index = max(range(len(normalized)), key=lambda i: normalized[i][1])
            marker_indices = {min_index, max_index}
            painter.save()
            painter.setClipRect(graph)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color_cfg.get("graph_marker", "#FFD21F")))
            marker_radius = max(2.0, 3.2 * scale)
            for index in marker_indices:
                x_ratio, value = normalized[index]
                point = QPointF(
                    graph.left() + graph.width() * x_ratio,
                    graph.bottom() - graph.height() * value,
                )
                painter.drawEllipse(point, marker_radius, marker_radius)
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
        del muted
        color_cfg = config.get("colors", {})
        panel = QColor(color_cfg.get("pedals_background", "#000000"))
        border = QColor(color_cfg.get("pedals_border", "#000000"))
        self._surface(painter, rect, panel, border, scale, 0.0)

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
            max(4.0, float(config.get("pedal_bar_width", 38.0)) * scale),
            max(4.0, (rect.width() - gap * (len(items) + 1)) / len(items)),
        )
        group_width = len(items) * bar_width + (len(items) - 1) * gap
        start_x = rect.center().x() - group_width / 2.0
        value_height = max(20.0 * scale, rect.height() * 0.17)
        bar_top = rect.top() + value_height + 4.0 * scale
        bar_bottom = rect.bottom() - 5.0 * scale
        track_color = QColor(color_cfg.get("pedal_track", "#292929"))

        for index, (_short_label, value, maximum, key, alert) in enumerate(items):
            x = start_x + index * (bar_width + gap)
            value_text = f"{value * 100:.0f}"
            value_rect = QRectF(
                x - 3.0 * scale, rect.top() + 1.0 * scale,
                bar_width + 6.0 * scale, value_height - 2.0 * scale,
            )
            painter.setFont(self._fit(
                config, value_rect, value_text,
                max(12.0 * scale, value_height * 0.56), 7.5, True,
            ))
            painter.setPen(text)
            painter.drawText(value_rect, Qt.AlignmentFlag.AlignCenter, value_text)

            bar = QRectF(
                x, bar_top, bar_width,
                max(6.0 * scale, bar_bottom - bar_top),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(track_color)
            painter.drawRect(bar)

            fill_height = max(0.0, min(1.0, value)) * bar.height()
            if fill_height > 0.0:
                fill = QRectF(
                    bar.left(), bar.bottom() - fill_height,
                    bar.width(), fill_height,
                )
                painter.setBrush(colors[key])
                painter.drawRect(fill)

            if bool(config.get("pedal_show_peaks", False)) and maximum > 0.0:
                peak_y = bar.bottom() - bar.height() * max(0.0, min(1.0, maximum))
                painter.setPen(QPen(text, max(1.0, 1.2 * scale)))
                painter.drawLine(
                    QPointF(bar.left() - 2 * scale, peak_y),
                    QPointF(bar.right() + 2 * scale, peak_y),
                )
            if alert:
                painter.setPen(QPen(colors[key], max(1.0, 1.3 * scale)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(value_rect.adjusted(1, 1, -1, -1))

    def _gear(
        self, painter: QPainter, rect: QRectF, data: DriverPanelViewData,
        config: dict[str, Any], scale: float,
    ) -> None:
        gear = self._format_gear(data.gear)
        gear_color = QColor(
            "#FFFFFF" if data.gear_flash
            else config.get("colors", {}).get("gear", "#FFD21F")
        )
        gear_scale = max(0.35, min(3.0, float(config.get("gear_font_scale", 1.0))))
        gear_rect = rect.adjusted(3.0 * scale, 2.0 * scale, -3.0 * scale, -2.0 * scale)
        preferred = min(rect.height() * 0.68, rect.width() * 0.88) * gear_scale
        painter.setFont(self._fit(config, gear_rect, gear, preferred, 9.0, True))
        painter.setPen(gear_color)
        painter.drawText(gear_rect, Qt.AlignmentFlag.AlignCenter, gear)

    def _wheel(
        self, painter: QPainter, rect: QRectF, data: DriverPanelViewData,
        colors: dict[str, QColor], text: QColor, config: dict[str, Any], scale: float,
    ) -> None:
        elements = config.get("elements", {})
        center = QPointF(rect.center().x(), rect.center().y())
        wheel_scale = max(0.35, min(2.0, float(config.get("steering_size_scale", 1.0))))
        radius = max(
            7.0 * scale,
            min(rect.width() * 0.39, rect.height() * 0.43) * wheel_scale,
        )

        if bool(elements.get("steering", True)):
            ring_color = QColor(config.get("colors", {}).get("wheel", "#292929"))
            painter.setPen(QPen(ring_color, max(1.2, 2.0 * scale)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, radius, radius)

            if bool(elements.get("steering_marker", True)):
                angle = math.radians(
                    data.steering * float(config.get("steering_visual_degrees", 180))
                )
                marker_center = QPointF(
                    center.x() + radius * math.sin(angle),
                    center.y() - radius * math.cos(angle),
                )
                marker_width = max(9.0 * scale, radius * 0.30)
                marker_height = max(3.5 * scale, radius * 0.105)
                marker = QRectF(
                    marker_center.x() - marker_width / 2.0,
                    marker_center.y() - marker_height / 2.0,
                    marker_width, marker_height,
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(config.get("colors", {}).get("steering_marker", "#FFD21F")))
                painter.drawRoundedRect(marker, marker_height / 2.0, marker_height / 2.0)

        if bool(elements.get("speed", True)):
            unit = str(config.get("speed_unit", "km/h"))
            speed_value = data.speed_kmh * 0.621371 if unit == "mph" else data.speed_kmh
            speed_text = f"{speed_value:.0f}"
            speed_scale = max(0.35, min(3.0, float(config.get("speed_font_scale", 1.0))))
            speed_rect = QRectF(
                center.x() - radius * 0.82,
                center.y() - radius * 0.52,
                radius * 1.64,
                radius * 1.04,
            )
            preferred = radius * 0.62 * speed_scale
            painter.setFont(self._fit(config, speed_rect, speed_text, preferred, 8.0, True))
            painter.setPen(text)
            painter.drawText(speed_rect, Qt.AlignmentFlag.AlignCenter, speed_text)

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
