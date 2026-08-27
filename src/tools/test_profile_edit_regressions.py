from __future__ import annotations

import json
import os
import tempfile
import unittest
import shutil
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect

from src.ui.overlay_manager import OverlayManager
from src.widget.standings.standings_widget import StandingsWidget


class ProfileEditRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_editor_update_preserves_geometry_for_every_widget(self) -> None:
        previous = {
            "position": {"x": 0.31, "y": 0.42},
            "size": {"width": 0.27, "height": 0.18},
            "scale": 1.25,
            "monitor": 1,
        }
        incoming = deepcopy(previous)
        incoming["position"] = {"x": 0.0, "y": 0.0}
        incoming["size"] = {"width": 0.1, "height": 0.1}
        incoming["opacity"] = 0.7
        merged = OverlayManager._preserve_editor_geometry(
            "delta", previous, incoming, preserve_geometry=True
        )
        self.assertEqual(merged["position"], previous["position"])
        self.assertEqual(merged["size"], previous["size"])
        self.assertEqual(merged["opacity"], 0.7)

    def test_delayed_geometry_is_saved_to_origin_profile(self) -> None:
        config = {
            "widgets": {"delta": {"position": {}, "size": {}}},
            "profiles": {
                "standard": {"name": "Padrão", "mode": "standard", "widgets": {"delta": {"position": {}, "size": {}}}},
                "engineer": {"name": "Engenheiro", "mode": "engineer", "widgets": {"delta": {"position": {}, "size": {}}}},
            },
            "active_profile": "engineer",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "widgets.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            manager = OverlayManager(path)
            manager._save_widget_geometry("delta", 0.2, 0.3, 0.4, 0.5, "standard")
            self.assertEqual(manager.config_data["profiles"]["standard"]["widgets"]["delta"]["position"]["x"], 0.2)
            self.assertNotIn("x", manager.config_data["widgets"]["delta"]["position"])
            manager.close_all()

    def test_rank_percent_keeps_available_decimal_precision(self) -> None:
        self.assertEqual(StandingsWidget._format_rank_percent(43.6), "43.6%")
        self.assertEqual(StandingsWidget._format_rank_percent(70.0), "70%")
        self.assertEqual(StandingsWidget._format_rank_percent(-2.7, signed=True), "-2.7%")

    def test_standings_profile_restore_uses_saved_width(self) -> None:
        factory = Path(__file__).resolve().parents[1] / "config" / "widgets.json"
        config = json.loads(factory.read_text(encoding="utf-8"))["widgets"]["standings"]
        config = deepcopy(config)
        config["size"] = {"width": 0.50, "height": 0.30}
        # Uma referência propositalmente diferente não pode modificar a
        # largura que o usuário salvou no perfil.
        config["column_width_reference_total"] = 100.0
        widget = StandingsWidget("standings", config)
        widget.apply_normalized_geometry(QRect(0, 0, 1000, 800))
        self.assertEqual(widget.width(), 500)
        widget.close()

    def test_url_copies_of_isolated_widgets_stay_hidden_in_edit_mode(self) -> None:
        factory = Path(__file__).resolve().parents[1] / "config" / "widgets.json"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "widgets.json"
            shutil.copy2(factory, path)
            manager = OverlayManager(
                path, external_widget_ids={"delta", "driver_panel"}
            )
            manager.config_data["widgets"]["url"]["enabled"] = True
            manager.config_data["widgets"]["url"]["published_widgets"] = [
                "delta", "driver_panel"
            ]
            manager.create_url()
            manager.set_edit_mode(True)
            for widget_id in ("delta", "driver_panel"):
                source = manager.widgets[widget_id]
                self.assertTrue(source.property("sectorflow_url_source"))
                self.assertFalse(source.isVisible())
            manager.close_all()

    def test_every_overlay_can_be_created_edited_and_closed(self) -> None:
        factory = Path(__file__).resolve().parents[1] / "config" / "widgets.json"
        overlay_ids = (
            "driver_panel", "delta", "flags", "weather", "tires",
            "battery", "damage", "fuel_time", "lap_timer", "relative",
            "radar", "map", "standings", "url",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "widgets.json"
            shutil.copy2(factory, path)
            manager = OverlayManager(path)
            # Evita abrir uma porta e criar fontes adicionais neste smoke
            # test; o ciclo URL completo possui teste dedicado acima.
            manager.config_data["widgets"]["url"]["enabled"] = False
            manager.config_data["widgets"]["url"]["published_widgets"] = []
            for widget_id in overlay_ids:
                widget = manager.create_widget(widget_id)
                self.assertIsNotNone(widget, widget_id)
            manager.set_edit_mode(True)
            self.app.processEvents()
            manager.set_edit_mode(False)
            manager.close_all()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
