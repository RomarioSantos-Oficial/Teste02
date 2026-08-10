
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
    ) -> int:
        return self.layout_engine.preferred_height(
            width,
            config,
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
        background = QColor(colors.get("background", "#070B12"))
        border = QColor(colors.get("border", "#3A4452"))
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
            config,
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

        text = QColor(colors.get("text", "#FFFFFF"))
        muted = QColor(colors.get("muted", "#AAB2BD"))
        warning = QColor(colors.get("warning", "#FFC42E"))
        danger = QColor(colors.get("loss", "#FF2828"))
        panel = QColor(colors.get("panel", "#121821"))

        if bool(config.get("section_backgrounds", True)):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(panel)
            painter.drawRoundedRect(
                rect,
                max(3.0, 7.0 * scale),
                max(3.0, 7.0 * scale),
            )

        items: list[tuple[str, QColor]] = []

        if self._enabled(elements, "session_time"):
            items.append(
                (f"TIME  {data.session_time_text}", text)
            )

        if self._enabled(elements, "session_type"):
            items.append(
                (data.session_name.upper(), text)
            )

        if self._enabled(elements, "track_state"):
            items.append(
                (data.track_state.upper(), text)
            )

        if self._enabled(elements, "penalties"):
            current = max(0.0, data.penalties_current)
            limit = max(0.0, data.penalties_limit)

            if limit > 0:
                label = (
                    f"PEN  {self._format_counter(current)}"
                    f"/{self._format_counter(limit)}"
                )

                if current >= limit:
                    color = danger
                elif current > 0:
                    color = warning
                else:
                    color = muted
            else:
                label = f"PEN  {data.penalties}"
                color = warning if data.penalties > 0 else muted

            items.append((label, color))

        if not items:
            return

        slot_width = rect.width() / len(items)

        for index, (label, color) in enumerate(items):
            slot = QRectF(
                rect.left() + slot_width * index,
                rect.top(),
                slot_width,
                rect.height(),
            )
            painter.setFont(
                self._fit_font(
                    config,
                    slot,
                    label,
                    rect.height() * 0.35,
                    7,
                    True,
                )
            )
            painter.setPen(color)
            painter.drawText(
                slot,
                Qt.AlignmentFlag.AlignCenter,
                label,
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
        text = QColor(colors.get("text", "#FFFFFF"))
        gain = QColor(colors.get("gain", "#00A000"))
        loss = QColor(colors.get("loss", "#FF2828"))
        neutral = QColor(colors.get("neutral", "#5A5A5A"))
        panel = QColor(colors.get("panel", "#121821"))
        muted = QColor(colors.get("muted", "#AAB2BD"))

        if bool(config.get("section_backgrounds", True)):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(panel)
            painter.drawRoundedRect(
                rect,
                max(3.0, 8.0 * scale),
                max(3.0, 8.0 * scale),
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
        grid = QColor(colors.get("grid", "#27313E"))
        panel = QColor(colors.get("panel", "#121821"))
        gain = QColor(colors.get("gain", "#00A000"))
        loss = QColor(colors.get("loss", "#FF2828"))
        muted = QColor(colors.get("muted", "#AAB2BD"))

        painter.setPen(
            QPen(
                grid.lighter(130),
                max(0.8, scale),
            )
        )
        painter.setBrush(panel)
        painter.drawRoundedRect(
            rect,
            max(3.0, 7.0 * scale),
            max(3.0, 7.0 * scale),
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
                "#111720",
            )
        )
        text = QColor(
            colors.get(
                "text",
                "#FFFFFF",
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
                "#AAB2BD",
            )
        )

        painter.setPen(
            QPen(
                purple.darker(140),
                max(1.0, 1.5 * scale),
            )
        )
        painter.setBrush(panel)
        painter.drawRoundedRect(
            rect,
            max(4.0, 8.0 * scale),
            max(4.0, 8.0 * scale),
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
                "#FFFFFF",
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
                "#00A000",
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

        gap = max(
            4.0,
            8.0 * scale,
        )
        width = (
            rect.width() - gap * 2
        ) / 3

        color_by_status = {
            SECTOR_BETTER: better,
            SECTOR_WORSE: worse,
            SECTOR_SESSION_BEST: session_best,
        }

        for index in range(3):
            sector = (
                sectors[index]
                if index < len(sectors)
                else DeltaSectorData(
                    f"S{index + 1}"
                )
            )
            box = QRectF(
                rect.left()
                + index * (width + gap),
                rect.top(),
                width,
                rect.height(),
            )

            color = color_by_status.get(
                sector.status,
                neutral,
            )

            if sector.delta_s is not None:
                label = (
                    f"{sector.label}  "
                    f"{sector.delta_s:+.3f}"
                )
            elif sector.time_s is not None:
                label = (
                    f"{sector.label}  "
                    f"{sector.time_s:.3f}"
                )
            else:
                label = sector.label

            painter.setPen(
                QPen(
                    color.darker(135),
                    max(1.0, scale),
                )
            )
            painter.setBrush(color)
            painter.drawRoundedRect(
                box,
                max(3.0, 6.0 * scale),
                max(3.0, 6.0 * scale),
            )
            painter.setFont(
                self._fit_font(
                    config,
                    box,
                    label,
                    box.height() * 0.35,
                    7,
                    True,
                )
            )
            painter.setPen(text)
            painter.drawText(
                box,
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

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
