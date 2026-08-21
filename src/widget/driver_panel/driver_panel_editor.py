from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QColorDialog,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class DriverPanelEditor(QDialog):
    config_changed = Signal(dict)
    restore_requested = Signal()

    def __init__(
        self,
        config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("Editar Telemetry")
        self.resize(550, 720)
        self.config = deepcopy(config)
        self._color_buttons: dict[str, QPushButton] = {}

        root = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)

        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        scroll.setWidget(content)

        self._build_size_group()
        self._build_elements_group()
        self._build_pedals_group()
        self._build_graph_group()
        self._build_rpm_group()
        self._build_steering_group()
        self._build_appearance_group()

        buttons = QHBoxLayout()

        restore = QPushButton("Restaurar padrão")
        close = QPushButton("Fechar")

        restore.clicked.connect(
            self.restore_requested.emit
        )
        close.clicked.connect(self.accept)

        buttons.addWidget(restore)
        buttons.addStretch()
        buttons.addWidget(close)

        root.addLayout(buttons)

    def _build_elements_group(self) -> None:
        group = QGroupBox("Elementos visíveis")
        form = QFormLayout(group)
        elements = self.config.setdefault("elements", {})
        for key, label in (
            ("rpm", "RPM e barra"),
            ("graph", "Gráfico em tempo real"),
            ("steering", "Volante e ângulo"),
            ("steering_marker", "Marcador do volante"),
            ("gear", "Marcha no volante"),
            ("speed", "Velocidade no volante"),
            ("pedals", "Barras dos pedais"),
        ):
            check = QCheckBox()
            check.setChecked(bool(elements.get(key, True)))
            check.toggled.connect(
                lambda value, k=key: self._set_nested("elements", k, value)
            )
            form.addRow(label + ":", check)

        speed_unit = QComboBox()
        speed_unit.addItems(("km/h", "mph"))
        speed_unit.setCurrentText(str(self.config.get("speed_unit", "km/h")))
        speed_unit.currentTextChanged.connect(lambda value: self._set_root("speed_unit", value))
        form.addRow("Unidade de velocidade:", speed_unit)

        speed_position = QComboBox()
        speed_position.addItem("Dentro do volante", "inside")
        speed_position.addItem("Ao lado da marcha", "beside_gear")
        current_position = str(self.config.get("speed_position", "inside"))
        speed_position.setCurrentIndex(max(0, speed_position.findData(current_position)))
        speed_position.currentIndexChanged.connect(
            lambda _index: self._set_root("speed_position", speed_position.currentData())
        )
        form.addRow("Posição da velocidade:", speed_position)

        style = QComboBox()
        style.addItems(("Circular", "GT", "Fórmula", "Somente ângulo", "Imagem personalizada"))
        style.setCurrentText(str(self.config.get("steering_style", "Circular")))
        style.currentTextChanged.connect(lambda value: self._set_root("steering_style", value))
        form.addRow("Estilo do volante:", style)

        image_row = QHBoxLayout()
        image_path = QLineEdit(str(self.config.get("custom_wheel_image", "")))
        choose = QPushButton("Escolher…")
        def choose_image() -> None:
            path, _ = QFileDialog.getOpenFileName(self, "Imagem do volante", "", "Imagens (*.png *.jpg *.jpeg *.webp)")
            if path:
                image_path.setText(path)
                self._set_root("custom_wheel_image", path)
        choose.clicked.connect(choose_image)
        image_path.editingFinished.connect(lambda: self._set_root("custom_wheel_image", image_path.text().strip()))
        image_row.addWidget(image_path); image_row.addWidget(choose)
        form.addRow("Imagem personalizada:", image_row)
        self.content_layout.addWidget(group)

    def _build_pedals_group(self) -> None:
        group = QGroupBox("Barras individuais dos pedais")
        form = QFormLayout(group)
        pedal_elements = self.config.setdefault("pedal_elements", {})
        for key, label in (
            ("throttle", "Mostrar acelerador"),
            ("brake", "Mostrar freio"),
            ("clutch", "Mostrar embreagem"),
        ):
            check = QCheckBox()
            check.setChecked(bool(pedal_elements.get(key, True)))
            check.toggled.connect(
                lambda value, k=key: self._set_nested("pedal_elements", k, value)
            )
            form.addRow(label + ":", check)

        width = QDoubleSpinBox()
        width.setRange(8.0, 80.0)
        width.setSingleStep(2.0)
        width.setSuffix(" px")
        width.setValue(float(self.config.get("pedal_bar_width", 38.0)))
        width.valueChanged.connect(
            lambda value: self._set_root("pedal_bar_width", value)
        )
        form.addRow("Largura das barras:", width)

        gap = QDoubleSpinBox()
        gap.setRange(0.0, 40.0)
        gap.setSingleStep(1.0)
        gap.setSuffix(" px")
        gap.setValue(float(self.config.get("pedal_bar_gap", 9.0)))
        gap.valueChanged.connect(
            lambda value: self._set_root("pedal_bar_gap", value)
        )
        form.addRow("Espaço entre barras:", gap)
        self.content_layout.addWidget(group)

    def _build_size_group(self) -> None:
        group = QGroupBox("Tamanho e posição")
        form = QFormLayout(group)

        for section, key, label, default in (
            ("position", "x", "X:", 0.14),
            ("position", "y", "Y:", 0.66),
            ("size", "width", "Largura:", 0.72),
            ("size", "height", "Altura:", 0.30),
        ):
            value = self.config.get(
                section,
                {},
            ).get(key, default)

            spin = self._percent_spin(value)
            spin.valueChanged.connect(
                lambda v, s=section, k=key:
                self._set_nested(s, k, v / 100)
            )
            form.addRow(label, spin)

        scale = QDoubleSpinBox()
        scale.setRange(0.25, 2.50)
        scale.setSingleStep(0.05)
        scale.setValue(
            float(self.config.get("scale", 1.0))
        )
        scale.valueChanged.connect(
            lambda v: self._set_root("scale", v)
        )

        form.addRow("Escala geral:", scale)
        self.content_layout.addWidget(group)

    def _build_graph_group(self) -> None:
        group = QGroupBox(
            "Gráfico de acelerador e freio"
        )
        form = QFormLayout(group)

        interval = QComboBox()
        interval.addItems(("5 s", "10 s", "30 s", "Volta", "Sessão"))
        interval.setCurrentText(str(self.config.get("graph_interval", "10 s")))
        interval.currentTextChanged.connect(lambda value: self._set_root("graph_interval", value))
        form.addRow("Intervalo exibido:", interval)

        history = QSpinBox()
        history.setRange(30, 1200)
        history.setSingleStep(30)
        history.setValue(
            int(
                self.config.get(
                    "graph_history_points",
                    240,
                )
            )
        )
        history.valueChanged.connect(
            lambda v:
            self._set_root(
                "graph_history_points",
                v,
            )
        )

        vertical = QSpinBox()
        vertical.setRange(2, 20)
        vertical.setValue(
            int(
                self.config.get(
                    "graph_vertical_lines",
                    8,
                )
            )
        )
        vertical.valueChanged.connect(
            lambda v:
            self._set_root(
                "graph_vertical_lines",
                v,
            )
        )

        form.addRow(
            "Pontos no histórico:",
            history,
        )
        form.addRow(
            "Linhas verticais:",
            vertical,
        )

        self.content_layout.addWidget(group)

    def _build_rpm_group(self) -> None:
        group = QGroupBox(
            "Barra segmentada de RPM"
        )
        form = QFormLayout(group)

        layout = self.config.setdefault(
            "layout",
            {},
        )

        segments = QSpinBox()
        segments.setRange(10, 60)
        segments.setValue(
            int(layout.get("rpm_segments", 28))
        )
        segments.valueChanged.connect(
            lambda v:
            self._set_nested(
                "layout",
                "rpm_segments",
                v,
            )
        )

        shift = QDoubleSpinBox()
        shift.setRange(0.50, 0.95)
        shift.setSingleStep(0.01)
        shift.setValue(
            float(layout.get("shift_start", 0.78))
        )
        shift.valueChanged.connect(
            lambda v:
            self._set_nested(
                "layout",
                "shift_start",
                v,
            )
        )

        red = QDoubleSpinBox()
        red.setRange(0.70, 1.00)
        red.setSingleStep(0.01)
        red.setValue(
            float(layout.get("red_start", 0.92))
        )
        red.valueChanged.connect(
            lambda v:
            self._set_nested(
                "layout",
                "red_start",
                v,
            )
        )

        form.addRow("Segmentos:", segments)
        form.addRow(
            "Começo do amarelo:",
            shift,
        )
        form.addRow(
            "Começo do vermelho:",
            red,
        )

        self.content_layout.addWidget(group)

    def _build_steering_group(self) -> None:
        group = QGroupBox("Volante")
        form = QFormLayout(group)

        angle = QSpinBox()
        angle.setRange(45, 540)
        angle.setSuffix("°")
        angle.setValue(
            int(
                self.config.get(
                    "steering_visual_degrees",
                    180,
                )
            )
        )
        angle.valueChanged.connect(
            lambda v:
            self._set_root(
                "steering_visual_degrees",
                v,
            )
        )

        form.addRow(
            "Rotação visual máxima:",
            angle,
        )

        for key, label, minimum, maximum in (
            ("steering_size_scale", "Tamanho do volante", 35, 200),
            ("speed_font_scale", "Fonte da velocidade", 35, 300),
            ("gear_font_scale", "Fonte da marcha", 35, 300),
        ):
            size = QSpinBox()
            size.setRange(minimum, maximum)
            size.setSingleStep(5)
            size.setSuffix("%")
            size.setValue(round(float(self.config.get(key, 1.0)) * 100))
            size.valueChanged.connect(
                lambda value, k=key: self._set_root(k, value / 100.0)
            )
            form.addRow(label + ":", size)

        smoothing = QDoubleSpinBox()
        smoothing.setRange(0.0, 0.95)
        smoothing.setSingleStep(0.05)
        smoothing.setValue(float(self.config.get("steering_smoothing", 0.32)))
        smoothing.valueChanged.connect(lambda value: self._set_root("steering_smoothing", value))
        form.addRow("Suavização:", smoothing)

        self.content_layout.addWidget(group)

    def _build_appearance_group(self) -> None:
        group = QGroupBox("Aparência")
        form = QFormLayout(group)

        font_cfg = self.config.setdefault(
            "font",
            {},
        )

        font = QComboBox()
        font.addItems(QFontDatabase.families())
        font.setCurrentText(
            str(font_cfg.get("family", "Arial"))
        )
        font.currentTextChanged.connect(
            lambda v:
            self._set_nested(
                "font",
                "family",
                v,
            )
        )

        opacity = QDoubleSpinBox()
        opacity.setRange(0.10, 1.00)
        opacity.setSingleStep(0.05)
        opacity.setValue(
            float(self.config.get("opacity", 0.96))
        )
        opacity.valueChanged.connect(
            lambda v:
            self._set_root("opacity", v)
        )

        background_opacity = QDoubleSpinBox()
        background_opacity.setRange(0.00, 1.00)
        background_opacity.setSingleStep(0.05)
        background_opacity.setValue(
            float(
                self.config.get(
                    "background_opacity",
                    0.88,
                )
            )
        )
        background_opacity.valueChanged.connect(
            lambda v:
            self._set_root(
                "background_opacity",
                v,
            )
        )

        form.addRow("Fonte:", font)
        form.addRow("Opacidade:", opacity)
        form.addRow(
            "Opacidade do fundo:",
            background_opacity,
        )

        for key, label in (
            ("text", "Texto"),
            ("muted", "Texto secundário"),
            ("background", "Fundo"),
            ("panel", "Painéis internos"),
            ("grid", "Grade"),
            ("rpm_low", "RPM azul"),
            ("rpm_shift", "RPM amarelo"),
            ("rpm_high", "RPM vermelho"),
            ("throttle", "Acelerador"),
            ("brake", "Freio"),
            ("clutch", "Embreagem"),
            ("speed", "Velocidade"),
            ("rpm_graph", "RPM no gráfico"),
            ("steering_graph", "Volante no gráfico"),
            ("wheel", "Volante"),
            ("steering_center", "Linha central"),
            ("steering_marker", "Marca do volante"),
            ("border", "Borda"),
        ):
            button = QPushButton(
                self.config.setdefault(
                    "colors",
                    {},
                ).get(key, "#FFFFFF")
            )
            button.clicked.connect(
                lambda checked=False, k=key:
                self._choose_color(k)
            )
            form.addRow(label + ":", button)
            self._color_buttons[key] = button

        self.content_layout.addWidget(group)
        self.content_layout.addStretch()

    def _percent_spin(
        self,
        normalized: float,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, 100)
        spin.setDecimals(1)
        spin.setSuffix("%")
        spin.setValue(float(normalized) * 100)
        return spin

    def _set_nested(
        self,
        section: str,
        key: str,
        value: Any,
    ) -> None:
        self.config.setdefault(
            section,
            {},
        )[key] = value

        self.config_changed.emit(
            deepcopy(self.config)
        )

    def _set_root(
        self,
        key: str,
        value: Any,
    ) -> None:
        self.config[key] = value

        self.config_changed.emit(
            deepcopy(self.config)
        )

    def _choose_color(
        self,
        key: str,
    ) -> None:
        current = QColor(
            self.config.setdefault(
                "colors",
                {},
            ).get(key, "#FFFFFF")
        )

        color = QColorDialog.getColor(
            current,
            self,
        )

        if not color.isValid():
            return

        value = color.name(
            QColor.NameFormat.HexRgb
        )

        self.config["colors"][key] = value
        self._color_buttons[key].setText(value)

        self.config_changed.emit(
            deepcopy(self.config)
        )
