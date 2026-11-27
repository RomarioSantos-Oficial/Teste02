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
    QLabel,
    QPushButton,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.i18n import tr


class DriverPanelEditor(QDialog):
    config_changed = Signal(dict)
    geometry_changed = Signal(str, str, object)
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
            path, _ = QFileDialog.getOpenFileName(
                self,
                tr("Imagem do volante"),
                "",
                tr("Imagens (*.png *.jpg *.jpeg *.webp)"),
            )
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

        for key, label in (
            ("pedal_show_labels", "Mostrar identificação dos pedais"),
            ("pedal_show_peaks", "Mostrar marcador do pico máximo"),
        ):
            check = QCheckBox()
            check.setChecked(bool(self.config.get(key, True)))
            check.toggled.connect(lambda value, k=key: self._set_root(k, value))
            form.addRow(label + ":", check)

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
                self._set_geometry_nested(s, k, v / 100)
            )
            form.addRow(label, spin)

        scale = QDoubleSpinBox()
        scale.setRange(0.25, 2.50)
        scale.setSingleStep(0.05)
        scale.setValue(
            float(self.config.get("scale", 1.0))
        )
        scale.valueChanged.connect(
            lambda v: self._set_geometry_root("scale", v)
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
        interval.setCurrentText(
            "Volta" if bool(self.config.get("compare_personal_best", False))
            else str(self.config.get("graph_interval", "10 s"))
        )
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

        for key, label, default in (
            ("throttle_line_width", "Espessura do acelerador:", 3.6),
            ("brake_line_width", "Espessura do freio:", 3.6),
            ("clutch_line_width", "Espessura da embreagem:", 3.4),
            ("reference_line_width", "Espessura da melhor volta:", 2.0),
        ):
            line_width = QDoubleSpinBox()
            line_width.setRange(1.0, 9.0)
            line_width.setSingleStep(0.2)
            line_width.setDecimals(1)
            line_width.setSuffix(" px")
            line_width.setValue(float(self.config.get(key, default)))
            line_width.valueChanged.connect(
                lambda value, k=key: self._set_root(k, value)
            )
            form.addRow(label, line_width)

        for key, label in (
            ("graph_show_grid", "Mostrar grade do gráfico"),
            ("graph_show_scale_labels", "Mostrar escala numérica"),
            ("graph_extrema_markers", "Destacar pontos mínimo e máximo do acelerador"),
            ("graph_curve_glow", "Realce suave das linhas"),
        ):
            check = QCheckBox()
            check.setChecked(bool(self.config.get(key, True)))
            check.toggled.connect(lambda value, k=key: self._set_root(k, value))
            form.addRow(label + ":", check)

        compare_best = QCheckBox("Comparar com minha melhor volta salva")
        compare_best.setChecked(bool(self.config.get("compare_personal_best", False)))
        def set_compare_best(enabled: bool) -> None:
            self._set_root("compare_personal_best", enabled)
            if enabled:
                interval.setCurrentText("Volta")

        compare_best.toggled.connect(set_compare_best)
        scope = QComboBox()
        scope.addItem("Categoria (qualquer carro)", "category")
        scope.addItem("Mesmo modelo de carro", "model")
        scope.setCurrentIndex(max(0, scope.findData(str(self.config.get("personal_best_scope", "category")))))
        scope.currentIndexChanged.connect(
            lambda index: self._set_root("personal_best_scope", scope.itemData(index))
        )
        form.addRow("Sobrepor curvas da volta:", compare_best)
        form.addRow("Separar por:", scope)
        hint = QLabel("Com a comparação ativa, o gráfico usa a volta atual e sobrepõe sua melhor volta salva.")
        hint.setWordWrap(True)
        form.addRow("", hint)

        self.content_layout.addWidget(group)

    def _build_rpm_group(self) -> None:
        group = QGroupBox("Faixa de RPM e luzes de troca")
        form = QFormLayout(group)
        layout = self.config.setdefault("layout", {})

        segments = QSpinBox()
        segments.setRange(10, 10)
        segments.setValue(10)
        segments.setEnabled(False)
        form.addRow("Blocos da faixa (10):", segments)

        def add_threshold(key: str, label: str, default: float, minimum: float = 0.50) -> None:
            spin = QDoubleSpinBox()
            spin.setRange(minimum, 1.20)
            spin.setSingleStep(0.01)
            spin.setDecimals(0)
            spin.setSuffix("%")
            spin.setValue(float(layout.get(key, default)) * 100.0)
            spin.valueChanged.connect(
                lambda value, config_key=key:
                self._set_nested("layout", config_key, value / 100.0)
            )
            form.addRow(label, spin)

        add_threshold("shift_start", "Acender azul central:", 0.88)
        add_threshold("shift_light_1", "1ª luz superior:", 0.91)
        add_threshold("shift_light_2", "2ª luz superior:", 0.94)
        add_threshold("shift_light_3", "3ª luz superior:", 0.96)
        add_threshold("rpm_flash_start", "Piscar vermelho/roxo (acima de 99%):", 0.99, 0.80)

        flash_interval = QDoubleSpinBox()
        flash_interval.setRange(0.05, 1.00)
        flash_interval.setSingleStep(0.01)
        flash_interval.setDecimals(2)
        flash_interval.setSuffix(" s")
        flash_interval.setValue(float(self.config.get("rpm_flash_interval_s", 0.06)))
        flash_interval.valueChanged.connect(
            lambda value: self._set_root("rpm_flash_interval_s", value)
        )
        form.addRow("Velocidade do pisca:", flash_interval)
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
        font.setEditable(True)
        font.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        font.setCurrentText(
            str(font_cfg.get("family", "Bahnschrift Light"))
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

        font_scale = QDoubleSpinBox()
        font_scale.setRange(0.65, 1.80)
        font_scale.setSingleStep(0.05)
        font_scale.setDecimals(2)
        font_scale.setValue(float(font_cfg.get("scale", 1.0)))
        font_scale.valueChanged.connect(
            lambda value: self._set_nested("font", "scale", value)
        )

        form.addRow("Fonte:", font)
        form.addRow("Escala dos textos:", font_scale)
        form.addRow("Opacidade:", opacity)
        form.addRow(
            "Opacidade do fundo:",
            background_opacity,
        )

        for key, label in (
            ("text", "Texto"),
            ("muted", "Texto secundário"),
            ("background", "Fundo"),
            ("panel", "Painéis internos (padrão)"),
            ("graph_background", "Fundo do gráfico"),
            ("graph_border", "Borda do gráfico"),
            ("pedals_background", "Fundo das barras dos pedais"),
            ("pedals_border", "Borda das barras dos pedais"),
            ("rpm_background", "Fundo da área de RPM"),
            ("rpm_border", "Borda da área de RPM"),
            ("steering_background", "Fundo da área do volante"),
            ("steering_border", "Borda da área do volante"),
            ("pedal_track", "Fundo interno das barras"),
            ("personal_best_throttle", "Melhor volta — acelerador"),
            ("personal_best_brake", "Melhor volta — freio"),
            ("grid", "Grade"),
            ("rpm_green", "RPM verde"),
            ("rpm_yellow", "RPM amarelo"),
            ("rpm_blue", "RPM azul"),
            ("rpm_high", "RPM vermelho"),
            ("gear", "Marcha"),
            ("graph_reference", "Linha superior do gráfico"),
            ("graph_marker", "Pontos de destaque do gráfico"),
            ("rpm_flash", "RPM em alerta (roxo)"),
            ("rpm_value_background", "Fundo da caixa de RPM"),
            ("rpm_value_border", "Borda da caixa de RPM"),
            ("throttle", "Acelerador"),
            ("brake", "Freio"),
            ("clutch", "Embreagem"),
            ("speed", "Velocidade"),
            ("rpm_graph", "RPM no gráfico"),
            ("steering_graph", "Volante no gráfico"),
            ("wheel", "Volante"),
            ("steering_marker", "Bolinha indicadora do volante"),
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

    def _set_geometry_nested(
        self,
        section: str,
        key: str,
        value: Any,
    ) -> None:
        self.config.setdefault(section, {})[key] = value
        self.geometry_changed.emit(section, key, value)

    def _set_geometry_root(
        self,
        key: str,
        value: Any,
    ) -> None:
        self.config[key] = value
        self.geometry_changed.emit("", key, value)

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
