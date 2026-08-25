from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from src.ui.menu_row import MenuRow
from src.ui.widget_registry import WIDGET_DEFINITIONS
from src.i18n import LANGUAGES, app_language, set_app_language, tr
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
from src.widget.lap_timer.lap_timer_editor import LapTimerEditor
from src.widget.url.url_editor import UrlEditor
from src.widget.radar.radar_editor import RadarEditor


class MainMenuWindow(QMainWindow):
    def __init__(self, overlay_manager, edit_mode_manager, parent=None) -> None:
        super().__init__(parent)
        self.overlay_manager = overlay_manager
        self.edit_mode_manager = edit_mode_manager
        self.rows: dict[str, MenuRow] = {}
        self.editors: dict[str, QWidget] = {}
        self._lmu_connected = False
        self._lmu_status_text = "conexão"

        self.setWindowTitle("SectorFlow Overley")
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
        self.overlay_manager.profile_changed.connect(self._profile_applied)

    def _build_header(self) -> QWidget:
        box = QFrame()
        box.setObjectName("headerBox")
        layout = QHBoxLayout(box)
        identity = QVBoxLayout()
        title = QLabel("SectorFlow Overley")
        title.setObjectName("mainTitle")
        subtitle = QLabel("Ative, desative e personalize os overlays.")
        subtitle.setObjectName("subtitle")
        identity.addWidget(title)
        identity.addWidget(subtitle)
        layout.addLayout(identity, 1)

        header_config = self._load_header_config()
        update_box = QFrame()
        update_box.setObjectName("headerInfoBox")
        update_layout = QVBoxLayout(update_box)
        update_layout.setContentsMargins(12, 8, 12, 8)
        self.version_label = QLabel(f"{tr('Versão')} {header_config['version']}")
        self.version_label.setProperty("sectorflowVersion", header_config["version"])
        self.version_label.setObjectName("versionLabel")
        notes_button = QPushButton("Notas da versão")
        notes_button.setObjectName("updateNotesButton")
        notes_button.clicked.connect(
            lambda: self._open_update_notes(header_config)
        )
        update_layout.addWidget(self.version_label)
        update_layout.addWidget(notes_button)
        layout.addWidget(update_box, 1)

        donation_box = QFrame()
        donation_box.setObjectName("headerInfoBox")
        donation_layout = QVBoxLayout(donation_box)
        donation_layout.setContentsMargins(12, 8, 12, 8)
        donation_title = QLabel(header_config["donation_label"])
        donation_title.setObjectName("donationLabel")
        donation_button = QPushButton("Doações")
        donation_button.setObjectName("donationButton")
        donation_button.clicked.connect(
            lambda: self._open_donation(header_config)
        )
        donation_layout.addWidget(donation_title)
        donation_layout.addWidget(donation_button)
        layout.addWidget(donation_box)
        return box

    @staticmethod
    def _load_header_config() -> dict[str, str]:
        defaults = {
            "version": "0.0.5",
            "update_note": "Novidades e correções da versão atual.",
            "update_note_key": "",
            "update_note_addendum": "",
            "update_note_addendum_key": "",
            "update_note_fix": "",
            "update_note_fix_key": "",
            "donation_label": "Apoie o desenvolvimento",
            "donation_url": "",
            "pix_key": "",
            "pix_qr_image": "images/pix/qrcode-pix.png",
        }
        path = Path(__file__).resolve().parents[1] / "config" / "menu_header.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return defaults
        return {
            key: str(data.get(key, value) or value)
            for key, value in defaults.items()
        }

    def _open_donation(self, config: dict[str, str]) -> None:
        pix_key = config.get("pix_key", "").strip()
        donation_url = config.get("donation_url", "").strip()
        dialog = QDialog(self)
        dialog.setWindowTitle("Doações")
        dialog.setMinimumWidth(380)
        layout = QVBoxLayout(dialog)

        title = QLabel("Apoie o desenvolvimento do SectorFlow Overley")
        title.setObjectName("donationDialogTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        qr_relative = config.get("pix_qr_image", "").strip()
        qr_path = Path(__file__).resolve().parents[2] / qr_relative
        if qr_relative and qr_path.is_file():
            pixmap = QPixmap(str(qr_path))
            if not pixmap.isNull():
                qr_label = QLabel()
                qr_label.setObjectName("pixQrCode")
                qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                qr_label.setPixmap(
                    pixmap.scaled(
                        260,
                        260,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                layout.addWidget(qr_label)

        if pix_key:
            key_label = QLabel(f"{tr('Chave PIX:')} {pix_key}")
            key_label.setObjectName("pixKeyLabel")
            key_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            key_label.setWordWrap(True)
            layout.addWidget(key_label)
            copy_pix = QPushButton("Copiar chave PIX")
            copy_pix.clicked.connect(
                lambda: self._copy_pix_key(pix_key, copy_pix)
            )
            layout.addWidget(copy_pix)

        if donation_url:
            paypal = QPushButton("Doar com PayPal")
            paypal.setObjectName("paypalButton")
            paypal.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl(donation_url))
            )
            layout.addWidget(paypal)

        if not pix_key and not donation_url:
            layout.addWidget(QLabel("Destino de doação ainda não configurado."))

        close = QPushButton("Fechar")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def _open_update_notes(self, config: dict[str, str]) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Notas da versão")
        dialog.setMinimumSize(480, 300)
        layout = QVBoxLayout(dialog)

        version = QLabel(f"SectorFlow Overley — {tr('Versão')} {config['version']}")
        version.setObjectName("updateDialogTitle")
        layout.addWidget(version)

        source_note = config.get("update_note", "").strip() or "Nenhuma nota cadastrada."
        translation_key = config.get("update_note_key", "").strip()
        translated_note = tr(translation_key) if translation_key else tr(source_note)
        if translation_key and translated_note == translation_key:
            translated_note = source_note
        addendum_source = config.get("update_note_addendum", "").strip()
        addendum_key = config.get("update_note_addendum_key", "").strip()
        translated_addendum = tr(addendum_key) if addendum_key else tr(addendum_source)
        if addendum_key and translated_addendum == addendum_key:
            translated_addendum = addendum_source
        if translated_addendum:
            translated_note = f"{translated_note}\n\n{translated_addendum}"
        fix_source = config.get("update_note_fix", "").strip()
        fix_key = config.get("update_note_fix_key", "").strip()
        translated_fix = tr(fix_key) if fix_key else tr(fix_source)
        if fix_key and translated_fix == fix_key:
            translated_fix = fix_source
        if translated_fix:
            translated_note = f"{translated_note}\n\n{translated_fix}"
        note = QLabel(translated_note)
        note.setObjectName("updateDialogNote")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(note, 1)

        close = QPushButton("Fechar")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    @staticmethod
    def _copy_pix_key(pix_key: str, button: QPushButton) -> None:
        QApplication.clipboard().setText(pix_key)
        button.setText(tr("Chave PIX copiada!"))

    def _build_toolbar(self) -> QWidget:
        box = QFrame()
        box.setObjectName("toolbarBox")
        layout = QHBoxLayout(box)
        layout.addWidget(QLabel("Perfil:"))
        self.profile_combo = QComboBox()
        self._reload_profiles()
        self.profile_combo.currentIndexChanged.connect(self._switch_profile)
        layout.addWidget(self.profile_combo)
        add_profile = QPushButton("Novo perfil")
        add_profile.clicked.connect(self._create_profile)
        layout.addWidget(add_profile)
        self.rename_profile_button = QPushButton("Renomear")
        self.rename_profile_button.clicked.connect(self._rename_profile)
        layout.addWidget(self.rename_profile_button)
        self.delete_profile_button = QPushButton("Excluir")
        self.delete_profile_button.clicked.connect(self._delete_profile)
        layout.addWidget(self.delete_profile_button)
        self._update_profile_buttons()
        self.edit_mode_button = QPushButton("Modo edição: DESLIGADO")
        self.edit_mode_button.setCheckable(True)
        self.edit_mode_button.toggled.connect(self._set_edit_mode)
        layout.addWidget(self.edit_mode_button)
        save = QPushButton("Salvar layout")
        save.clicked.connect(self.overlay_manager.save_config)
        layout.addWidget(save)
        layout.addWidget(QLabel("Idioma:"))
        self.language_combo = QComboBox()
        for code, label in LANGUAGES.items():
            self.language_combo.addItem(label, code)
        current = self.language_combo.findData(app_language())
        self.language_combo.setCurrentIndex(max(0, current))
        self.language_combo.setToolTip("Idioma da interface")
        self.language_combo.currentIndexChanged.connect(self._change_language)
        layout.addWidget(self.language_combo)
        layout.addStretch()
        return box

    def _change_language(self, index: int) -> None:
        language = str(self.language_combo.itemData(index) or "pt_BR")
        set_app_language(language)
        self._refresh_dynamic_translations()

    def _refresh_dynamic_translations(self) -> None:
        """Reaplica textos que mudam depois que a janela foi traduzida."""
        version = str(self.version_label.property("sectorflowVersion") or "0.0.5")
        self.version_label.setText(f"{tr('Versão')} {version}")
        self._reload_profiles()
        self.edit_mode_button.setText(
            tr("Modo edição: LIGADO")
            if self.edit_mode_button.isChecked()
            else tr("Modo edição: DESLIGADO")
        )
        for row in self.rows.values():
            source_title = str(row.property("sectorflowTitle") or "")
            if source_title:
                row.title_label.setText(tr(source_title))
            row._apply_enabled_status(row.toggle.isChecked())
        self.set_lmu_status(self._lmu_connected, self._lmu_status_text)

    def _reload_profiles(self, selected_id: str | None = None) -> None:
        if not hasattr(self, "profile_combo"):
            return
        selected_id = selected_id or self.overlay_manager.active_profile_id
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        selected_index = 0
        for index, (profile_id, name) in enumerate(
            self.overlay_manager.profile_items()
        ):
            # Nomes criados pelo usuário não são traduzidos. Somente os dois
            # perfis internos possuem nomes localizáveis.
            display_name = tr(name) if profile_id in {"standard", "engineer"} else name
            self.profile_combo.addItem(display_name, profile_id)
            if profile_id == selected_id:
                selected_index = index
        self.profile_combo.setCurrentIndex(selected_index)
        self.profile_combo.blockSignals(False)

    def _switch_profile(self, index: int) -> None:
        profile_id = self.profile_combo.itemData(index)
        if profile_id:
            self.overlay_manager.switch_profile(str(profile_id))
        self._update_profile_buttons()

    def _create_profile(self) -> None:
        name, accepted = self._translated_text_dialog(
            "Novo perfil", "Nome do perfil personalizado:"
        )
        if not accepted or not name.strip():
            return
        try:
            profile_id = self.overlay_manager.create_profile(name)
            self._reload_profiles(profile_id)
            self.overlay_manager.switch_profile(profile_id)
        except Exception as exc:
            QMessageBox.critical(self, tr("Erro ao criar perfil"), str(exc))

    def _rename_profile(self) -> None:
        profile_id = str(self.profile_combo.currentData() or "")
        if profile_id in {"standard", "engineer"}:
            return
        current_name = self.profile_combo.currentText()
        name, accepted = self._translated_text_dialog(
            "Renomear perfil",
            "Novo nome do perfil:",
            current_name,
        )
        if not accepted or not name.strip():
            return
        try:
            self.overlay_manager.rename_profile(profile_id, name)
        except Exception as exc:
            QMessageBox.critical(self, tr("Erro ao renomear perfil"), str(exc))

    def _translated_text_dialog(
        self, title: str, label: str, value: str = ""
    ) -> tuple[str, bool]:
        dialog = QInputDialog(self)
        dialog.setInputMode(QInputDialog.InputMode.TextInput)
        dialog.setWindowTitle(tr(title))
        dialog.setLabelText(tr(label))
        dialog.setTextValue(value)
        dialog.setOkButtonText(tr("OK"))
        dialog.setCancelButtonText(tr("Cancelar"))
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        return dialog.textValue(), accepted

    def _delete_profile(self) -> None:
        profile_id = str(self.profile_combo.currentData() or "")
        if profile_id in {"standard", "engineer"}:
            return
        name = self.profile_combo.currentText()
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Question)
        message.setWindowTitle(tr("Excluir perfil"))
        message.setText(tr("Excluir permanentemente o perfil '{name}'?").format(name=name))
        message.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        message.setDefaultButton(QMessageBox.StandardButton.No)
        yes_button = message.button(QMessageBox.StandardButton.Yes)
        no_button = message.button(QMessageBox.StandardButton.No)
        if yes_button is not None:
            yes_button.setText(tr("Sim"))
        if no_button is not None:
            no_button.setText(tr("Não"))
        answer = QMessageBox.StandardButton(message.exec())
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.overlay_manager.delete_profile(profile_id)
        except Exception as exc:
            QMessageBox.critical(self, tr("Erro ao excluir perfil"), str(exc))

    def _update_profile_buttons(self) -> None:
        if not hasattr(self, "delete_profile_button"):
            return
        custom = str(self.profile_combo.currentData() or "") not in {
            "standard", "engineer", ""
        }
        self.rename_profile_button.setEnabled(custom)
        self.delete_profile_button.setEnabled(custom)

    def _profile_applied(self, profile_id: str) -> None:
        self._reload_profiles(profile_id)
        self._update_profile_buttons()
        configs = self.overlay_manager.config_data.get("widgets", {})
        for widget_id, row in self.rows.items():
            row.set_enabled_state(
                bool(configs.get(widget_id, {}).get("enabled", False))
            )

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
            row.setProperty("sectorflowTitle", definition.title)
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
        self._lmu_connected = bool(connected)
        self._lmu_status_text = text
        message = (
            (tr("LMU: conectado ") if connected else tr("LMU: aguardando "))
            + tr(text)
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
            self.rows[widget_id].set_enabled_state(enabled)
        except Exception as exc:
            QMessageBox.critical(self, tr("Erro ao controlar widget"), str(exc))
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
        elif widget_id == "lap_timer":
            editor = LapTimerEditor(
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
                tr("Editor ainda não criado"),
                tr("O editor de '{widget_id}' ainda não foi implementado.").format(
                    widget_id=widget_id
                ),
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
        if bool(getattr(self, "tray_mode_enabled", False)):
            event.ignore()
            self.hide()
            tray_icon = getattr(self, "tray_icon", None)
            if tray_icon is not None:
                tray_icon.showMessage(
                    "SectorFlow Overley",
                    tr("O programa continua na bandeja do Windows."),
                    QSystemTrayIcon.MessageIcon.Information,
                    2500,
                )
            return
        event.accept()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _set_edit_mode(self, enabled: bool) -> None:
        if self.edit_mode_manager is not None:
            self.edit_mode_manager.set_enabled(enabled)
        self.overlay_manager.set_edit_mode(enabled)
        self.edit_mode_button.setText(
            tr("Modo edição: LIGADO") if enabled else tr("Modo edição: DESLIGADO")
        )

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #090D15; color: #F4F7FB; font-family: Arial; font-size: 14px; }
            QFrame#headerBox, QFrame#toolbarBox, QFrame#footerBox { background: #151B26; border: 1px solid #2A3444; border-radius: 12px; }
            QFrame#headerInfoBox { background: #101722; border: 1px solid #2A3444; border-radius: 8px; }
            QLabel#mainTitle { font-size: 30px; font-weight: 700; }
            QLabel#subtitle { color: #9BA8BA; }
            QLabel#versionLabel { color: #67E8F9; font-weight: 700; }
            QPushButton#updateNotesButton { background: #1265A8; border-color: #2784CA; }
            QLabel#updateDialogTitle { color: #67E8F9; font-size: 20px; font-weight: 700; }
            QLabel#updateDialogNote { color: #D7DEE9; font-size: 14px; padding: 10px; }
            QLabel#donationLabel { color: #F1B84B; font-size: 12px; font-weight: 700; }
            QPushButton#donationButton { background: #7C3AED; border-color: #9B6AF3; }
            QLabel#donationDialogTitle { font-size: 18px; font-weight: 700; color: #F1B84B; }
            QLabel#pixQrCode { background: #202938; border: 2px solid #67E8F9; border-radius: 10px; padding: 14px; }
            QLabel#pixKeyLabel { color: #D7DEE9; font-family: Consolas; font-size: 12px; }
            QPushButton#paypalButton { background: #0070BA; border-color: #169BD7; }
            QFrame#menuRow { background: #171E2A; border: 1px solid #2B3546; border-radius: 9px; }
            QFrame#menuRow:hover { border: 1px solid #506078; }
            QLabel#rowTitle { font-size: 17px; font-weight: 650; }
            QLabel#rowStatus { color: #EF5350; font-size: 11px; font-weight: 700; }
            QLabel#rowStatus[active="true"] { color: #4BD59A; }
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
