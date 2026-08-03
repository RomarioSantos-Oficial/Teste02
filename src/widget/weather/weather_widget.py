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

from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QPoint,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QPixmap,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .weather_icons import WeatherIconManager
from .weather_models import (
    WeatherForecast,
    WeatherSample,
)
from .weather_predictor import (
    WeatherTrendPredictor,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parents[3]


class WeatherWidget(QWidget):
    """
    Tempo Completo adaptado ao Sector Flow Drive.

    Preserva o layer do arquivo de referência:
    - pista e temperatura à esquerda;
    - clima e temperatura do ar;
    - cartão condicional de chuva/pista molhada;
    - cinco blocos de tendência à direita.
    """

    geometry_changed = Signal(
        str,
        float,
        float,
        float,
        float,
    )
    selected = Signal(str)

    BASE_WIDTH = 760.0

    def __init__(
        self,
        widget_id: str,
        config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.widget_id = widget_id
        self.config = config
        self.edit_mode = False

        self.predictor = WeatherTrendPredictor(
            max_samples=int(
                config.get(
                    "history_samples",
                    180,
                )
            ),
            sample_interval_seconds=float(
                config.get(
                    "sample_interval_seconds",
                    2.0,
                )
            ),
        )
        self.icons = WeatherIconManager(
            PROJECT_ROOT,
            str(
                config.get(
                    "icon_directory",
                    "images/tempo",
                )
            ),
        )

        self.current_sample: (
            WeatherSample | None
        ) = None
        self.forecasts: list[
            WeatherForecast
        ] = []

        self._dragging = False
        self._resizing = False
        self._drag_offset = QPoint()
        self._resize_start_global = QPoint()
        self._resize_start_width = 0
        self._responsive_scale = 1.0
        self._metrics_pending = False
        self._fitting = False

        self.setWindowTitle(
            "Sector Flow Drive - Weather"
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.setMinimumWidth(320)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )

        self.main_layout = QVBoxLayout(
            self
        )
        self.main_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        self.main_layout.setSpacing(4)

        self.top_layout = QHBoxLayout()
        self.top_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        self.top_layout.setSpacing(4)
        self.main_layout.addLayout(
            self.top_layout
        )

        self._build_current_panel()
        self._build_forecast_panel()
        self._build_status_panel()
        self.apply_config()

    def _build_current_panel(self) -> None:
        self.current_panel = QFrame()
        self.current_panel.setObjectName(
            "CurrentWeatherPanel"
        )
        self.current_grid = QGridLayout(
            self.current_panel
        )

        self.track_icon = QLabel()
        self.track_icon.setObjectName(
            "CurrentIcon"
        )
        self.track_icon.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.weather_icon = QLabel()
        self.weather_icon.setObjectName(
            "CurrentIcon"
        )
        self.weather_icon.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.track_temp = QLabel("--°C")
        self.track_temp.setObjectName(
            "TrackTemp"
        )
        self.track_temp.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.air_temp = QLabel("--°C")
        self.air_temp.setObjectName(
            "AirTemp"
        )
        self.air_temp.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.wet_status = QLabel("")
        self.wet_status.setObjectName(
            "WetStatus"
        )
        self.wet_status.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.wet_status.hide()

        self.wind_status = QLabel("")
        self.wind_status.setObjectName(
            "WindStatus"
        )
        self.wind_status.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.wind_status.hide()

        self.current_grid.addWidget(
            self.track_icon,
            0,
            0,
        )
        self.current_grid.addWidget(
            self.weather_icon,
            0,
            1,
        )
        self.current_grid.addWidget(
            self.track_temp,
            1,
            0,
        )
        self.current_grid.addWidget(
            self.air_temp,
            1,
            1,
        )
        self.top_layout.addWidget(
            self.current_panel,
            0,
        )

    def _build_forecast_panel(
        self,
    ) -> None:
        self.forecast_panel = QFrame()
        self.forecast_panel.setObjectName(
            "ForecastPanel"
        )
        self.forecast_layout = QHBoxLayout(
            self.forecast_panel
        )
        self.forecast_cards: list[
            dict[str, Any]
        ] = []

        for index in range(5):
            card = QFrame()
            card.setObjectName(
                "ForecastCard"
            )
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            card_layout = QVBoxLayout(
                card
            )

            time_label = QLabel(
                f"+{(index + 1) * 5}m"
            )
            time_label.setObjectName(
                "ForecastTime"
            )
            time_label.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

            icon_label = QLabel()
            icon_label.setObjectName(
                "ForecastIcon"
            )
            icon_label.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

            temp_label = QLabel("--°")
            temp_label.setObjectName(
                "ForecastTemp"
            )
            temp_label.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

            rain_label = QLabel("")
            rain_label.setObjectName(
                "ForecastRain"
            )
            rain_label.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )
            rain_label.hide()

            card_layout.addWidget(
                time_label
            )
            card_layout.addWidget(
                icon_label,
                alignment=Qt.AlignmentFlag.AlignCenter,
            )
            card_layout.addWidget(
                temp_label
            )
            card_layout.addWidget(
                rain_label
            )

            self.forecast_layout.addWidget(
                card,
                1,
            )
            self.forecast_cards.append(
                {
                    "card": card,
                    "layout": card_layout,
                    "time": time_label,
                    "icon": icon_label,
                    "temp": temp_label,
                    "rain": rain_label,
                }
            )

        self.top_layout.addWidget(
            self.forecast_panel,
            1,
        )

    def _build_status_panel(self) -> None:
        self.status_panel = QFrame()
        self.status_panel.setObjectName(
            "WeatherStatusPanel"
        )
        self.status_layout = QHBoxLayout(
            self.status_panel
        )
        self.status_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        self.status_layout.setSpacing(2)
        self.status_layout.addWidget(
            self.wet_status
        )
        self.status_layout.addWidget(
            self.wind_status
        )
        self.status_layout.addStretch(1)
        self.wet_status.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.wind_status.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.main_layout.addWidget(
            self.status_panel
        )
        self.status_panel.hide()

    def apply_config(self) -> None:
        self.setWindowOpacity(
            max(
                0.10,
                min(
                    1.0,
                    float(
                        self.config.get(
                            "opacity",
                            0.98,
                        )
                    ),
                ),
            )
        )
        self.predictor.update_config(
            float(
                self.config.get(
                    "sample_interval_seconds",
                    2.0,
                )
            )
        )
        self.icons.set_directory(
            str(
                self.config.get(
                    "icon_directory",
                    "images/tempo",
                )
            )
        )
        self.forecast_panel.setVisible(
            bool(
                self.config.get(
                    "show_forecast",
                    True,
                )
            )
        )
        self._schedule_metrics()
        self.update()

    def update_config(
        self,
        config: dict[str, Any],
    ) -> None:
        self.config = config
        self.apply_config()

        if self.current_sample is not None:
            self._render(
                self.current_sample,
                self.forecasts,
            )

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
                    0.30,
                )
            )
        )
        y = int(
            screen_geometry.top()
            + screen_geometry.height()
            * float(
                position.get(
                    "y",
                    0.04,
                )
            )
        )

        self.resize(
            width,
            max(70, self.height()),
        )
        self.move(x, y)
        self._schedule_metrics()

    def update_from_session(
        self,
        session: Any,
    ) -> None:
        sample = self.predictor.add_session(
            session
        )
        count = max(
            1,
            min(
                5,
                int(
                    self.config.get(
                        "forecast_count",
                        5,
                    )
                ),
            ),
        )
        interval = max(
            1,
            int(
                self.config.get(
                    "forecast_interval_minutes",
                    5,
                )
            ),
        )

        forecasts = self.predictor.forecast(
            sample,
            count=count,
            interval_minutes=interval,
        )

        self.current_sample = sample
        self.forecasts = forecasts
        self._render(
            sample,
            forecasts,
        )

    def _render(
        self,
        sample: WeatherSample,
        forecasts: list[
            WeatherForecast
        ],
    ) -> None:
        symbol = self._temperature_symbol()
        self.track_temp.setText(
            f"{self._temperature(sample.track_temp_c):.1f}"
            f"{symbol}"
        )
        self.air_temp.setText(
            f"{self._temperature(sample.air_temp_c):.1f}"
            f"{symbol}"
        )

        current_state = (
            WeatherTrendPredictor.weather_state(
                rain=sample.rain,
                wetness=sample.wetness,
                dark_cloud=sample.dark_cloud,
                cloud_coverage=sample.cloud_coverage,
                time_of_day_s=sample.time_of_day_s,
            )
        )

        self._set_icon(
            self.track_icon,
            "Pista",
        )
        self._set_icon(
            self.weather_icon,
            current_state,
        )

        rain_threshold = max(
            0.0,
            min(
                1.0,
                float(
                    self.config.get(
                        "rain_alert_threshold",
                        0.01,
                    )
                ),
            ),
        )
        wet_threshold = max(
            0.0,
            min(
                1.0,
                float(
                    self.config.get(
                        "wet_alert_threshold",
                        0.02,
                    )
                ),
            ),
        )
        rain_pct = round(
            sample.rain * 100
        )
        wet_pct = round(
            sample.wetness * 100
        )

        show_wet = (
            bool(
                self.config.get(
                    "show_wet_status",
                    True,
                )
            )
            and (
                sample.rain >= rain_threshold
                or sample.wetness >= wet_threshold
            )
        )

        if show_wet:
            if sample.rain >= rain_threshold:
                text = (
                    f"CHUVA {rain_pct}%  |  "
                    f"PISTA {wet_pct}%"
                )
            else:
                text = (
                    f"PISTA MOLHADA {wet_pct}%"
                )

            self.wet_status.setText(
                text
            )
            self.wet_status.show()
        else:
            self.wet_status.hide()

        show_wind = bool(
            self.config.get(
                "show_wind",
                False,
            )
        )

        if show_wind:
            self.wind_status.setText(
                f"VENTO "
                f"{sample.wind_speed_kmh:.1f} km/h"
            )
            self.wind_status.show()
        else:
            self.wind_status.hide()

        self.status_panel.setVisible(
            show_wet or show_wind
        )

        show_forecast_rain = bool(
            self.config.get(
                "show_forecast_rain",
                False,
            )
        )

        for index, card in enumerate(
            self.forecast_cards
        ):
            visible = (
                index < len(forecasts)
                and bool(
                    self.config.get(
                        "show_forecast",
                        True,
                    )
                )
            )
            card["card"].setVisible(
                visible
            )

            if not visible:
                continue

            forecast = forecasts[index]
            card["time"].setText(
                f"+{forecast.minutes_ahead}m"
            )
            card["temp"].setText(
                f"{self._temperature(forecast.air_temp_c):.1f}°"
            )
            self._set_icon(
                card["icon"],
                forecast.weather_state,
                forecast=True,
            )

            if show_forecast_rain:
                card["rain"].setText(
                    f"{round(forecast.rain * 100)}%"
                )
                card["rain"].show()
            else:
                card["rain"].hide()

        self._schedule_metrics()

    def _set_icon(
        self,
        label: QLabel,
        state: str,
        forecast: bool = False,
    ) -> None:
        base_size = (
            24
            if forecast
            else 30
        )
        size = max(
            10,
            round(
                base_size
                * self._responsive_scale
            ),
        )
        pixmap = self.icons.pixmap(
            state,
            size,
        )

        if pixmap is not None:
            label.setText("")
            label.setPixmap(pixmap)
        else:
            label.setPixmap(QPixmap())
            label.setText(
                self.icons.fallback_text(
                    state
                )
            )

    def resizeEvent(
        self,
        event: QResizeEvent,
    ) -> None:
        super().resizeEvent(event)
        self._schedule_metrics()

    def _schedule_metrics(self) -> None:
        if self._metrics_pending:
            return

        self._metrics_pending = True
        QTimer.singleShot(
            0,
            self._apply_responsive_metrics,
        )

    def _apply_responsive_metrics(
        self,
    ) -> None:
        self._metrics_pending = False
        minimum = max(
            0.32,
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
                    2.0,
                )
            ),
        )
        internal = max(
            0.5,
            float(
                self.config.get(
                    "internal_scale",
                    1.0,
                )
            ),
        )

        self._responsive_scale = max(
            minimum,
            min(
                maximum,
                self.width()
                / self.BASE_WIDTH
                * internal,
            ),
        )
        s = self._responsive_scale

        gap = max(
            2,
            round(
                float(
                    self.config.get(
                        "bar_gap",
                        4,
                    )
                )
                * s
            ),
        )
        self.main_layout.setSpacing(gap)
        self.top_layout.setSpacing(gap)
        self.status_layout.setSpacing(gap)
        self.current_grid.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        self.current_grid.setSpacing(gap)
        self.forecast_layout.setContentsMargins(
            gap,
            0,
            0,
            0,
        )
        self.forecast_layout.setSpacing(
            max(2, round(5 * s))
        )

        icon_size = max(
            12,
            round(
                int(
                    self.config.get(
                        "icon_size",
                        30,
                    )
                )
                * s
            ),
        )

        for icon in (
            self.track_icon,
            self.weather_icon,
        ):
            icon.setFixedSize(
                icon_size,
                icon_size,
            )

        for card in self.forecast_cards:
            forecast_icon = max(
                10,
                round(
                    icon_size * 0.80
                ),
            )
            card["icon"].setFixedSize(
                forecast_icon,
                forecast_icon,
            )
            card["layout"].setContentsMargins(
                max(1, round(2 * s)),
                max(1, round(2 * s)),
                max(1, round(2 * s)),
                max(1, round(2 * s)),
            )
            card["layout"].setSpacing(
                max(1, round(2 * s))
            )

        current_width = max(
            100,
            round(168 * s),
        )
        self.current_panel.setFixedWidth(
            current_width
        )
        self._apply_style(s)

        if self.current_sample is not None:
            current_state = (
                WeatherTrendPredictor.weather_state(
                    rain=self.current_sample.rain,
                    wetness=self.current_sample.wetness,
                    dark_cloud=self.current_sample.dark_cloud,
                    cloud_coverage=self.current_sample.cloud_coverage,
                    time_of_day_s=self.current_sample.time_of_day_s,
                )
            )
            self._set_icon(
                self.track_icon,
                "Pista",
            )
            self._set_icon(
                self.weather_icon,
                current_state,
            )

            for index, forecast in enumerate(
                self.forecasts[:5]
            ):
                self._set_icon(
                    self.forecast_cards[index][
                        "icon"
                    ],
                    forecast.weather_state,
                    forecast=True,
                )

        QTimer.singleShot(
            0,
            self._fit_content,
        )

    def _apply_style(
        self,
        scale: float,
    ) -> None:
        colors = self.config.get(
            "colors",
            {},
        )
        font_name = str(
            self.config.get(
                "font_name",
                "Arial",
            )
        )
        base_font = max(
            8,
            int(
                self.config.get(
                    "font_size",
                    16,
                )
            ),
        )
        value_size = max(
            7,
            round(base_font * scale),
        )
        forecast_size = max(
            6,
            round(
                base_font
                * 0.75
                * scale
            ),
        )
        time_size = max(
            6,
            round(
                base_font
                * 0.62
                * scale
            ),
        )
        radius = max(
            3,
            round(5 * scale),
        )
        padding = max(
            1,
            round(2 * scale),
        )
        wet_padding = max(
            3,
            round(6 * scale),
        )
        wet_font_size = max(
            8,
            round(
                base_font
                * 0.90
                * scale
            ),
        )
        border = max(
            1,
            round(1 * scale),
        )

        background = colors.get(
            "background",
            "#0A0F17",
        )
        panel = colors.get(
            "panel",
            "#161616",
        )
        track = colors.get(
            "track_temp",
            "#FFAA00",
        )
        air = colors.get(
            "air_temp",
            "#FFFFFF",
        )
        muted = colors.get(
            "muted",
            "#999999",
        )
        forecast_text = colors.get(
            "forecast_text",
            "#E0E0E0",
        )
        wet_background = colors.get(
            "wet_background",
            "#0C274A",
        )
        wet_text = colors.get(
            "wet_text",
            "#00AAFF",
        )
        border_color = colors.get(
            "border",
            "#344155",
        )

        self.setStyleSheet(
            f"""
            WeatherWidget {{
                background: transparent;
                border: none;
                font-family: "{font_name}";
            }}

            QFrame#CurrentWeatherPanel,
            QFrame#ForecastPanel,
            QFrame#WeatherStatusPanel {{
                background: transparent;
                border: none;
            }}

            QLabel#TrackTemp {{
                background-color: {panel};
                color: {track};
                border: {border}px solid {border_color};
                border-radius: {radius}px;
                padding: {padding}px;
                font-size: {value_size}px;
                font-weight: 900;
            }}

            QLabel#AirTemp {{
                background-color: {panel};
                color: {air};
                border: {border}px solid {border_color};
                border-radius: {radius}px;
                padding: {padding}px;
                font-size: {value_size}px;
                font-weight: 900;
            }}

            QLabel#WetStatus {{
                background-color: {wet_background};
                color: {wet_text};
                border: {border}px solid {wet_text};
                border-radius: {radius}px;
                padding: {wet_padding}px;
                font-size: {wet_font_size}px;
                font-weight: 900;
            }}

            QLabel#WindStatus {{
                background-color: {background};
                color: {muted};
                border-radius: {radius}px;
                padding: {padding}px;
                font-size: {time_size}px;
                font-weight: bold;
            }}

            QFrame#ForecastCard {{
                background-color: {background};
                border: {border}px solid {border_color};
                border-radius: {radius}px;
            }}

            QLabel#ForecastTime {{
                color: {muted};
                font-size: {time_size}px;
                font-weight: bold;
            }}

            QLabel#ForecastTemp {{
                background-color: {panel};
                color: {forecast_text};
                border-radius: {radius}px;
                padding: {padding}px;
                font-size: {forecast_size}px;
                font-weight: bold;
            }}

            QLabel#ForecastRain {{
                color: {wet_text};
                font-size: {time_size}px;
                font-weight: bold;
            }}

            QLabel#ForecastIcon {{
                color: {forecast_text};
                font-size: {time_size}px;
                font-weight: bold;
            }}
            """
        )

    def set_edit_mode(
        self,
        enabled: bool,
    ) -> None:
        self.edit_mode = bool(
            enabled
        )
        self.setCursor(
            Qt.CursorShape.SizeAllCursor
            if self.edit_mode
            else Qt.CursorShape.ArrowCursor
        )
        self.update()

    def paintEvent(
        self,
        event: QPaintEvent,
    ) -> None:
        super().paintEvent(event)

        if not self.edit_mode:
            return

        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )
        color = QColor(
            self.config.get(
                "colors",
                {},
            ).get(
                "edit_border",
                "#9B5CFF",
            )
        )
        pen = QPen(
            color,
            max(
                1.0,
                2.0
                * self._responsive_scale,
            ),
        )
        pen.setStyle(
            Qt.PenStyle.DashLine
        )
        painter.setPen(pen)
        painter.setBrush(
            Qt.BrushStyle.NoBrush
        )
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(
                1,
                1,
                -1,
                -1,
            ),
            8,
            8,
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
            self._resize_start_width = (
                self.width()
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
            self.resize(
                max(
                    self.minimumWidth(),
                    self._resize_start_width
                    + delta.x(),
                ),
                self.height(),
            )
            self._schedule_metrics()
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
            self._fit_content()
            self._emit_geometry()
            event.accept()
        else:
            event.ignore()

    def _fit_content(self) -> None:
        if self._fitting:
            return

        self._fitting = True
        self.main_layout.activate()
        desired = max(
            48,
            self.main_layout.sizeHint().height(),
        )

        if abs(
            self.height() - desired
        ) > 1:
            self.resize(
                self.width(),
                desired,
            )

        self._fitting = False

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
            self.width() - size - 3,
            self.height() - size - 3,
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
                self.x()
                - rect.left()
            )
            / rect.width(),
            (
                self.y()
                - rect.top()
            )
            / rect.height(),
            self.width()
            / rect.width(),
            self.height()
            / rect.height(),
        )

    def reset_session_state(self) -> None:
        self.predictor.reset()
        self.current_sample = None
        self.forecasts = []

    def _temperature(
        self,
        value_c: float,
    ) -> float:
        unit = str(
            self.config.get(
                "temperature_unit",
                "C",
            )
        ).upper()

        if unit == "F":
            return (
                float(value_c)
                * 9.0
                / 5.0
                + 32.0
            )

        return float(value_c)

    def _temperature_symbol(
        self,
    ) -> str:
        unit = str(
            self.config.get(
                "temperature_unit",
                "C",
            )
        ).upper()
        return "°F" if unit == "F" else "°C"
