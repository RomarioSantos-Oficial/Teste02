
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
)

from .delta_layout import DeltaLayoutEngine
from .delta_logo_manager import DeltaLogoManager
from .delta_models import (
    DeltaSectorData,
    DeltaViewData,
    FastestLapData,
    SECTOR_BETTER,
    SECTOR_SESSION_BEST,
    SECTOR_WORSE,
)
from src.widget.standings.standings_assets import CountryFlagStore, flag_emoji


class DeltaRenderer:
    def __init__(self, logo_manager: DeltaLogoManager) -> None:
        self.logo_manager = logo_manager
        self.layout_engine = DeltaLayoutEngine()
        self.flag_store = CountryFlagStore(
            logo_manager.project_root,
            {
                "use_flag_images": True,
                "flag_cache_directory": "data/flags",
                "flag_provider_url": CountryFlagStore.DEFAULT_URL,
            },
        )

    def preferred_height(
        self,
        width: int,
        config: dict[str, Any],
        fastest_count: int,
        sectors_visible: bool = False,
    ) -> int:
        layout_config = self._sector_layout_config(config, sectors_visible)
        return self.layout_engine.preferred_height(
            width,
            layout_config,
            fastest_count,
        )

    def draw(
        self,
        painter: QPainter,
        bounds: QRectF,
        data: DeltaViewData,
        delta_history: Sequence[float],
        config: dict[str, Any],
        edit_mode: bool = False,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform,
            True,
        )

        colors = config.get("colors", {})
        background = QColor(colors.get("background", "#090D12"))
        border = QColor(colors.get("border", "#2A3540"))
        background.setAlphaF(
            float(config.get("background_opacity", 0.86))
        )

        fastest_laps = list(data.fastest_laps)
        if not fastest_laps and data.fastest_lap is not None:
            fastest_laps = [data.fastest_lap]
        fastest_count = (
            len(fastest_laps)
            if data.fastest_alpha > 0.001
            else 0
        )
        layout = self.layout_engine.build(
            bounds,
            self._sector_layout_config(config, data.sector_visible),
            fastest_count,
        )
        scale = max(
            0.35,
            min(2.5, bounds.width() / 1200.0),
        )
        radius = max(
            4.0,
            float(config.get("border_radius", 12)) * scale,
        )

        if self._draw_outer_background(config):
            frame_rect = layout.outer.adjusted(
                -max(4.0, 8.0 * scale),
                -max(4.0, 8.0 * scale),
                max(4.0, 8.0 * scale),
                max(4.0, 8.0 * scale),
            )
            painter.setPen(
                QPen(
                    border,
                    max(1.0, 1.5 * scale),
                )
            )
            painter.setBrush(background)
            painter.drawRoundedRect(
                frame_rect,
                radius,
                radius,
            )

        if layout.header is not None:
            self._draw_header(
                painter,
                layout.header,
                data,
                config,
                scale,
            )

        self._draw_delta_bar(
            painter,
            layout.delta_bar,
            data.delta_s,
            config,
            scale,
        )

        if layout.history is not None:
            self._draw_history(
                painter,
                layout.history,
                delta_history,
                config,
                scale,
            )

        if (
            layout.fastest is not None
            and fastest_laps
        ):
            painter.save()
            painter.setOpacity(
                max(0.0, min(1.0, data.fastest_alpha))
            )
            self._draw_fastest_laps(
                painter,
                layout.fastest,
                fastest_laps,
                config,
                scale,
            )
            painter.restore()

        if layout.sectors is not None:
            self._draw_sectors(
                painter,
                layout.sectors,
                data.sectors,
                config,
                scale,
            )

        if edit_mode:
            edit = QColor(colors.get("edit_border", "#9B5CFF"))
            pen = QPen(edit, max(1.2, 2.0 * scale))
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            frame_rect = layout.outer.adjusted(
                -max(4.0, 8.0 * scale),
                -max(4.0, 8.0 * scale),
                max(4.0, 8.0 * scale),
                max(4.0, 8.0 * scale),
            )
            painter.drawRoundedRect(
                frame_rect,
                radius,
                radius,
            )

        painter.restore()

    @staticmethod
    def _draw_outer_background(config: dict[str, Any]) -> bool:
        mode = str(
            config.get(
                "background_mode",
                "sections",
            )
        ).strip().lower()

        if mode == "group":
            return bool(config.get("background_enabled", True))

        return False

    @staticmethod
    def _draw_section_panel(
        painter: QPainter,
        rect: QRectF,
        config: dict[str, Any],
        section: str,
        scale: float,
        fallback_background: str,
        fallback_border: str,
        fallback_radius: float,
    ) -> None:
        styles = config.get("section_styles", {})
        style = styles.get(section, {}) if isinstance(styles, dict) else {}
        if not isinstance(style, dict):
            style = {}
        if not bool(style.get("enabled", True)):
            return

        background = QColor(str(style.get("background", fallback_background)))
        opacity = max(0.0, min(1.0, float(style.get("opacity", 1.0))))
        background.setAlphaF(background.alphaF() * opacity)

        border_enabled = bool(style.get("border_enabled", True))
        border_width = max(0.0, float(style.get("border_width", 0.8))) * scale
        if border_enabled and border_width > 0.0:
            border = QColor(str(style.get("border", fallback_border)))
            painter.setPen(QPen(border, border_width))
        else:
            painter.setPen(Qt.PenStyle.NoPen)

        painter.setBrush(background)
        radius = max(0.0, float(style.get("radius", fallback_radius)) * scale)
        painter.drawRoundedRect(rect, radius, radius)

    def _draw_header(
        self,
        painter: QPainter,
        rect: QRectF,
        data: DeltaViewData,
        config: dict[str, Any],
        scale: float,
    ) -> None:
        colors = config.get("colors", {})
        elements = config.get("elements", {})
        labels = config.get("header_labels", {})
        if not isinstance(labels, dict):
            labels = {}

        text = QColor(colors.get("text", "#F4F6F8"))
        label_color = QColor(colors.get("header_label", "#A7B0BA"))
        value_color = QColor(colors.get("header_value", "#F4F6F8"))
        cell_background = QColor(colors.get("header_cell_background", "#10151D"))
        separator = QColor(colors.get("header_separator", "#2A3540"))
        accent = QColor(colors.get("header_accent", "#FF54B8"))
        highlight_background = QColor(
            colors.get("header_highlight_background", "#B51B69")
        )
        highlight_text = QColor(colors.get("header_highlight_text", "#FFFFFF"))
        warning = QColor(colors.get("warning", "#E49127"))
        danger = QColor(colors.get("header_limit_danger", "#FF3B45"))

        # A família do cabeçalho é independente da fonte usada no restante
        # do Delta, permitindo escolher uma fonte mais legível para números.
        header_font_config = dict(config)
        header_font = dict(config.get("header_font", {}) or {})
        font_settings = dict(config.get("font", {}) or {})
        font_settings["family"] = str(
            header_font.get("family", "Segoe UI") or "Segoe UI"
        )
        header_font_config["font"] = font_settings

        items: list[tuple[str, str, str, QColor]] = []
        if self._enabled(elements, "session_time"):
            items.append((
                "session_time",
                str(labels.get("session_time", "TIME LEFT") or "TIME LEFT"),
                str(data.session_time_text or "--:--"),
                value_color,
            ))

        if self._enabled(elements, "session_type"):
            items.append((
                "session_type",
                str(labels.get("session_type", "SESSION") or "SESSION"),
                str(data.session_name or "--").upper(),
                value_color,
            ))

        if self._enabled(elements, "track_state"):
            items.append((
                "track_state",
                str(labels.get("track_state", "TRACK") or "TRACK"),
                str(data.track_state or "--").upper(),
                value_color,
            ))

        if self._enabled(elements, "split") and data.split_label:
            split_value = str(data.split_label).strip().upper()
            if split_value.startswith("SPLIT "):
                split_value = split_value[6:].strip()
            elif split_value.startswith("S "):
                split_value = split_value[2:].strip()
            items.append((
                "split",
                str(labels.get("split", "SPLIT") or "SPLIT"),
                split_value or "--",
                value_color,
            ))

        if self._enabled(elements, "penalties"):
            current = max(0.0, float(data.penalties_current or 0.0))
            limit = max(0.0, float(data.penalties_limit or 0.0))
            if limit > 0 and current >= limit:
                limit_color = danger
            elif current > 0:
                limit_color = warning
            else:
                limit_color = value_color
            items.append((
                "penalties",
                str(labels.get("penalties", "PEN") or "PEN"),
                str(data.track_limits_text or "--"),
                limit_color,
            ))

        if not items:
            return

        radius = max(3.0, float(config.get("header_radius", 6.0)) * scale)
        border_width = max(0.6, float(config.get("header_border_width", 0.8)) * scale)
        self._draw_section_panel(
            painter, rect, config, "header", scale,
            colors.get("header_background", "#080B10"),
            colors.get("header_separator", "#2A3540"),
            6.0,
        )

        gap = max(1.0, float(config.get("header_cell_gap", 3.0)) * scale)
        inner = rect.adjusted(2.0 * scale, 2.0 * scale, -2.0 * scale, -2.0 * scale)
        gaps_width = gap * max(0, len(items) - 1)
        usable_width = max(1.0, inner.width() - gaps_width)

        # Dá mais espaço a tempo e sessão, mas mantém cada bloco responsivo.
        weight_by_key = {
            "session_time": 1.30,
            "session_type": 1.55,
            "track_state": 1.00,
            "split": 0.92,
            "penalties": 0.92,
        }
        weights = [weight_by_key.get(item[0], 1.0) for item in items]
        weight_total = sum(weights) or 1.0
        x = inner.left()
        highlight_item = str(
            config.get("header_highlight_item", "session_type") or "session_type"
        )

        label_size = max(
            7.0,
            float(config.get("header_label_size", 10.0)) * scale,
        )
        value_size = max(
            7.0,
            float(config.get("header_value_size", 19.0)) * scale,
        )
        vertical_padding = max(1.0, 3.0 * scale)

        for index, (key, label, value, status_color) in enumerate(items):
            width = usable_width * weights[index] / weight_total
            if index == len(items) - 1:
                width = inner.right() - x
            cell = QRectF(x, inner.top(), width, inner.height())
            x += width + gap

            highlighted = key == highlight_item and highlight_item != "none"
            self._draw_section_panel(
                painter, cell, config,
                "header_highlight" if highlighted else "header_cells",
                scale,
                (
                    colors.get("header_highlight_background", "#B51B69")
                    if highlighted else colors.get("header_cell_background", "#10151D")
                ),
                (
                    colors.get("header_accent", "#FF54B8")
                    if highlighted else colors.get("header_separator", "#2A3540")
                ),
                max(2.0, radius * 0.72) / max(0.35, scale),
            )

            label_rect = QRectF(
                cell.left() + 3.0 * scale,
                cell.top() + vertical_padding,
                max(1.0, cell.width() - 6.0 * scale),
                max(1.0, cell.height() * 0.34),
            )
            value_rect = QRectF(
                cell.left() + 3.0 * scale,
                cell.top() + cell.height() * 0.34,
                max(1.0, cell.width() - 6.0 * scale),
                max(1.0, cell.height() * 0.59 - vertical_padding * 0.35),
            )

            label_font = self._fit_font(
                header_font_config,
                label_rect,
                label.upper(),
                label_size,
                7,
                True,
            )
            painter.setFont(label_font)
            label_pen = QColor(highlight_text if highlighted else label_color)
            if highlighted:
                label_pen.setAlpha(205)
            painter.setPen(label_pen)
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                label.upper(),
            )

            value_font = self._fit_font(
                header_font_config,
                value_rect,
                value,
                value_size,
                7,
                True,
            )
            painter.setFont(value_font)
            painter.setPen(
                highlight_text if highlighted else status_color
            )
            painter.drawText(
                value_rect,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                value,
            )

        # Filete rosa reforça a identidade visual sem obrigar o usuário a
        # manter essa cor: o valor vem do seletor de cores do editor.
        accent_height = max(1.0, float(config.get("header_accent_height", 2.0)) * scale)
        accent_rect = QRectF(
            rect.left() + radius,
            rect.bottom() - accent_height,
            max(1.0, rect.width() - radius * 2.0),
            accent_height,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(
            accent_rect,
            accent_height / 2.0,
            accent_height / 2.0,
        )

    def _draw_delta_bar(
        self,
        painter: QPainter,
        rect: QRectF,
        delta_s: float,
        config: dict[str, Any],
        scale: float,
    ) -> None:
        """
        Direção solicitada:

        - centro para a esquerda: tempo pior, vermelho;
        - centro para a direita: tempo melhor, verde.

        No LMU, delta negativo normalmente significa ganho. Por isso a
        posição visual usa -delta_s.
        """
        colors = config.get("colors", {})
        text = QColor(colors.get("text", "#F4F6F8"))
        gain = QColor(colors.get("gain", "#55D98A"))
        loss = QColor(colors.get("loss", "#FF2828"))
        neutral = QColor(colors.get("neutral", "#5A5A5A"))
        muted = QColor(colors.get("muted", "#A7B0BA"))

        self._draw_section_panel(
            painter, rect, config, "delta_bar", scale,
            colors.get("panel", "#12171D"),
            colors.get("border", "#2A3540"),
            8.0,
        )

        inner = rect.adjusted(
            max(8.0, 24.0 * scale),
            max(8.0, 18.0 * scale),
            -max(8.0, 24.0 * scale),
            -max(8.0, 14.0 * scale),
        )
        bar = QRectF(
            inner.left(),
            inner.top() + inner.height() * 0.08,
            inner.width(),
            inner.height() * 0.32,
        )
        number = QRectF(
            inner.left(),
            bar.bottom(),
            inner.width(),
            inner.bottom() - bar.bottom(),
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(neutral)
        painter.drawRoundedRect(
            bar,
            max(1.0, 3.0 * scale),
            max(1.0, 3.0 * scale),
        )

        center_x = bar.center().x()
        painter.setPen(
            QPen(
                text,
                max(1.0, 2.0 * scale),
            )
        )
        painter.drawLine(
            QPointF(
                center_x,
                bar.top() - 3 * scale,
            ),
            QPointF(
                center_x,
                bar.bottom() + 3 * scale,
            ),
        )

        max_delta = max(
            0.1,
            float(
                config.get(
                    "max_delta_seconds",
                    5.0,
                )
            ),
        )

        # Inverte o sinal apenas para a posição visual.
        visual_ratio = max(
            -1.0,
            min(1.0, -delta_s / max_delta),
        )
        travel = bar.width() / 2
        marker_x = center_x + visual_ratio * travel
        delta_color = gain if delta_s <= 0 else loss

        if marker_x >= center_x:
            fill = QRectF(
                center_x,
                bar.top(),
                marker_x - center_x,
                bar.height(),
            )
        else:
            fill = QRectF(
                marker_x,
                bar.top(),
                center_x - marker_x,
                bar.height(),
            )

        painter.fillRect(fill, delta_color)

        marker_width = max(
            4.0,
            7.0 * scale,
        )
        marker = QRectF(
            marker_x - marker_width / 2,
            bar.top() - 2 * scale,
            marker_width,
            bar.height() + 4 * scale,
        )
        painter.fillRect(marker, delta_color)

        value = f"{delta_s:+.3f}"
        painter.setFont(
            self._fit_font(
                config,
                number,
                value,
                number.height() * 0.63,
                12,
                True,
            )
        )
        painter.setPen(delta_color)
        painter.drawText(
            number,
            Qt.AlignmentFlag.AlignCenter,
            value,
        )

    def _draw_history(
        self,
        painter: QPainter,
        rect: QRectF,
        history: Sequence[float],
        config: dict[str, Any],
        scale: float,
    ) -> None:
        colors = config.get("colors", {})
        grid = QColor(colors.get("grid", "#26303A"))
        panel = QColor(colors.get("panel", "#12171D"))
        gain = QColor(colors.get("gain", "#55D98A"))
        loss = QColor(colors.get("loss", "#FF2828"))
        muted = QColor(colors.get("muted", "#A7B0BA"))

        self._draw_section_panel(
            painter, rect, config, "history", scale,
            colors.get("history_background", "#12171D"),
            colors.get("history_border", "#26303A"),
            7.0,
        )

        graph = rect.adjusted(
            10 * scale,
            8 * scale,
            -10 * scale,
            -8 * scale,
        )
        center_y = graph.center().y()

        painter.setPen(
            QPen(
                grid,
                max(0.8, scale),
            )
        )

        for index in range(1, 6):
            x = (
                graph.left()
                + graph.width() * index / 6
            )
            painter.drawLine(
                QPointF(x, graph.top()),
                QPointF(x, graph.bottom()),
            )

        painter.setPen(
            QPen(
                muted,
                max(1.0, scale),
            )
        )
        painter.drawLine(
            QPointF(graph.left(), center_y),
            QPointF(graph.right(), center_y),
        )

        if len(history) < 2:
            return

        max_delta = max(
            0.1,
            float(
                config.get(
                    "max_delta_seconds",
                    5.0,
                )
            ),
        )

        gain_path = QPainterPath()
        loss_path = QPainterPath()
        gain_started = False
        loss_started = False

        for index, value in enumerate(history):
            x = (
                graph.left()
                + graph.width()
                * index
                / max(1, len(history) - 1)
            )

            # Negativo/bom aparece para cima no histórico.
            normalized = max(
                -1.0,
                min(
                    1.0,
                    float(value) / max_delta,
                ),
            )
            y = (
                center_y
                + normalized
                * graph.height()
                / 2
            )

            if value <= 0:
                if not gain_started:
                    gain_path.moveTo(x, y)
                    gain_started = True
                else:
                    gain_path.lineTo(x, y)

                loss_started = False
            else:
                if not loss_started:
                    loss_path.moveTo(x, y)
                    loss_started = True
                else:
                    loss_path.lineTo(x, y)

                gain_started = False

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(
                gain,
                max(1.2, 2.2 * scale),
            )
        )
        painter.drawPath(gain_path)

        painter.setPen(
            QPen(
                loss,
                max(1.2, 2.2 * scale),
            )
        )
        painter.drawPath(loss_path)

    def _draw_fastest_laps(
        self,
        painter: QPainter,
        rect: QRectF,
        fastest_laps: Sequence[FastestLapData],
        config: dict[str, Any],
        scale: float,
    ) -> None:
        if not fastest_laps:
            return
        gap = max(2.0, 8.0 * scale)
        row_height = (
            rect.height() - gap * max(0, len(fastest_laps) - 1)
        ) / len(fastest_laps)
        for index, fastest in enumerate(fastest_laps):
            row = QRectF(
                rect.left(),
                rect.top() + index * (row_height + gap),
                rect.width(),
                row_height,
            )

            self._draw_fastest_lap(
                painter,
                row,
                fastest,
                config,
                scale,
            )

    def _draw_fastest_lap(
        self,
        painter: QPainter,
        rect: QRectF,
        fastest: FastestLapData,
        config: dict[str, Any],
        scale: float,
    ) -> None:
        colors = config.get("colors", {})
        panel = QColor(
            colors.get(
                "fastest_panel",
                "#0E1319",
            )
        )
        text = QColor(
            colors.get(
                "text",
                "#F4F6F8",
            )
        )
        purple = QColor(
            colors.get(
                "fastest",
                "#8B4DFF",
            )
        )
        muted = QColor(
            colors.get(
                "muted",
                "#A7B0BA",
            )
        )

        self._draw_section_panel(
            painter, rect, config, "fastest_lap", scale,
            colors.get("fastest_panel", "#0E1319"),
            colors.get("fastest_border", "#6036AE"),
            8.0,
        )

        padding = max(
            5.0,
            10.0 * scale,
        )
        inner = rect.adjusted(
            padding,
            padding,
            -padding,
            -padding,
        )
        logo_width = (
            inner.height() * 1.15
            if bool(
                config.get(
                    "show_manufacturer_logo",
                    True,
                )
            )
            else 0.0
        )
        flag_width = inner.height() * 0.72
        position_width = inner.width() * 0.18
        lap_width = inner.width() * 0.26
        driver_width = (
            inner.width()
            - logo_width
            - flag_width
            - position_width
            - lap_width
        )

        logo_rect = QRectF(
            inner.left(),
            inner.top(),
            logo_width,
            inner.height(),
        )
        driver_rect = QRectF(
            logo_rect.right(),
            inner.top(),
            driver_width,
            inner.height(),
        )
        flag_rect = QRectF(
            driver_rect.right(),
            inner.top(),
            flag_width,
            inner.height(),
        )
        lap_rect = QRectF(
            flag_rect.right(),
            inner.top(),
            lap_width,
            inner.height(),
        )
        position_rect = QRectF(
            lap_rect.right(),
            inner.top(),
            position_width,
            inner.height(),
        )

        if logo_width > 0:
            pixmap = self.logo_manager.pixmap(
                fastest.logo_path
            )

            if pixmap is not None:
                target = logo_rect.adjusted(
                    3 * scale,
                    3 * scale,
                    -3 * scale,
                    -3 * scale,
                )
                scaled = pixmap.scaled(
                    int(target.width()),
                    int(target.height()),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                x = (
                    target.center().x()
                    - scaled.width() / 2
                )
                y = (
                    target.center().y()
                    - scaled.height() / 2
                )
                painter.drawPixmap(
                    int(x),
                    int(y),
                    scaled,
                )
            else:
                initials = (
                    fastest.manufacturer
                    or "CAR"
                )[:3].upper()

                painter.setPen(purple)
                painter.setBrush(
                    Qt.BrushStyle.NoBrush
                )
                painter.drawEllipse(
                    logo_rect.adjusted(
                        6 * scale,
                        6 * scale,
                        -6 * scale,
                        -6 * scale,
                    )
                )
                painter.setFont(
                    self._fit_font(
                        config,
                        logo_rect,
                        initials,
                        logo_rect.height() * 0.25,
                        7,
                        True,
                    )
                )
                painter.drawText(
                    logo_rect,
                    Qt.AlignmentFlag.AlignCenter,
                    initials,
                )

        driver_name = (
            fastest.driver_name
            or "Fastest lap"
        )
        painter.setFont(
            self._fit_font(
                config,
                driver_rect,
                driver_name,
                driver_rect.height() * 0.35,
                8,
                True,
            )
        )
        painter.setPen(text)
        painter.drawText(
            driver_rect.adjusted(
                5 * scale,
                0,
                -5 * scale,
                0,
            ),
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            driver_name,
        )

        flag_target = flag_rect.adjusted(
            3 * scale,
            flag_rect.height() * .28,
            -3 * scale,
            -flag_rect.height() * .28,
        )
        flag = self.flag_store.pixmap(
            fastest.nationality,
            fastest.country_code,
            max(1, round(flag_target.width())),
            max(1, round(flag_target.height())),
        )
        if flag is not None:
            painter.drawPixmap(flag_target.toRect(), flag)
        else:
            emoji = flag_emoji(fastest.nationality, fastest.country_code)
            if emoji:
                painter.setFont(self._fit_font(config, flag_rect, emoji, flag_rect.height()*.34, 8, False))
                painter.setPen(text)
                painter.drawText(flag_rect, Qt.AlignmentFlag.AlignCenter, emoji)

        lap_text = self._format_lap(
            fastest.lap_time_s
        )
        painter.setFont(
            self._fit_font(
                config,
                lap_rect,
                lap_text,
                lap_rect.height() * 0.40,
                8,
                True,
            )
        )
        painter.setPen(purple)
        painter.drawText(
            lap_rect,
            Qt.AlignmentFlag.AlignCenter,
            lap_text,
        )

        class_position = fastest.class_position or fastest.position
        class_name = str(fastest.vehicle_class or "").upper()
        position = (
            f"P{class_position} {class_name}".strip()
            if class_position > 0
            else ""
        )
        painter.setFont(
            self._fit_font(
                config,
                position_rect,
                position,
                position_rect.height() * 0.40,
                7,
                True,
            )
        )
        painter.setPen(muted)
        painter.drawText(
            position_rect,
            Qt.AlignmentFlag.AlignCenter,
            position,
        )

    def _draw_sectors(
        self,
        painter: QPainter,
        rect: QRectF,
        sectors: Sequence[DeltaSectorData],
        config: dict[str, Any],
        scale: float,
    ) -> None:
        colors = config.get("colors", {})
        text = QColor(
            colors.get(
                "text",
                "#F4F6F8",
            )
        )
        neutral = QColor(
            colors.get(
                "sector_neutral",
                "#5A5A5A",
            )
        )
        better = QColor(
            colors.get(
                "sector_better",
                "#55D98A",
            )
        )
        worse = QColor(
            colors.get(
                "sector_worse",
                "#FFC42E",
            )
        )
        session_best = QColor(
            colors.get(
                "sector_session_best",
                "#8B4DFF",
            )
        )

        if not sectors:
            return

        color_by_status = {
            SECTOR_BETTER: better,
            SECTOR_WORSE: worse,
            SECTOR_SESSION_BEST: session_best,
        }

        sector = sectors[0]
        box = rect

        color = color_by_status.get(sector.status, neutral)

        self._draw_section_panel(
            painter, box.adjusted(scale, scale, -scale, -scale),
            config, "sectors", scale,
            colors.get("sector_panel", "#8B4DFF"),
            colors.get("sector_border", "#8B4DFF"),
            7.0,
        )

        if sector.delta_s is not None:
            label = f"{sector.label}  {sector.delta_s:+.3f}"
        elif sector.time_s is not None:
            label = f"{sector.label}  {sector.time_s:.3f}"
        else:
            label = sector.label

        font = self._fit_font(config, box, label, box.height() * 0.52, 8, True)
        font.setWeight(QFont.Weight.Black)
        painter.setFont(font)
        # No melhor setor a cor do texto e do fundo seria a mesma roxa.
        # Usa branco nesse caso para preservar contraste e legibilidade.
        painter.setPen(text if sector.status == SECTOR_SESSION_BEST else color)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)

    @staticmethod
    def _sector_layout_config(config: dict[str, Any], visible: bool) -> dict[str, Any]:
        if visible:
            return config
        result = dict(config)
        elements = dict(config.get("elements", {}))
        sector = elements.get("sectors", {})
        if isinstance(sector, dict):
            sector = dict(sector)
            sector["enabled"] = False
        else:
            sector = False
        elements["sectors"] = sector
        result["elements"] = elements
        return result

    @staticmethod
    def _enabled(
        elements: dict[str, Any],
        key: str,
    ) -> bool:
        value = elements.get(key, {})

        if isinstance(value, bool):
            return value

        return bool(value.get("enabled", False))

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
                    "Bahnschrift Condensed",
                )
            )
        )
        font.setPixelSize(
            max(7, int(pixel_size))
        )
        # Todas as fontes do Delta usam peso em negrito, inclusive
        # textos auxiliares e fallbacks que antes solicitavam fonte normal.
        font.setBold(True)
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
                <= rect.width() * 0.92
                and metrics.height()
                <= rect.height() * 0.90
            ):
                return font

            size -= 1

        return self._font(
            config,
            minimum,
            bold,
        )

    @staticmethod
    def _format_lap(seconds: float) -> str:
        if seconds <= 0:
            return "--:--.---"

        minutes = int(seconds // 60)
        remainder = seconds - minutes * 60
        return f"{minutes}:{remainder:06.3f}"

    @staticmethod
    def _format_counter(value: float) -> str:
        """
        Formata pontos de punição em intervalos de 0.25.

        Exemplos:
        0.00 -> 0
        0.25 -> 0.25
        0.50 -> 0.50
        0.75 -> 0.75
        1.00 -> 1
        """
        rounded_integer = round(value)

        if abs(value - rounded_integer) < 0.001:
            return str(int(rounded_integer))

        return f"{value:.2f}"
