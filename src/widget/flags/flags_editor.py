from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class FlagsEditor(QDialog):
    config_changed = Signal(dict)
    restore_requested = Signal()

    def __init__(
        self,
        config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.config = deepcopy(config)
        self.color_buttons: dict[
            str,
            QPushButton,
        ] = {}

        self.setWindowTitle(
            "Editar Flags V3"
        )
        self.resize(570, 760)

        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)

        content = QWidget()
        self.content_layout = QVBoxLayout(
            content
        )
        scroll.setWidget(content)

        self._build_behavior()
        self._build_detection()
        self._build_responsive()
        self._build_visual()

        actions = QHBoxLayout()
        restore = QPushButton(
            "Restaurar padrão"
        )
        close = QPushButton("Fechar")
        restore.clicked.connect(
            self.restore_requested.emit
        )
        close.clicked.connect(
            self.accept
        )
        actions.addWidget(restore)
        actions.addStretch()
        actions.addWidget(close)
        root.addLayout(actions)

    def _build_behavior(self) -> None:
        group = QGroupBox(
            "Bandeiras e comportamento"
        )
        form = QFormLayout(group)

        for key, label, default in (
            (
                "show_yellow_flag",
                "Bandeira amarela:",
                True,
            ),
            (
                "show_blue_flag",
                "Bandeira azul:",
                True,
            ),
            (
                "show_startlights",
                "Bandeira verde:",
                True,
            ),
            (
                "auto_hide_when_clear",
                "Ocultar sem bandeira:",
                True,
            ),
        ):
            check = QCheckBox()
            check.setChecked(
                bool(
                    self.config.get(
                        key,
                        default,
                    )
                )
            )
            check.toggled.connect(
                lambda value, current=key:
                self._set(
                    current,
                    value,
                )
            )
            form.addRow(label, check)

        duration = QDoubleSpinBox()
        duration.setRange(0.0, 10.0)
        duration.setSingleStep(0.25)
        duration.setSuffix(" s")
        duration.setValue(
            float(
                self.config.get(
                    "duracao_minima_visivel",
                    1.0,
                )
            )
        )
        duration.valueChanged.connect(
            lambda value:
            self._set(
                "duracao_minima_visivel",
                value,
            )
        )

        green_duration = QDoubleSpinBox()
        green_duration.setRange(0.5, 15.0)
        green_duration.setSingleStep(0.5)
        green_duration.setSuffix(" s")
        green_duration.setValue(
            float(
                self.config.get(
                    "green_flag_duration_seconds",
                    3.0,
                )
            )
        )
        green_duration.valueChanged.connect(
            lambda value:
            self._set(
                "green_flag_duration_seconds",
                value,
            )
        )

        preview = QComboBox()
        preview.addItem(
            "Amarela",
            "yellow",
        )
        preview.addItem(
            "Azul",
            "blue",
        )
        preview.addItem(
            "Amarela + azul",
            "yellow_blue",
        )
        preview.addItem(
            "Verde",
            "green",
        )
        index = preview.findData(
            self.config.get(
                "preview_mode",
                "yellow",
            )
        )
        preview.setCurrentIndex(
            max(0, index)
        )
        preview.currentIndexChanged.connect(
            lambda:
            self._set(
                "preview_mode",
                preview.currentData(),
            )
        )

        form.addRow(
            "Tempo mínimo visível:",
            duration,
        )
        form.addRow(
            "Duração da verde:",
            green_duration,
        )
        form.addRow(
            "Prévia no F12:",
            preview,
        )

        self.content_layout.addWidget(
            group
        )

    def _build_detection(self) -> None:
        group = QGroupBox(
            "Captura das informações"
        )
        form = QFormLayout(group)

        settings = [
            (
                "yellow_lookahead_seconds",
                "Janela amarela à frente:",
                1.0,
                20.0,
                0.5,
                10.0,
                " s",
            ),
            (
                "yellow_max_ahead_m",
                "Máximo à frente:",
                100.0,
                1500.0,
                50.0,
                900.0,
                " m",
            ),
            (
                "yellow_max_behind_m",
                "Máximo atrás:",
                0.0,
                300.0,
                10.0,
                100.0,
                " m",
            ),
            (
                "yellow_hazard_speed_kmh",
                "Carro lento:",
                1.0,
                80.0,
                1.0,
                15.12,
                " km/h",
            ),
        ]

        for (
            key,
            label,
            minimum,
            maximum,
            step,
            default,
            suffix,
        ) in settings:
            spin = QDoubleSpinBox()
            spin.setRange(
                minimum,
                maximum,
            )
            spin.setSingleStep(step)
            spin.setSuffix(suffix)
            spin.setValue(
                float(
                    self.config.get(
                        key,
                        default,
                    )
                )
            )
            spin.valueChanged.connect(
                lambda value, current=key:
                self._set(
                    current,
                    value,
                )
            )
            form.addRow(label, spin)

        self.content_layout.addWidget(
            group
        )

    def _build_responsive(self) -> None:
        group = QGroupBox(
            "Redimensionamento responsivo"
        )
        form = QFormLayout(group)

        internal = QDoubleSpinBox()
        internal.setRange(0.50, 2.00)
        internal.setSingleStep(0.05)
        internal.setValue(
            float(
                self.config.get(
                    "internal_scale",
                    1.0,
                )
            )
        )
        internal.valueChanged.connect(
            lambda value:
            self._set(
                "internal_scale",
                value,
            )
        )

        min_scale = QDoubleSpinBox()
        min_scale.setRange(0.25, 1.00)
        min_scale.setSingleStep(0.05)
        min_scale.setValue(
            float(
                self.config.get(
                    "responsive_min_scale",
                    0.48,
                )
            )
        )
        min_scale.valueChanged.connect(
            lambda value:
            self._set(
                "responsive_min_scale",
                value,
            )
        )

        max_scale = QDoubleSpinBox()
        max_scale.setRange(1.00, 3.00)
        max_scale.setSingleStep(0.10)
        max_scale.setValue(
            float(
                self.config.get(
                    "responsive_max_scale",
                    2.20,
                )
            )
        )
        max_scale.valueChanged.connect(
            lambda value:
            self._set(
                "responsive_max_scale",
                value,
            )
        )

        form.addRow(
            "Escala interna:",
            internal,
        )
        form.addRow(
            "Escala mínima:",
            min_scale,
        )
        form.addRow(
            "Escala máxima:",
            max_scale,
        )

        self.content_layout.addWidget(
            group
        )

    def _build_visual(self) -> None:
        group = QGroupBox(
            "Mesmo desenho da referência"
        )
        form = QFormLayout(group)

        font_name = QComboBox()
        font_name.addItems(
            QFontDatabase.families()
        )
        font_name.setCurrentText(
            str(
                self.config.get(
                    "font_name",
                    "Arial",
                )
            )
        )
        font_name.currentTextChanged.connect(
            lambda value:
            self._set(
                "font_name",
                value,
            )
        )
        form.addRow(
            "Fonte:",
            font_name,
        )

        font_size = QSpinBox()
        font_size.setRange(8, 40)
        font_size.setValue(
            int(
                self.config.get(
                    "font_size",
                    16,
                )
            )
        )
        font_size.valueChanged.connect(
            lambda value:
            self._set(
                "font_size",
                value,
            )
        )
        form.addRow(
            "Fonte base:",
            font_size,
        )

        opacity = QDoubleSpinBox()
        opacity.setRange(0.10, 1.00)
        opacity.setSingleStep(0.05)
        opacity.setValue(
            float(
                self.config.get(
                    "opacity",
                    1.0,
                )
            )
        )
        opacity.valueChanged.connect(
            lambda value:
            self._set(
                "opacity",
                value,
            )
        )
        form.addRow(
            "Opacidade:",
            opacity,
        )

        labels = {
            "yellow_bg": "Fundo amarelo",
            "yellow_light": "Cápsulas amarelas",
            "blue_bg": "Fundo azul",
            "blue_light": "Cápsulas azuis",
            "green_bg": "Fundo verde",
            "green_fg": "Texto verde",
        }

        for key, label in labels.items():
            button = QPushButton(
                self.config
                .setdefault(
                    "colors",
                    {},
                )
                .get(
                    key,
                    "#FFFFFF",
                )
            )
            button.clicked.connect(
                lambda checked=False, current=key:
                self._choose_color(
                    current
                )
            )
            self.color_buttons[key] = button
            form.addRow(
                label + ":",
                button,
            )

        self.content_layout.addWidget(
            group
        )
        self.content_layout.addStretch()

    def _choose_color(
        self,
        key: str,
    ) -> None:
        current = QColor(
            self.config
            .setdefault(
                "colors",
                {},
            )
            .get(
                key,
                "#FFFFFF",
            )
        )
        selected = QColorDialog.getColor(
            current,
            self,
        )

        if not selected.isValid():
            return

        value = selected.name(
            QColor.NameFormat.HexRgb
        )
        self.config["colors"][key] = value
        self.color_buttons[key].setText(
            value
        )
        self._emit()

    def _set(
        self,
        key: str,
        value: Any,
    ) -> None:
        self.config[key] = value
        self._emit()

    def _emit(self) -> None:
        self.config_changed.emit(
            deepcopy(self.config)
        )
