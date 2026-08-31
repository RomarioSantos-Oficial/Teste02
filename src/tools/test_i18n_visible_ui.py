from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QApplication,
    QComboBox,
    QGroupBox,
    QLabel,
    QTabWidget,
    QWidget,
)

from src.i18n.translator import LANGUAGES, _load_catalog, _source_text  # noqa: E402
from src.ui.main_menu_window import MainMenuWindow  # noqa: E402
from src.widget.battery.battery_editor import BatteryEditor  # noqa: E402
from src.widget.damage.damage_editor import DamageEditor  # noqa: E402
from src.widget.delta.delta_editor import DeltaEditor  # noqa: E402
from src.widget.driver_panel.driver_panel_editor import DriverPanelEditor  # noqa: E402
from src.widget.flags.flags_editor import FlagsEditor  # noqa: E402
from src.widget.fuel_time.fuel_time_editor import FuelTimeEditor  # noqa: E402
from src.widget.lap_timer.lap_timer_editor import LapTimerEditor  # noqa: E402
from src.widget.map.map_editor import MapEditor  # noqa: E402
from src.widget.radar.radar_editor import RadarEditor  # noqa: E402
from src.widget.relative.relative_editor import RelativeEditor  # noqa: E402
from src.widget.standings.standings_editor import StandingsEditor  # noqa: E402
from src.widget.tyres.tyres_editor import TyresEditor  # noqa: E402
from src.widget.url.url_editor import UrlEditor  # noqa: E402
from src.widget.weather.weather_editor import WeatherEditor  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TECHNICAL_TEXT = re.compile(
    r"^(#[0-9A-Fa-f]{6,8}|[0-9]+ s|[XY]:|km/h|mph|PSI|GT|C|F)$"
)
TECHNICAL_LABELS = {"Lap Timer:", "Sector Flow Overlay - Lap Timer"}
DYNAMIC_TRANSLATION_KEYS = {
    "Atrás:",
    "Frente:",
    "VENTO",
    "DIANTEIRO {front}  |  TRASEIRO {rear}",
    "Escolher cor",
    "Escolher imagem",
    "Escolher pasta de logos",
    "Imagem do volante",
    "Imagens (*.png *.jpg *.jpeg *.bmp *.webp)",
    "Imagens (*.png *.jpg *.jpeg *.webp)",
    "Editor ainda não criado",
    "Erro ao controlar widget",
    "Erro ao criar perfil",
    "Erro ao excluir perfil",
    "Erro ao renomear perfil",
    "Excluir perfil",
    "Renomear perfil",
    "O editor de '{widget_id}' ainda não foi implementado.",
}


class VisibleUiTranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.config = json.loads(
            (PROJECT_ROOT / "src/config/widgets.json").read_text(encoding="utf-8")
        )

    def _visible_editor_texts(self) -> set[str]:
        editors = {
            "driver_panel": DriverPanelEditor,
            "delta": DeltaEditor,
            "flags": FlagsEditor,
            "tires": TyresEditor,
            "weather": WeatherEditor,
            "battery": BatteryEditor,
            "damage": DamageEditor,
            "relative": RelativeEditor,
            "map": MapEditor,
            "standings": StandingsEditor,
            "fuel_time": FuelTimeEditor,
            "lap_timer": LapTimerEditor,
            "url": UrlEditor,
            "radar": RadarEditor,
        }
        texts: set[str] = set(DYNAMIC_TRANSLATION_KEYS)

        def add(value: str) -> None:
            text = str(value or "").strip()
            if text and any(character.isalpha() for character in text):
                texts.add(text)

        for widget_id, editor_type in editors.items():
            editor = editor_type(
                self.config["widgets"].get(widget_id, {}),
                None,
            )
            add(editor.windowTitle())
            for obj in [editor, *editor.findChildren(QWidget)]:
                add(obj.toolTip())
                if isinstance(obj, QLabel):
                    add(obj.text())
                if isinstance(obj, QAbstractButton):
                    add(obj.text())
                if isinstance(obj, QGroupBox):
                    add(obj.title())
                if isinstance(obj, QComboBox):
                    for index in range(obj.count()):
                        add(obj.itemText(index))
                if isinstance(obj, QTabWidget):
                    for index in range(obj.count()):
                        add(obj.tabText(index))
            editor.close()
            editor.deleteLater()

        return {
            _source_text(text)
            for text in texts
            if not TECHNICAL_TEXT.fullmatch(text)
            and text not in TECHNICAL_LABELS
        }

    def test_every_visible_editor_text_has_all_translations(self) -> None:
        required = self._visible_editor_texts()
        failures: list[str] = []
        for language in LANGUAGES:
            if language == "pt_BR":
                continue
            missing = sorted(required.difference(_load_catalog(language)))
            if missing:
                failures.append(f"{language}: {', '.join(missing)}")
        self.assertFalse(failures, "\n".join(failures))

    def test_release_notes_keep_all_translation_keys(self) -> None:
        config = MainMenuWindow._load_header_config()
        fields = (
            "update_note_key",
            "update_note_addendum_key",
            "update_note_fix_key",
        )
        for language in LANGUAGES:
            if language == "pt_BR":
                continue
            catalog = _load_catalog(language)
            for field in fields:
                key = config[field]
                self.assertTrue(key, field)
                self.assertIn(key, catalog, f"{language}: {key}")
                self.assertNotEqual(catalog[key], key)


if __name__ == "__main__":
    unittest.main()
