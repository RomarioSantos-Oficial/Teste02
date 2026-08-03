from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QPoint,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QBrush,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .flags_logic import FlagsLogic
from .flags_models import (
    FlagCar,
    FlagsSnapshot,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class RadarWidget(QWidget):
    """
    Radar idêntico ao desenho de referência, mas responsivo.

    O tamanho base continua 160x60. Ao redimensionar o widget principal,
    mapa, carros, linhas e textos diminuem/aumentam juntos.
    """

    BASE_WIDTH = 160
    BASE_HEIGHT = 60

    def __init__(
        self,
        parent: QWidget | None = None,
        is_blue_radar: bool = False,
    ) -> None:
        super().__init__(parent)
        self.is_blue_radar = is_blue_radar
        self.cars_data: list[FlagCar] = []
        self.ui_scale = 1.0
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.set_ui_scale(1.0)

    def set_ui_scale(
        self,
        scale: float,
    ) -> None:
        self.ui_scale = max(
            0.42,
            min(2.50, float(scale)),
        )
        self.setFixedSize(
            max(
                68,
                round(
                    self.BASE_WIDTH
                    * self.ui_scale
                ),
            ),
            max(
                26,
                round(
                    self.BASE_HEIGHT
                    * self.ui_scale
                ),
            ),
        )
        self.update()

    def update_radar_data(
        self,
        cars: list[FlagCar],
    ) -> None:
        self.cars_data = list(cars)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(
            round(
                self.BASE_WIDTH
                * self.ui_scale
            ),
            round(
                self.BASE_HEIGHT
                * self.ui_scale
            ),
        )

    def paintEvent(
        self,
        event: QPaintEvent,
    ) -> None:
        del event

        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        width = float(self.width())
        height = float(self.height())
        center_x = width / 2.0
        center_y = height / 2.0
        scale = self.ui_scale
        max_radar_distance = 140.0

        left_lane = width * 0.25
        right_lane = width * 0.75

        painter.setPen(
            QPen(
                QColor(0, 0, 0, 140),
                max(1.0, 3.0 * scale),
            )
        )
        painter.drawLine(
            QPoint(
                round(left_lane),
                0,
            ),
            QPoint(
                round(left_lane),
                round(height),
            ),
        )
        painter.drawLine(
            QPoint(
                round(right_lane),
                0,
            ),
            QPoint(
                round(right_lane),
                round(height),
            ),
        )

        dash_pen = QPen(
            QColor(0, 0, 0, 100),
            max(1.0, 2.0 * scale),
            Qt.PenStyle.DashLine,
        )
        painter.setPen(dash_pen)
        painter.drawLine(
            QPoint(
                round(center_x),
                0,
            ),
            QPoint(
                round(center_x),
                round(height),
            ),
        )

        painter.setPen(
            QPen(
                QColor(0, 0, 0, 180)
            )
        )
        font = painter.font()
        font.setPixelSize(
            max(
                6,
                round(9 * scale),
            )
        )
        font.setBold(True)
        painter.setFont(font)

        painter.save()
        painter.translate(
            width * 0.16,
            center_y + 15 * scale,
        )
        painter.rotate(-90)
        painter.drawText(0, 0, "LS")
        painter.restore()

        painter.save()
        painter.translate(
            width * 0.94,
            center_y + 15 * scale,
        )
        painter.rotate(-90)
        painter.drawText(0, 0, "RS")
        painter.restore()

        car_width = max(
            4.0,
            10.0 * scale,
        )
        car_height = max(
            9.0,
            20.0 * scale,
        )
        car_radius = max(
            1.0,
            3.0 * scale,
        )

        painter.setBrush(
            QBrush(QColor(0, 0, 0))
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(
            QRectF(
                center_x - car_width / 2,
                center_y - car_height / 2,
                car_width,
                car_height,
            ),
            car_radius,
            car_radius,
        )

        for car in self.cars_data:
            raw_pos_x = float(car.raw_pos_x)
            raw_pos_y = float(car.raw_pos_y)

            if (
                abs(raw_pos_x) < 0.001
                and abs(raw_pos_y) < 0.001
            ):
                continue

            pos_y = (
                center_y
                + raw_pos_y
                * (
                    height / 2.0
                    / max_radar_distance
                )
            )
            pos_x = (
                center_x
                + raw_pos_x
                * 5.2
                * scale
            )

            horizontal_margin = max(
                car_width / 2 + 1,
                width * 0.38,
            )
            pos_x = max(
                horizontal_margin,
                min(
                    width - horizontal_margin,
                    pos_x,
                ),
            )
            pos_y = max(
                car_height / 2,
                min(
                    height - car_height / 2,
                    pos_y,
                ),
            )

            car_color = (
                QColor(25, 118, 210)
                if (
                    self.is_blue_radar
                    or car.is_blue_context
                )
                else QColor(229, 57, 53)
            )

            painter.setBrush(
                QBrush(car_color)
            )
            painter.setPen(
                Qt.PenStyle.NoPen
            )
            painter.drawRoundedRect(
                QRectF(
                    pos_x - car_width / 2,
                    pos_y - car_height / 2,
                    car_width,
                    car_height,
                ),
                car_radius,
                car_radius,
            )


class FlagsWidget(QWidget):
    """
    Mesma janela do arquivo de referência, agora totalmente responsiva.

    A largura controla proporcionalmente:
    - letras;
    - cápsulas;
    - margens;
    - bordas;
    - radar;
    - carros;
    - altura total da janela.
    """

    geometry_changed = Signal(
        str,
        float,
        float,
        float,
        float,
    )
    selected = Signal(str)

    BASE_WIDTH = 520.0
    BASE_FONT_SIZE = 16.0

    def __init__(
        self,
        widget_id: str,
        config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.widget_id = widget_id
        self.config = config
        self.logic = FlagsLogic(config)
        self.snapshot = FlagsSnapshot()

        self.edit_mode = False
        self.yellow_ativa = False
        self.blue_ativa = False
        self.green_ativa = False
        self.widget_visivel = False
        self.tempo_ultima_ativacao = 0.0
        self.ultimo_timestamp = 0

        self._dragging = False
        self._resizing = False
        self._drag_offset = QPoint()
        self._resize_start_global = QPoint()
        self._resize_start_width = 0
        self._resize_start_height = 0

        self._responsive_scale = 1.0
        self._metrics_pending = False
        self._fitting = False

        self.setWindowTitle(
            "Sector Flow Drive - Flags V3"
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.setMinimumWidth(220)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        self.main_layout.setSpacing(0)

        self._build_reference_ui()
        self.apply_config()

        self.visibility_timer = QTimer(self)
        self.visibility_timer.timeout.connect(
            self.verificar_visibilidade_widget
        )
        self.visibility_timer.start(100)

    def _build_reference_ui(self) -> None:
        self.yellow_card = QFrame()
        self.yellow_card.setObjectName(
            "YellowCard"
        )
        self.yellow_card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.yellow_outer = QVBoxLayout(
            self.yellow_card
        )

        self.yellow_top = QHBoxLayout()
        self.yellow_category_frame, self.yellow_category = (
            self._create_info_pill(
                "Categoria",
                "yellow_light",
            )
        )
        self.yellow_driver_frame, self.yellow_driver = (
            self._create_info_pill(
                "Piloto",
                "yellow_light",
            )
        )
        self.yellow_position_frame, self.yellow_position = (
            self._create_info_pill(
                "Posição",
                "yellow_light",
            )
        )
        self.yellow_top.addWidget(
            self.yellow_category_frame
        )
        self.yellow_top.addWidget(
            self.yellow_driver_frame,
            stretch=1,
        )
        self.yellow_top.addWidget(
            self.yellow_position_frame
        )

        self.yellow_distance_frame = QFrame()
        self.yellow_distance_layout = QVBoxLayout(
            self.yellow_distance_frame
        )
        self.yellow_distance_title = self._label(
            "Distância/Tempo",
            title=True,
        )
        self.yellow_distance = self._label(
            "---",
            value=True,
        )
        self.yellow_distance_layout.addWidget(
            self.yellow_distance_title
        )
        self.yellow_distance_layout.addWidget(
            self.yellow_distance
        )

        self.yellow_radar_frame = QFrame()
        self.yellow_radar_layout = QVBoxLayout(
            self.yellow_radar_frame
        )
        self.yellow_radar = RadarWidget(
            is_blue_radar=False
        )
        self.yellow_radar_layout.addWidget(
            self.yellow_radar,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

        self.yellow_outer.addLayout(
            self.yellow_top
        )
        self.yellow_outer.addWidget(
            self.yellow_distance_frame,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        self.yellow_outer.addWidget(
            self.yellow_radar_frame
        )

        self.main_layout.addWidget(
            self.yellow_card
        )
        self.yellow_card.hide()

        self.blue_card = QFrame()
        self.blue_card.setObjectName(
            "BlueCard"
        )
        self.blue_card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.blue_outer = QVBoxLayout(
            self.blue_card
        )

        self.blue_top = QHBoxLayout()
        self.blue_category_frame, self.blue_category = (
            self._create_info_pill(
                "Categoria",
                "blue_light",
            )
        )
        self.blue_driver_frame, self.blue_driver = (
            self._create_info_pill(
                "Piloto",
                "blue_light",
            )
        )
        self.blue_position_frame, self.blue_position = (
            self._create_info_pill(
                "Posição",
                "blue_light",
            )
        )
        self.blue_top.addWidget(
            self.blue_category_frame
        )
        self.blue_top.addWidget(
            self.blue_driver_frame,
            stretch=1,
        )
        self.blue_top.addWidget(
            self.blue_position_frame
        )

        self.blue_distance_frame = QFrame()
        self.blue_distance_layout = QVBoxLayout(
            self.blue_distance_frame
        )
        self.blue_distance_title = self._label(
            "Distância",
            title=True,
        )
        self.blue_distance = self._label(
            "---",
            value=True,
        )
        self.blue_distance_layout.addWidget(
            self.blue_distance_title
        )
        self.blue_distance_layout.addWidget(
            self.blue_distance
        )

        self.blue_radar_frame = QFrame()
        self.blue_radar_layout = QVBoxLayout(
            self.blue_radar_frame
        )
        self.blue_radar = RadarWidget(
            is_blue_radar=True
        )
        self.blue_radar_layout.addWidget(
            self.blue_radar,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

        self.blue_outer.addLayout(
            self.blue_top
        )
        self.blue_outer.addWidget(
            self.blue_distance_frame,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        self.blue_outer.addWidget(
            self.blue_radar_frame
        )

        self.main_layout.addWidget(
            self.blue_card
        )
        self.blue_card.hide()

        self.green_flag = QLabel(
            "◆ GREEN FLAG ◆"
        )
        self.green_flag.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.green_flag.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.main_layout.addWidget(
            self.green_flag
        )
        self.green_flag.hide()

    def _create_info_pill(
        self,
        title_text: str,
        color_key: str,
    ) -> tuple[QFrame, QLabel]:
        frame = QFrame()
        frame.setProperty(
            "pillColorKey",
            color_key,
        )
        frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            10,
            6,
            10,
            6,
        )
        layout.setSpacing(1)

        title = self._label(
            title_text,
            title=True,
        )
        value = self._label(
            "---",
            value=True,
        )
        layout.addWidget(title)
        layout.addWidget(value)

        frame._flags_layout = layout  # type: ignore[attr-defined]
        return frame, value

    @staticmethod
    def _label(
        text: str,
        title: bool = False,
        value: bool = False,
    ) -> QLabel:
        label = QLabel(text)
        label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        label.setWordWrap(False)

        if title:
            label.setProperty(
                "flagTitle",
                True,
            )

        if value:
            label.setProperty(
                "flagValue",
                True,
            )

        return label

    def apply_config(self) -> None:
        self.logic.update_config(
            self.config
        )
        self.setWindowOpacity(
            max(
                0.10,
                min(
                    1.0,
                    float(
                        self.config.get(
                            "opacity",
                            1.0,
                        )
                    ),
                ),
            )
        )
        self._schedule_responsive_update()

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
                        0.28,
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
                    0.36,
                )
            )
        )
        y = int(
            screen_geometry.top()
            + screen_geometry.height()
            * float(
                position.get(
                    "y",
                    0.08,
                )
            )
        )

        self.resize(
            width,
            max(
                50,
                self.height(),
            ),
        )
        self.move(x, y)
        self._schedule_responsive_update()

    def resizeEvent(
        self,
        event: QResizeEvent,
    ) -> None:
        super().resizeEvent(event)
        self._schedule_responsive_update()

    def _schedule_responsive_update(
        self,
    ) -> None:
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

        minimum_scale = max(
            0.35,
            float(
                self.config.get(
                    "responsive_min_scale",
                    0.48,
                )
            ),
        )
        maximum_scale = max(
            minimum_scale,
            float(
                self.config.get(
                    "responsive_max_scale",
                    2.20,
                )
            ),
        )
        internal_scale = max(
            0.50,
            float(
                self.config.get(
                    "internal_scale",
                    1.0,
                )
            ),
        )

        self._responsive_scale = max(
            minimum_scale,
            min(
                maximum_scale,
                (
                    self.width()
                    / self.BASE_WIDTH
                )
                * internal_scale,
            ),
        )
        s = self._responsive_scale

        outer_margin = max(
            2,
            round(5 * s),
        )
        outer_spacing = max(
            2,
            round(5 * s),
        )
        top_spacing = max(
            3,
            round(10 * s),
        )
        pill_h_margin = max(
            4,
            round(10 * s),
        )
        pill_v_margin = max(
            3,
            round(6 * s),
        )
        distance_h_margin = max(
            6,
            round(20 * s),
        )
        radar_v_margin = max(
            3,
            round(10 * s),
        )

        for outer in (
            self.yellow_outer,
            self.blue_outer,
        ):
            outer.setContentsMargins(
                outer_margin,
                outer_margin,
                outer_margin,
                outer_margin,
            )
            outer.setSpacing(
                outer_spacing
            )

        for top in (
            self.yellow_top,
            self.blue_top,
        ):
            top.setSpacing(top_spacing)

        for frame in (
            self.yellow_category_frame,
            self.yellow_driver_frame,
            self.yellow_position_frame,
            self.blue_category_frame,
            self.blue_driver_frame,
            self.blue_position_frame,
        ):
            layout = frame._flags_layout  # type: ignore[attr-defined]
            layout.setContentsMargins(
                pill_h_margin,
                pill_v_margin,
                pill_h_margin,
                pill_v_margin,
            )
            layout.setSpacing(
                max(
                    0,
                    round(1 * s),
                )
            )

        for layout in (
            self.yellow_distance_layout,
            self.blue_distance_layout,
        ):
            layout.setContentsMargins(
                distance_h_margin,
                pill_v_margin,
                distance_h_margin,
                pill_v_margin,
            )
            layout.setSpacing(
                max(
                    0,
                    round(1 * s),
                )
            )

        for layout in (
            self.yellow_radar_layout,
            self.blue_radar_layout,
        ):
            layout.setContentsMargins(
                0,
                radar_v_margin,
                0,
                radar_v_margin,
            )

        category_min = max(
            48,
            round(92 * s),
        )
        position_min = max(
            42,
            round(74 * s),
        )

        for frame in (
            self.yellow_category_frame,
            self.blue_category_frame,
        ):
            frame.setMinimumWidth(
                category_min
            )

        for frame in (
            self.yellow_position_frame,
            self.blue_position_frame,
        ):
            frame.setMinimumWidth(
                position_min
            )

        self.yellow_radar.set_ui_scale(s)
        self.blue_radar.set_ui_scale(s)
        self._apply_reference_style(s)

        QTimer.singleShot(
            0,
            self._fit_content,
        )

    def _apply_reference_style(
        self,
        scale: float,
    ) -> None:
        colors = self.config.get(
            "colors",
            {},
        )
        yellow_bg = colors.get(
            "yellow_bg",
            "#FFEA00",
        )
        yellow_light = colors.get(
            "yellow_light",
            "#FFF59D",
        )
        blue_bg = colors.get(
            "blue_bg",
            "#1E88E5",
        )
        blue_light = colors.get(
            "blue_light",
            "#81D4FA",
        )
        green_bg = colors.get(
            "green_bg",
            "#00AA00",
        )
        green_fg = colors.get(
            "green_fg",
            "#FFFFFF",
        )

        base_font = max(
            8.0,
            float(
                self.config.get(
                    "font_size",
                    self.BASE_FONT_SIZE,
                )
            ),
        )
        title_size = max(
            6,
            round(
                base_font
                * 0.60
                * scale
            ),
        )
        value_size = max(
            7,
            round(
                base_font
                * 0.90
                * scale
            ),
        )
        green_size = max(
            8,
            round(
                base_font
                * 1.25
                * scale
            ),
        )
        radius_card = max(
            5,
            round(16 * scale),
        )
        radius_pill = max(
            4,
            round(12 * scale),
        )
        radius_radar = max(
            4,
            round(16 * scale),
        )
        green_padding_v = max(
            3,
            round(8 * scale),
        )
        green_padding_h = max(
            5,
            round(12 * scale),
        )
        family = str(
            self.config.get(
                "font_name",
                "Arial",
            )
        )

        self.setStyleSheet(
            f"""
            FlagsWidget {{
                background: transparent;
                border: none;
            }}

            QFrame#YellowCard {{
                background-color: {yellow_bg};
                border-radius: {radius_card}px;
            }}

            QFrame#BlueCard {{
                background-color: {blue_bg};
                border-radius: {radius_card}px;
            }}

            QFrame[pillColorKey="yellow_light"] {{
                background-color: {yellow_light};
                border-radius: {radius_pill}px;
            }}

            QFrame[pillColorKey="blue_light"] {{
                background-color: {blue_light};
                border-radius: {radius_pill}px;
            }}

            QLabel {{
                color: #000000;
                font-family: "{family}";
                background: transparent;
            }}

            QLabel[flagTitle="true"] {{
                font-size: {title_size}px;
                font-weight: bold;
            }}

            QLabel[flagValue="true"] {{
                font-size: {value_size}px;
                font-weight: 900;
            }}
            """
        )

        self.yellow_distance_frame.setStyleSheet(
            f"""
            background-color: {yellow_light};
            border-radius: {radius_pill}px;
            """
        )
        self.yellow_radar_frame.setStyleSheet(
            f"""
            background-color: {yellow_light};
            border-radius: {radius_radar}px;
            """
        )
        self.blue_distance_frame.setStyleSheet(
            f"""
            background-color: {blue_light};
            border-radius: {radius_pill}px;
            """
        )
        self.blue_radar_frame.setStyleSheet(
            f"""
            background-color: {blue_light};
            border-radius: {radius_radar}px;
            """
        )
        self.green_flag.setStyleSheet(
            f"""
            QLabel {{
                color: {green_fg};
                background-color: {green_bg};
                border-radius: {radius_pill}px;
                padding: {green_padding_v}px {green_padding_h}px;
                font-family: "{family}";
                font-size: {green_size}px;
                font-weight: 900;
            }}
            """
        )

    def update_from_session(
        self,
        session: Any,
    ) -> None:
        # Durante a edição, a telemetria não deve ocultar nem substituir
        # o quadro usado para posicionar e redimensionar o widget.
        if self.edit_mode:
            if not self.isVisible():
                self.show()
            self.widget_visivel = True
            self.update()
            return

        simulated = self._read_simulation_file()

        self.snapshot = (
            simulated
            if simulated is not None
            else self.logic.update(session)
        )
        self._render_snapshot()

    def _render_snapshot(self) -> None:
        yellow = self.snapshot.yellow
        blue = self.snapshot.blue

        # Caso 1: amarelo tem prioridade.
        if yellow.active:
            self.blue_card.hide()

            self.yellow_category.setText(
                yellow.category
            )
            self.yellow_driver.setText(
                yellow.driver
            )
            self.yellow_position.setText(
                f"P{yellow.position}"
                if yellow.position > 0
                else "---"
            )

            if yellow.distance < 0:
                self.yellow_distance.setText(
                    f"Atrás: "
                    f"{abs(int(yellow.distance))}m"
                )
            elif yellow.distance <= 350:
                self.yellow_distance.setText(
                    f"Frente: "
                    f"{int(yellow.distance)}m"
                )
            else:
                self.yellow_distance.setText(
                    f"Frente: "
                    f"{yellow.tempo_gap:.1f}s"
                )

            self.yellow_radar.update_radar_data(
                yellow.cars
            )
            self.yellow_card.show()
            self.yellow_ativa = True

            colors = self.config.get(
                "colors",
                {},
            )
            yellow_bg = colors.get(
                "yellow_bg",
                "#FFEA00",
            )
            blue_bg = colors.get(
                "blue_bg",
                "#1E88E5",
            )
            radius = max(
                5,
                round(
                    16
                    * self._responsive_scale
                ),
            )

            if blue.active:
                border = max(
                    3,
                    round(
                        8
                        * self._responsive_scale
                    ),
                )
                self.yellow_card.setStyleSheet(
                    f"""
                    QFrame#YellowCard {{
                        background-color: {yellow_bg};
                        border-radius: {radius}px;
                        border-bottom: {border}px
                        solid {blue_bg};
                    }}
                    """
                )
                self.blue_ativa = True
            else:
                self.yellow_card.setStyleSheet(
                    f"""
                    QFrame#YellowCard {{
                        background-color: {yellow_bg};
                        border-radius: {radius}px;
                    }}
                    """
                )
                self.blue_ativa = False

        # Caso 2: somente azul.
        elif blue.active:
            self.yellow_card.hide()
            self.yellow_ativa = False

            self.blue_category.setText(
                blue.category
            )
            self.blue_driver.setText(
                blue.driver
            )
            self.blue_position.setText(
                f"P{blue.position}"
                if blue.position > 0
                else "---"
            )
            self.blue_distance.setText(
                f" {abs(int(blue.distance))}m"
            )
            self.blue_radar.update_radar_data(
                blue.cars
            )
            self.blue_card.show()
            self.blue_ativa = True

        # Caso 3: pista limpa.
        else:
            self.yellow_card.hide()
            self.blue_card.hide()
            self.yellow_ativa = False
            self.blue_ativa = False

        if self.snapshot.green_active:
            self.green_flag.show()
            self.green_ativa = True
        else:
            self.green_flag.hide()
            self.green_ativa = False

        self.verificar_visibilidade_widget()
        self._schedule_responsive_update()

    def verificar_visibilidade_widget(
        self,
    ) -> None:
        agora = time.time()
        alguma_ativa = (
            self.yellow_ativa
            or self.blue_ativa
            or self.green_ativa
        )

        if self.edit_mode:
            if not self.widget_visivel:
                self.show()
                self.widget_visivel = True
            return

        if alguma_ativa:
            if not self.widget_visivel:
                self.show()
                self.widget_visivel = True

            self.tempo_ultima_ativacao = agora
            return

        if not bool(
            self.config.get(
                "auto_hide_when_clear",
                True,
            )
        ):
            if not self.widget_visivel:
                self.show()
                self.widget_visivel = True
            return

        duracao = max(
            0.0,
            float(
                self.config.get(
                    "duracao_minima_visivel",
                    1.0,
                )
            ),
        )

        if (
            self.widget_visivel
            and (
                agora
                - self.tempo_ultima_ativacao
            )
            >= duracao
        ):
            self.hide()
            self.widget_visivel = False

    def set_edit_mode(
        self,
        enabled: bool,
    ) -> None:
        self.edit_mode = bool(enabled)

        if self.edit_mode:
            # Exibe uma bandeira amarela de exemplo para facilitar o
            # posicionamento e o redimensionamento durante a edição.
            self.snapshot = self.logic.preview("yellow")
            self._render_snapshot()
            self.show()
            self.widget_visivel = True
            self.setCursor(
                Qt.CursorShape.SizeAllCursor
            )
        else:
            self.setCursor(
                Qt.CursorShape.ArrowCursor
            )
            # Remove imediatamente a prévia usada apenas na edição. Uma
            # bandeira real voltará a aparecer na próxima telemetria.
            self.snapshot = FlagsSnapshot()
            self.yellow_ativa = False
            self.blue_ativa = False
            self.green_ativa = False
            self.yellow_card.hide()
            self.blue_card.hide()
            self.green_flag.hide()

            if bool(
                self.config.get(
                    "auto_hide_when_clear",
                    True,
                )
            ):
                self.hide()
                self.widget_visivel = False
            else:
                self.show()
                self.widget_visivel = True

        self.update()

    def reset_session_state(self) -> None:
        self.logic.reset()
        self.snapshot = FlagsSnapshot()
        self.yellow_ativa = False
        self.blue_ativa = False
        self.green_ativa = False
        self.yellow_card.hide()
        self.blue_card.hide()
        self.green_flag.hide()
        self.verificar_visibilidade_widget()
        self._schedule_responsive_update()

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
        pen = QPen(
            QColor("#9B5CFF"),
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
            max(
                5.0,
                12.0
                * self._responsive_scale,
            ),
            max(
                5.0,
                12.0
                * self._responsive_scale,
            ),
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
            self._resize_start_width = self.width()
            self._resize_start_height = (
                self.height()
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

            # Aceita arrastar pela horizontal ou vertical.
            width_from_x = (
                self._resize_start_width
                + delta.x()
            )
            aspect = max(
                1.2,
                self._resize_start_width
                / max(
                    1,
                    self._resize_start_height,
                ),
            )
            width_from_y = (
                self._resize_start_width
                + delta.y() * aspect
            )
            chosen = (
                width_from_x
                if abs(delta.x())
                >= abs(delta.y())
                else width_from_y
            )

            self.resize(
                max(
                    self.minimumWidth(),
                    round(chosen),
                ),
                self.height(),
            )
            self._schedule_responsive_update()
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
            self._emit_normalized_geometry()
            event.accept()
        else:
            event.ignore()

    def _fit_content(self) -> None:
        if self._fitting:
            return

        self._fitting = True
        self.main_layout.activate()

        desired = max(
            1,
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

    def _emit_normalized_geometry(
        self,
    ) -> None:
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

    def _read_simulation_file(
        self,
    ) -> FlagsSnapshot | None:
        path = PROJECT_ROOT / str(
            self.config.get(
                "simulation_file",
                "simulacao_flags.json",
            )
        )

        if not path.exists():
            return None

        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            return None

        timestamp = int(
            data.get(
                "timestamp",
                0,
            )
            or 0
        )

        if timestamp == self.ultimo_timestamp:
            return None

        self.ultimo_timestamp = timestamp

        if (
            data.get(
                "modo",
                "real",
            )
            != "simulacao"
        ):
            return None

        state = data.get(
            "estado",
            {},
        )
        mode = str(
            state.get(
                "flag",
                "yellow",
            )
        ).lower()
        return self.logic.preview(mode)
