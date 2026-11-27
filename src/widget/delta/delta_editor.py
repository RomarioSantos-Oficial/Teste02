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
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.widget.base.editor_layout import build_editor_tabs

from src.i18n import tr


class DeltaEditor(QDialog):
    config_changed = Signal(dict)
    restore_requested = Signal()

    def __init__(
        self,
        config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle(
            "Editar Delta V2.2"
        )
        self.resize(590, 830)
        self.config = deepcopy(config)
        self._color_buttons: dict[
            str,
            QPushButton,
        ] = {}
        self._section_style_buttons: dict[tuple[str, str], QPushButton] = {}

        root = QVBoxLayout(self)
        build_editor_tabs(root, self, (
            ("Geral", (self._build_elements, self._build_fastest_lap,)),
            ("Layout e comportamento", (self._build_geometry, self._build_delta_behavior,)),
            ("Penalidades e setores", (self._build_penalties, self._build_sectors,)),
            ("Logos e aparência", (self._build_logos, self._build_appearance,)),
        ))

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

    def _build_elements(self) -> None:
        group = QGroupBox(
            "Informações exibidas"
        )
        layout = QVBoxLayout(group)

        labels = {
            "header": "Cabeçalho",
            "session_time": "Tempo restante da sessão",
            "session_type": "Tipo da sessão",
            "track_state": "Estado da pista",
            "split": "Split da sessão",
            "penalties": "Limites de pista (PEN) e punições esportivas (INFO)",
            "history": "Histórico do Delta",
            "fastest_lap": "Anúncio de melhor volta da categoria",
            "sectors": "Setores S1 / S2 / S3",
        }

        for key, label in labels.items():
            item = (
                self.config
                .setdefault("elements", {})
                .setdefault(key, {})
            )
            check = QCheckBox(label)
            check.setChecked(
                bool(item.get("enabled", True))
            )
            check.setEnabled(
                not bool(
                    item.get(
                        "locked",
                        False,
                    )
                )
            )
            check.toggled.connect(
                lambda enabled, k=key:
                self._set_element(
                    k,
                    enabled,
                )
            )
            layout.addWidget(check)

        self.content_layout.addWidget(group)

    def _build_fastest_lap(self) -> None:
        group = QGroupBox(
            "Melhor volta da categoria"
        )
        form = QFormLayout(group)

        duration = QDoubleSpinBox()
        duration.setRange(1.0, 60.0)
        duration.setSingleStep(0.5)
        duration.setSuffix(" s")
        duration.setValue(
            float(
                self.config.get(
                    "fastest_lap_show_seconds",
                    5.0,
                )
            )
        )
        duration.valueChanged.connect(
            lambda value:
            self._set_root(
                "fastest_lap_show_seconds",
                value,
            )
        )

        scope = QComboBox()
        scope.addItem(
            "Somente a classe do jogador",
            "player_class",
        )
        scope.addItem(
            "Todas as categorias",
            "all_classes",
        )
        selected_scope = str(
            self.config.get(
                "fastest_lap_scope",
                "player_class",
            )
        )
        selected_index = scope.findData(selected_scope)
        scope.setCurrentIndex(max(0, selected_index))
        scope.currentIndexChanged.connect(
            lambda _index: self._set_root(
                "fastest_lap_scope",
                str(scope.currentData()),
            )
        )

        fade = QDoubleSpinBox()
        fade.setRange(0.05, 3.0)
        fade.setSingleStep(0.05)
        fade.setSuffix(" s")
        fade.setValue(
            float(
                self.config.get(
                    "fastest_lap_fade_seconds",
                    0.30,
                )
            )
        )
        fade.valueChanged.connect(
            lambda value:
            self._set_root(
                "fastest_lap_fade_seconds",
                value,
            )
        )

        always = QCheckBox()
        always.setChecked(
            bool(
                self.config.get(
                    "fastest_lap_always_visible",
                    False,
                )
            )
        )
        always.toggled.connect(
            lambda value:
            self._set_root(
                "fastest_lap_always_visible",
                value,
            )
        )

        initial = QCheckBox()
        initial.setChecked(
            bool(
                self.config.get(
                    "announce_initial_fastest",
                    False,
                )
            )
        )
        initial.toggled.connect(
            lambda value:
            self._set_root(
                "announce_initial_fastest",
                value,
            )
        )

        show_logo = QCheckBox()
        show_logo.setChecked(
            bool(
                self.config.get(
                    "show_manufacturer_logo",
                    True,
                )
            )
        )
        show_logo.toggled.connect(
            lambda value:
            self._set_root(
                "show_manufacturer_logo",
                value,
            )
        )

        form.addRow(
            "Tempo visível (se não permanente):",
            duration,
        )
        form.addRow(
            "Categorias mostradas:",
            scope,
        )
        form.addRow(
            "Duração do fade:",
            fade,
        )
        form.addRow(
            "Sempre visível:",
            always,
        )
        form.addRow(
            "Anunciar volta já existente:",
            initial,
        )
        form.addRow(
            "Mostrar logo do fabricante:",
            show_logo,
        )

        self.content_layout.addWidget(group)

    def _build_geometry(self) -> None:
        group = QGroupBox(
            "Tamanho e posição"
        )
        form = QFormLayout(group)

        for section, key, label, default in (
            ("position", "x", "X:", 0.22),
            ("position", "y", "Y:", 0.18),
            ("size", "width", "Largura:", 0.56),
            ("size", "height", "Altura manual:", 0.36),
        ):
            value = self.config.get(
                section,
                {},
            ).get(key, default)

            spin = QDoubleSpinBox()
            spin.setRange(0.0, 100.0)
            spin.setDecimals(1)
            spin.setSingleStep(0.5)
            spin.setSuffix("%")
            spin.setValue(
                float(value) * 100
            )
            spin.valueChanged.connect(
                lambda number, s=section, k=key:
                self._set_nested(
                    s,
                    k,
                    number / 100,
                )
            )
            form.addRow(label, spin)

        scale = QDoubleSpinBox()
        scale.setRange(0.30, 2.50)
        scale.setSingleStep(0.05)
        scale.setValue(
            float(
                self.config.get(
                    "scale",
                    1.0,
                )
            )
        )
        scale.valueChanged.connect(
            lambda value:
            self._set_root(
                "scale",
                value,
            )
        )

        auto_fit = QCheckBox()
        auto_fit.setChecked(
            bool(
                self.config.get(
                    "auto_fit_content",
                    True,
                )
            )
        )
        auto_fit.toggled.connect(
            lambda value:
            self._set_root(
                "auto_fit_content",
                value,
            )
        )

        form.addRow(
            "Escala geral:",
            scale,
        )
        form.addRow(
            "Altura acompanha conteúdo:",
            auto_fit,
        )

        self.content_layout.addWidget(group)

    def _build_delta_behavior(self) -> None:
        group = QGroupBox(
            "Comportamento do Delta"
        )
        form = QFormLayout(group)

        maximum = QDoubleSpinBox()
        maximum.setRange(0.10, 20.0)
        maximum.setSingleStep(0.10)
        maximum.setSuffix(" s")
        maximum.setValue(
            float(
                self.config.get(
                    "max_delta_seconds",
                    5.0,
                )
            )
        )
        maximum.valueChanged.connect(
            lambda value:
            self._set_root(
                "max_delta_seconds",
                value,
            )
        )

        smoothing = QDoubleSpinBox()
        smoothing.setRange(1.0, 40.0)
        smoothing.setSingleStep(1.0)
        smoothing.setValue(
            float(
                self.config.get(
                    "delta_smoothing",
                    12.0,
                )
            )
        )
        smoothing.valueChanged.connect(
            lambda value:
            self._set_root(
                "delta_smoothing",
                value,
            )
        )

        history = QSpinBox()
        history.setRange(20, 1200)
        history.setSingleStep(20)
        history.setValue(
            int(
                self.config.get(
                    "history_points",
                    240,
                )
            )
        )
        history.valueChanged.connect(
            lambda value:
            self._set_root(
                "history_points",
                value,
            )
        )

        form.addRow(
            "Escala máxima da barra:",
            maximum,
        )
        form.addRow(
            "Suavização da barra:",
            smoothing,
        )
        form.addRow(
            "Pontos do histórico:",
            history,
        )

        self.content_layout.addWidget(group)

        personal = QGroupBox("Comparação com sua melhor volta")
        personal_form = QFormLayout(personal)
        enabled = QCheckBox("Usar a melhor volta pessoal salva como referência")
        enabled.setChecked(bool(self.config.get("compare_personal_best", True)))
        enabled.toggled.connect(
            lambda value: self._set_root("compare_personal_best", value)
        )
        scope = QComboBox()
        scope.addItem("Categoria (qualquer carro)", "category")
        scope.addItem("Mesmo modelo de carro", "model")
        selected_scope = scope.findData(
            str(self.config.get("personal_best_scope", "category"))
        )
        scope.setCurrentIndex(max(0, selected_scope))
        scope.currentIndexChanged.connect(
            lambda index: self._set_root(
                "personal_best_scope", str(scope.itemData(index) or "category")
            )
        )
        personal_form.addRow("Referência DELTA:", enabled)
        personal_form.addRow("Separar por:", scope)
        self.content_layout.addWidget(personal)

    def _build_penalties(self) -> None:
        group = QGroupBox(
            "Limites de pista e punições"
        )
        layout = QVBoxLayout(group)
        note = QLabel(
            "PEN mostra os pontos/limite de pista recebidos da telemetria. "
            "INFO mostra a penalidade esportiva do jogador (DT, SG, tempo, DQ "
            "ou PEN sem tipo informado). O Delta usa os mesmos formatadores "
            "do Standings; uma penalidade não será convertida em pontos de "
            "limite de pista."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.content_layout.addWidget(group)

    def _build_sectors(self) -> None:
        group = QGroupBox(
            "Classificação dos setores"
        )
        form = QFormLayout(group)

        duration = QDoubleSpinBox()
        duration.setRange(0.5, 30.0)
        duration.setSingleStep(0.5)
        duration.setSuffix(" s")
        duration.setValue(float(self.config.get("sector_show_seconds", 5.0)))
        duration.valueChanged.connect(
            lambda value: self._set_root("sector_show_seconds", value)
        )
        form.addRow("Tempo do anúncio:", duration)

        background_opacity = QDoubleSpinBox()
        background_opacity.setRange(0.0, 100.0)
        background_opacity.setDecimals(0)
        background_opacity.setSingleStep(5.0)
        background_opacity.setSuffix(" %")
        background_opacity.setValue(
            float(self.config.get("sector_background_opacity", 0.72)) * 100.0
        )
        background_opacity.valueChanged.connect(
            lambda value: self._set_root(
                "sector_background_opacity", value / 100.0
            )
        )
        form.addRow("Opacidade do fundo:", background_opacity)

        tolerance = QDoubleSpinBox()
        tolerance.setRange(0.0001, 0.1000)
        tolerance.setDecimals(4)
        tolerance.setSingleStep(0.0010)
        tolerance.setSuffix(" s")
        tolerance.setValue(
            float(
                self.config.get(
                    "sector_tolerance_seconds",
                    0.001,
                )
            )
        )
        tolerance.valueChanged.connect(
            lambda value:
            self._set_root(
                "sector_tolerance_seconds",
                value,
            )
        )

        form.addRow(
            "Tolerância de comparação:",
            tolerance,
        )

        self.content_layout.addWidget(group)

    def _build_logos(self) -> None:
        group = QGroupBox(
            "Logos de fabricantes"
        )
        form = QFormLayout(group)

        row = QHBoxLayout()
        self.logo_directory = QLineEdit(
            str(
                self.config.get(
                    "logo_directory",
                    "images/logos",
                )
            )
        )
        self.logo_directory.editingFinished.connect(
            lambda:
            self._set_root(
                "logo_directory",
                self.logo_directory.text().strip(),
            )
        )

        browse = QPushButton("Procurar")
        browse.clicked.connect(
            self._choose_logo_directory
        )

        row.addWidget(
            self.logo_directory,
            1,
        )
        row.addWidget(browse)

        wrapper = QWidget()
        wrapper.setLayout(row)
        form.addRow("Pasta:", wrapper)

        self.content_layout.addWidget(group)

    def _build_appearance(self) -> None:
        group = QGroupBox("Aparência")
        form = QFormLayout(group)

        font_cfg = self.config.setdefault(
            "font",
            {},
        )
        font = QComboBox()
        font.setEditable(True)
        font.addItems(sorted(QFontDatabase.families()))
        font.setCurrentText(
            str(
                font_cfg.get(
                    "family",
                    "Bahnschrift Condensed",
                )
            )
        )
        font.currentTextChanged.connect(
            lambda value:
            self._set_nested(
                "font",
                "family",
                value.strip(),
            )
        )

        header_group = QGroupBox("Cabeçalho — estilo telemetria")
        header_form = QFormLayout(header_group)
        header_font_cfg = self.config.setdefault("header_font", {})
        header_font = QComboBox()
        header_font.setEditable(True)
        header_font.addItems(sorted(QFontDatabase.families()))
        header_font.setCurrentText(
            str(header_font_cfg.get("family", "Segoe UI") or "Segoe UI")
        )
        header_font.currentTextChanged.connect(
            lambda value: self._set_nested(
                "header_font", "family", value.strip()
            )
        )

        header_label_size = QSpinBox()
        header_label_size.setRange(6, 24)
        header_label_size.setSuffix(" px")
        header_label_size.setValue(int(self.config.get("header_label_size", 10)))
        header_label_size.valueChanged.connect(
            lambda value: self._set_root("header_label_size", value)
        )

        header_value_size = QSpinBox()
        header_value_size.setRange(8, 42)
        header_value_size.setSuffix(" px")
        header_value_size.setValue(int(self.config.get("header_value_size", 19)))
        header_value_size.valueChanged.connect(
            lambda value: self._set_root("header_value_size", value)
        )

        highlight = QComboBox()
        for label, key in (
            ("Tipo da sessão", "session_type"),
            ("Tempo restante", "session_time"),
            ("Estado da pista", "track_state"),
            ("Split", "split"),
            ("Limites de pista", "penalties"),
            ("Sem destaque", "none"),
        ):
            highlight.addItem(label, key)
        highlight_key = str(self.config.get("header_highlight_item", "session_type"))
        highlight_index = highlight.findData(highlight_key)
        highlight.setCurrentIndex(max(0, highlight_index))
        highlight.currentIndexChanged.connect(
            lambda _index: self._set_root(
                "header_highlight_item", highlight.currentData()
            )
        )

        header_form.addRow("Fonte do cabeçalho:", header_font)
        header_form.addRow("Tamanho dos rótulos:", header_label_size)
        header_form.addRow("Tamanho dos valores:", header_value_size)
        header_form.addRow("Bloco em destaque:", highlight)

        header_labels = self.config.setdefault("header_labels", {})
        for key, default_label in (
            ("session_time", "TIME LEFT"),
            ("session_type", "SESSION"),
            ("track_state", "TRACK"),
            ("split", "SPLIT"),
            ("penalties", "PEN"),
        ):
            label_edit = QLineEdit(
                str(header_labels.get(key, default_label) or default_label)
            )
            label_edit.setMaxLength(18)
            label_edit.editingFinished.connect(
                lambda k=key, field=label_edit: self._set_nested(
                    "header_labels", k, field.text().strip()
                )
            )
            header_form.addRow(f"Rótulo {default_label}:", label_edit)

        self.content_layout.addWidget(header_group)

        opacity = QDoubleSpinBox()
        opacity.setRange(0.10, 1.00)
        opacity.setSingleStep(0.05)
        opacity.setValue(
            float(
                self.config.get(
                    "opacity",
                    0.96,
                )
            )
        )
        opacity.valueChanged.connect(
            lambda value:
            self._set_root(
                "opacity",
                value,
            )
        )

        background_opacity = QDoubleSpinBox()
        background_opacity.setRange(0.0, 1.0)
        background_opacity.setSingleStep(0.05)
        background_opacity.setValue(
            float(
                self.config.get(
                    "background_opacity",
                    0.86,
                )
            )
        )
        background_opacity.valueChanged.connect(
            lambda value:
            self._set_root(
                "background_opacity",
                value,
            )
        )

        background_enabled = QCheckBox()
        background_enabled.setChecked(
            bool(
                self.config.get(
                    "background_enabled",
                    True,
                )
            )
        )
        background_enabled.toggled.connect(
            lambda value:
            self._set_root(
                "background_enabled",
                value,
            )
        )

 
        form.addRow("Fonte:", font)
        form.addRow(
            "Opacidade geral:",
            opacity,
        )
        form.addRow(
            "Opacidade do fundo:",
            background_opacity,
        )
        form.addRow(
            "Fundo principal:",
            background_enabled,
        )
 

        for key, label in (
            ("text", "Texto"),
            ("muted", "Texto secundário"),
            ("background", "Fundo geral"),
 
            ("header_accent", "Destaque e filete do cabeçalho"),
            ("header_label", "Texto pequeno dos rótulos"),
            ("header_value", "Valores dos blocos"),
 
            ("header_highlight_text", "Texto do bloco destacado"),
            ("header_limit_danger", "Cor ao atingir limite de pista"),
 
            ("grid", "Grade do histórico"),
            ("gain", "Ganho / lado direito"),
            ("loss", "Perda / lado esquerdo"),
            ("neutral", "Barra neutra"),
            ("fastest", "Volta rápida"),
            ("warning", "Avisos"),
            ("sector_better", "Setor pessoal melhor"),
            ("sector_worse", "Setor pior"),
            ("sector_session_best", "Melhor setor de todos"),
            ("sector_neutral", "Setor sem valor"),
            ("border", "Borda"),
        ):
            button = QPushButton(
                self.config
                .setdefault("colors", {})
                .get(key, "#FFFFFF")
            )
            button.clicked.connect(
                lambda checked=False, color_key=key:
                self._choose_color(color_key)
            )
            form.addRow(
                label + ":",
                button,
            )
            self._color_buttons[key] = (
                button
            )

        self.content_layout.addWidget(group)
        self._build_independent_section_styles()
        self.content_layout.addStretch()

    def _build_independent_section_styles(self) -> None:
        styles = self.config.setdefault("section_styles", {})
        sections = (
            ("header", "Fundo externo do cabeçalho", "#080B10", "#2A3540", 1.0, 6.0),
            ("header_cells", "Blocos normais do cabeçalho", "#10151D", "#2A3540", 1.0, 4.0),
            ("header_highlight", "Bloco destacado do cabeçalho", "#B51B69", "#FF54B8", 1.0, 4.0),
            ("delta_bar", "Linha principal do Delta", "#12171D", "#2A3540", 0.95, 8.0),
            ("history", "Histórico do Delta", "#12171D", "#26303A", 0.95, 7.0),
            ("fastest_lap", "Cartão de volta mais rápida", "#0E1319", "#6036AE", 0.96, 8.0),
            ("sectors", "Cartão de setores", "#8B4DFF", "#8B4DFF", 0.72, 7.0),
        )
        for key, title, background, border, opacity, radius in sections:
            style = styles.setdefault(key, {})
            style.setdefault("enabled", True)
            style.setdefault("background", background)
            style.setdefault("border", border)
            style.setdefault("opacity", opacity)
            style.setdefault("border_enabled", True)
            style.setdefault("border_width", 0.8)
            style.setdefault("radius", radius)

            group = QGroupBox(title)
            form = QFormLayout(group)

            enabled = QCheckBox()
            enabled.setChecked(bool(style.get("enabled", True)))
            enabled.toggled.connect(
                lambda value, section=key: self._set_section_style(
                    section, "enabled", value
                )
            )

            background_button = QPushButton(str(style.get("background", background)))
            background_button.clicked.connect(
                lambda checked=False, section=key, button=background_button:
                    self._choose_section_style_color(section, "background", button)
            )

            opacity_spin = QDoubleSpinBox()
            opacity_spin.setRange(0.0, 100.0)
            opacity_spin.setDecimals(0)
            opacity_spin.setSuffix(" %")
            opacity_spin.setValue(float(style.get("opacity", opacity)) * 100.0)
            opacity_spin.valueChanged.connect(
                lambda value, section=key: self._set_section_style(
                    section, "opacity", value / 100.0
                )
            )

            border_enabled = QCheckBox()
            border_enabled.setChecked(bool(style.get("border_enabled", True)))
            border_enabled.toggled.connect(
                lambda value, section=key: self._set_section_style(
                    section, "border_enabled", value
                )
            )

            border_button = QPushButton(str(style.get("border", border)))
            border_button.clicked.connect(
                lambda checked=False, section=key, button=border_button:
                    self._choose_section_style_color(section, "border", button)
            )

            border_width = QDoubleSpinBox()
            border_width.setRange(0.0, 8.0)
            border_width.setDecimals(1)
            border_width.setSingleStep(0.2)
            border_width.setSuffix(" px")
            border_width.setValue(float(style.get("border_width", 0.8)))
            border_width.valueChanged.connect(
                lambda value, section=key: self._set_section_style(
                    section, "border_width", value
                )
            )

            radius_spin = QDoubleSpinBox()
            radius_spin.setRange(0.0, 24.0)
            radius_spin.setDecimals(1)
            radius_spin.setSingleStep(1.0)
            radius_spin.setSuffix(" px")
            radius_spin.setValue(float(style.get("radius", radius)))
            radius_spin.valueChanged.connect(
                lambda value, section=key: self._set_section_style(
                    section, "radius", value
                )
            )

            form.addRow("Fundo ativado:", enabled)
            form.addRow("Cor do fundo:", background_button)
            form.addRow("Opacidade do fundo:", opacity_spin)
            form.addRow("Borda ativada:", border_enabled)
            form.addRow("Cor da borda:", border_button)
            form.addRow("Espessura da borda:", border_width)
            form.addRow("Arredondamento:", radius_spin)

            self._section_style_buttons[(key, "background")] = background_button
            self._section_style_buttons[(key, "border")] = border_button
            self.content_layout.addWidget(group)

    def _set_section_style(self, section: str, key: str, value: Any) -> None:
        self.config.setdefault("section_styles", {}).setdefault(section, {})[key] = value
        self._emit()

    def _choose_section_style_color(
        self,
        section: str,
        key: str,
        button: QPushButton,
    ) -> None:
        style = self.config.setdefault("section_styles", {}).setdefault(section, {})
        current = QColor(str(style.get(key, "#FFFFFF")))
        selected = QColorDialog.getColor(current, self)
        if not selected.isValid():
            return
        value = selected.name(QColor.NameFormat.HexRgb)
        style[key] = value
        button.setText(value)
        self._emit()

    def _choose_logo_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            tr("Escolher pasta de logos"),
        )

        if not selected:
            return

        self.logo_directory.setText(
            selected
        )
        self._set_root(
            "logo_directory",
            selected,
        )

    def _set_element(
        self,
        key: str,
        enabled: bool,
    ) -> None:
        (
            self.config
            .setdefault("elements", {})
            .setdefault(key, {})
        )["enabled"] = enabled
        self._emit()

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
        self._emit()

    def _set_root(
        self,
        key: str,
        value: Any,
    ) -> None:
        self.config[key] = value
        self._emit()

    def _choose_color(
        self,
        key: str,
    ) -> None:
        current = QColor(
            self.config
            .setdefault("colors", {})
            .get(key, "#FFFFFF")
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
        self._color_buttons[key].setText(
            value
        )
        self._emit()

    def _emit(self) -> None:
        self.config_changed.emit(
            deepcopy(self.config)
        )
