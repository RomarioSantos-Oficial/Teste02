from __future__ import annotations

from copy import deepcopy

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.ui.menu_row import MenuRow
from src.ui.widget_registry import WIDGET_DEFINITIONS
from src.widget.delta.delta_editor import DeltaEditor
from src.widget.driver_panel.driver_panel_editor import DriverPanelEditor
from src.widget.flags.flags_editor import FlagsEditor
from src.widget.tyres.tyres_editor import TyresEditor
from src.widget.weather.weather_editor import WeatherEditor
from src.widget.battery.battery_editor import BatteryEditor
from src.widget.damage.damage_editor import DamageEditor
from src.widget.relative.relative_editor import RelativeEditor
from src.widget.map.map_editor import MapEditor
from src.widget.standings.standings_editor import StandingsEditor
from src.widget.fuel_time.fuel_time_editor import FuelTimeEditor
from src.widget.url.url_editor import UrlEditor
from src.widget.radar.radar_editor import RadarEditor


class MainMenuWindow(QMainWindow):
    def __init__(self, overlay_manager, edit_mode_manager, parent=None) -> None:
        super().__init__(parent)
        self.overlay_manager = overlay_manager
        self.edit_mode_manager = edit_mode_manager
        self.rows: dict[str, MenuRow] = {}
        self.editors: dict[str, QWidget] = {}

        self.setWindowTitle("Sector Flow Drive")
        self.resize(920, 720)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        root.addWidget(self._build_header())
        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_widget_grid(), 1)
        root.addWidget(self._build_footer())
        self._apply_style()

    def _build_header(self) -> QWidget:
        box = QFrame()
        box.setObjectName("headerBox")
        layout = QVBoxLayout(box)
        title = QLabel("Sector Flow Drive")
        title.setObjectName("mainTitle")
        subtitle = QLabel("Ative, desative e personalize os overlays.")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return box

    def _build_toolbar(self) -> QWidget:
        box = QFrame()
        box.setObjectName("toolbarBox")
        layout = QHBoxLayout(box)
        layout.addWidget(QLabel("Perfil:"))
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(["Padrão", "GT3", "Hypercar", "Endurance", "Streaming"])
        layout.addWidget(self.profile_combo)
        self.edit_mode_button = QPushButton("Modo edição: DESLIGADO")
        self.edit_mode_button.setCheckable(True)
        self.edit_mode_button.toggled.connect(self._set_edit_mode)
        layout.addWidget(self.edit_mode_button)
        save = QPushButton("Salvar layout")
        save.clicked.connect(self.overlay_manager.save_config)
        layout.addWidget(save)
        layout.addStretch()
        return box

    def _build_widget_grid(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        configs = self.overlay_manager.config_data.setdefault("widgets", {})
        for index, definition in enumerate(WIDGET_DEFINITIONS):
            enabled = bool(configs.get(definition.widget_id, {}).get("enabled", False))
            row = MenuRow(
                definition.widget_id,
                definition.title,
                enabled,
                definition.editable,
                definition.implemented,
            )
            row.toggled.connect(self._toggle_widget)
            row.edit_requested.connect(self._open_editor)
            grid.addWidget(row, index // 2, index % 2)
            self.rows[definition.widget_id] = row

        scroll.setWidget(content)
        return scroll

    def _build_footer(self) -> QWidget:
        box = QFrame()
        box.setObjectName("footerBox")
        layout = QHBoxLayout(box)
        self.connection_label = QLabel("LMU: aguardando conexão")
        self.connection_label.setObjectName("connectionLabel")
        layout.addWidget(self.connection_label)
        layout.addStretch()
        layout.addWidget(QLabel("F12 alterna o modo de edição"))
        return box

    def set_lmu_status(self, connected: bool, text: str = "") -> None:
        message = (
            ("LMU: conectado " if connected else "LMU: aguardando ")
            + text
        )
        if self.connection_label.text() != message:
            self.connection_label.setText(message)

        # Reaplicar todo o estilo 20 vezes por segundo é caro. O estilo só
        # precisa ser recalculado quando o estado da conexão realmente muda.
        previous = self.connection_label.property("connected")
        if previous != connected:
            self.connection_label.setProperty("connected", connected)
            self.connection_label.style().unpolish(self.connection_label)
            self.connection_label.style().polish(self.connection_label)

    def _toggle_widget(self, widget_id: str, enabled: bool) -> None:
        try:
            self.overlay_manager.set_widget_enabled(widget_id, enabled)
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao controlar widget", str(exc))
            self.rows[widget_id].set_enabled_state(False)

    def _open_editor(self, widget_id: str) -> None:
        if widget_id == "driver_panel":
            editor = DriverPanelEditor(
                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), None
            )
        elif widget_id == "delta":
            editor = DeltaEditor(
                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), None
            )
        elif widget_id == "flags":
            editor = FlagsEditor(
                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), None
            )
        elif widget_id == "tires":
            editor = TyresEditor(
                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), None
            )
        elif widget_id == "weather":
            editor = WeatherEditor(
                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), None
            )
        elif widget_id == "battery":
            editor = BatteryEditor(
                deepcopy(
                    self.overlay_manager.config_data["widgets"][widget_id]
                ),
                None,
            )
        elif widget_id == "damage":
            editor = DamageEditor(
                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]),
                None,
            )
        elif widget_id == "fuel_time":
            editor = FuelTimeEditor(
                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), None
            )
        elif widget_id == "url":
            editor = UrlEditor(
                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), None
            )
        elif widget_id == "relative":
            editor = RelativeEditor(
                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]),
                None,
            )
        elif widget_id == "radar":
            editor = RadarEditor(
                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), None
            )
        elif widget_id == "map":
            editor = MapEditor(
                deepcopy(
                    self.overlay_manager.config_data["widgets"][widget_id]
                ),
                None,
            )
        elif widget_id == "standings":
            editor = StandingsEditor(
                deepcopy(
                    self.overlay_manager.config_data["widgets"][widget_id]
                ),
                None,
            )
        else:
            QMessageBox.information(
                self,
                "Editor ainda não criado",
                f"O editor de '{widget_id}' ainda não foi implementado.",
            )
            return

        editor.config_changed.connect(
            lambda config, current_id=widget_id: self.overlay_manager.update_widget_config(
                current_id, config
            )
        )
        editor.restore_requested.connect(
            lambda current_id=widget_id: self.overlay_manager.restore_widget_default(current_id)
        )
        editor.finished.connect(
            lambda _result, current_id=widget_id: self._editor_closed(
                current_id
            )
        )
        self.editors[widget_id] = editor
        self.hide()
        editor.show()
        editor.raise_()
        editor.activateWindow()

    def _editor_closed(self, widget_id: str) -> None:
        self.editors.pop(widget_id, None)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        event.accept()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _set_edit_mode(self, enabled: bool) -> None:
        if self.edit_mode_manager is not None:
            self.edit_mode_manager.set_enabled(enabled)
        self.overlay_manager.set_edit_mode(enabled)
        self.edit_mode_button.setText(
            "Modo edição: LIGADO" if enabled else "Modo edição: DESLIGADO"
        )

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #090D15; color: #F4F7FB; font-family: Arial; font-size: 14px; }
            QFrame#headerBox, QFrame#toolbarBox, QFrame#footerBox { background: #151B26; border: 1px solid #2A3444; border-radius: 12px; }
            QLabel#mainTitle { font-size: 30px; font-weight: 700; }
            QLabel#subtitle { color: #9BA8BA; }
            QFrame#menuRow { background: #171E2A; border: 1px solid #2B3546; border-radius: 9px; }
            QFrame#menuRow:hover { border: 1px solid #506078; }
            QLabel#rowTitle { font-size: 17px; font-weight: 650; }
            QLabel#rowStatus { color: #4BD59A; font-size: 11px; }
            QLabel#rowStatus[pending="true"] { color: #F1B84B; }
            QPushButton { background: #29364A; border: 1px solid #40516C; border-radius: 7px; padding: 7px 12px; }
            QPushButton:hover { background: #34445C; }
            QPushButton:disabled { background: #1C2330; color: #606B7A; border-color: #2B3340; }
            QPushButton:checked { background: #7C3AED; border-color: #9B6AF3; }
            QComboBox { background: #202938; border: 1px solid #3A485E; border-radius: 7px; padding: 7px; min-width: 150px; }
            QCheckBox::indicator { width: 42px; height: 22px; }
            QCheckBox::indicator:unchecked { image: none; background: #4A5362; border-radius: 11px; }
            QCheckBox::indicator:checked { image: none; background: #14B86E; border-radius: 11px; }
            QLabel#connectionLabel { color: #F1B84B; font-weight: 600; }
            QLabel#connectionLabel[connected="true"] { color: #3EDB91; }
            QScrollArea { border: none; background: transparent; }
            """
        )
