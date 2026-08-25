from __future__ import annotations
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFormLayout, QGroupBox, QLabel, QSpinBox
from src.widget.standings.standings_editor import StandingsEditor


class RelativeEditor(StandingsEditor):
    COLUMN_WIDTHS = (
        ("position", "Posição", 46.0),
        ("change", "Mudança de posição", 60.0),
        ("flag", "Bandeira", 62.5),
        ("badge", "Badge", 60.0),
        ("driver", "Nome do piloto", 180.0),
        ("brand", "Marca", 72.0),
        ("dr", "Driver Rank (DR)", 110.0),
        ("sr", "Safety Rank (SR)", 88.0),
        ("number", "Número do carro", 58.0),
        ("pit", "Tempo do pit", 90.0),
        ("interval", "Intervalo da categoria", 100.0),
        ("delta", "Delta acumulado", 90.0),
        ("gap", "Gap/intervalo", 100.0),
        ("tyre", "Pneus", 76.0),
        ("energy", "Energia", 105.0),
        ("damage", "Danos", 80.0),
        ("track_limits", "Limites de pista", 88.0),
        ("penalty", "Punição", 90.0),
    )

    def __init__(self, config, parent=None):
        super().__init__(config, parent)
        self.setWindowTitle("Editar Relative")

    def _build_rules(self) -> None:
        group = QGroupBox("Carros ao redor do jogador")
        form = QFormLayout(group)
        note = QLabel(
            "A ordem usa a posição física circular na pista. O jogador fica "
            "no centro; carros à frente aparecem acima e carros atrás abaixo."
        )
        note.setWordWrap(True)
        form.addRow(note)
        for key, label, default in (
            ("relative_cars_ahead", "Carros à frente:", 5),
            ("relative_cars_behind", "Carros atrás:", 5),
        ):
            control = QSpinBox(); control.setRange(1, 20)
            control.setValue(int(self.config.get(key, default)))
            control.valueChanged.connect(lambda value, current=key: self._set(current, value))
            form.addRow(label, control)
        for key, label, default in (
            ("show_global_header", "Cabeçalho global:", False),
            ("show_column_legend", "Legenda das colunas:", False),
        ):
            check = QCheckBox(); check.setChecked(bool(self.config.get(key, default)))
            check.toggled.connect(lambda value, current=key: self._set(current, value))
            form.addRow(label, check)
        header_label = QLabel("Informacoes do cabecalho")
        header_label.setStyleSheet("font-weight: 700; margin-top: 8px;")
        form.addRow(header_label)
        for key, label in (
            ("show_header_session_type", "Tipo da sessao:"),
            ("show_header_session_time", "Tempo da sessao:"),
            ("show_header_server_time", "Horario do jogo:"),
            ("show_header_local_time", "Horario do computador:"),
            ("show_header_grip", "Estado da pista:"),
            ("show_header_track_limits", "Limites de pista:"),
            ("show_header_split", "Split da sessao:"),
            ("show_header_source", "Fonte dos dados:"),
        ):
            check = QCheckBox()
            check.setChecked(bool(self.config.get(key, True)))
            check.toggled.connect(
                lambda value, current=key: self._set(current, value)
            )
            form.addRow(label, check)
        self.layout_content.addWidget(group)

    def _build_columns(self) -> None:
        group = QGroupBox("Colunas")
        form = QFormLayout(group)
        note = QLabel("Posição, piloto e gap relativo são obrigatórios.")
        form.addRow(note)
        options = (
            ("show_position_change", "Mudança de posição:", True),
            ("show_country_flag", "Bandeira do piloto:", True),
            ("use_flag_images", "Usar imagem da bandeira:", True),
            ("show_badge", "Badge do piloto:", True),
            ("use_badge_images", "Usar imagem do badge:", True),
            ("show_driver_rank", "Driver Rank (DR):", True),
            ("show_safety_rank", "Safety Rank (SR):", True),
            ("show_estimated_driver_rank_gain", "Estimativa de ganho do DR:", False),
            ("show_brand_logo", "Logo da marca:", True),
            ("show_car_number", "Número do carro:", True),
            ("show_tyre", "Pneu:", True),
            ("show_invalid_lap_status", "Volta inválida:", True),
            ("show_pit_status", "Tempo/status do pit:", True),
            ("show_track_limits_column", "Limites de pista:", True),
            ("show_penalty_column", "Punição automática:", True),
            ("show_energy", "Bateria/Energia:", True),
            ("show_damage", "Dano:", True),
        )
        for key, label, default in options:
            check = QCheckBox(); check.setChecked(bool(self.config.get(key, default)))
            check.toggled.connect(lambda value, current=key: self._set(current, value))
            form.addRow(label, check)
        widths = self.config.setdefault("column_widths", {})
        form.addRow(QLabel("Largura individual das colunas"))
        note_width = QLabel(
            "As outras colunas acompanham automaticamente o texto e a altura da linha."
        )
        note_width.setWordWrap(True)
        form.addRow(note_width)
        for key, label, default in self.COLUMN_WIDTHS:
            if key not in {"driver", "flag", "tyre", "badge", "brand"}:
                continue
            control = QDoubleSpinBox(); control.setRange(24.0, 600.0)
            control.setSingleStep(2.0); control.setSuffix(" px")
            control.setValue(float(widths.get(key, default)))
            control.valueChanged.connect(lambda value, current=key: self._set_column_width(current, value))
            form.addRow(label + ":", control)
        self.layout_content.addWidget(group)
