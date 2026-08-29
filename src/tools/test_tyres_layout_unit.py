from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.widget.tyres.tyres_widget import (
    TyresWidget,
    tyres_main_frame_style,
    tyres_panel_margin,
    tyres_wear_font_size,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TyresLayoutUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _default_config() -> dict:
        return json.loads(
            (PROJECT_ROOT / "src/config/tyres_defaults.json").read_text(
                encoding="utf-8"
            )
        )

    def test_default_background_is_tighter(self) -> None:
        config = self._default_config()
        self.assertEqual(config["panel_margin"], 6.0)
        self.assertEqual(tyres_panel_margin(config, 1.0), 6)
        self.assertEqual(tyres_panel_margin(config, 0.55), 3)

    def test_background_can_be_disabled(self) -> None:
        style = tyres_main_frame_style(
            {"show_background": False},
            "#111111",
            8,
            1,
            "#FFFFFF",
        )
        self.assertEqual(style, "background: transparent; border: none;")

    def test_enabled_background_keeps_color_and_border(self) -> None:
        style = tyres_main_frame_style(
            {"show_background": True},
            "#111111",
            8,
            1,
            "#FFFFFF",
        )
        self.assertIn("background-color: #111111", style)
        self.assertIn("border: 1px solid #FFFFFF", style)

    def test_wear_percentage_is_larger_than_previous_ratio(self) -> None:
        config = {"wear_font_scale": 0.95}
        current = tyres_wear_font_size(config, 20, 1.0)
        previous = round(20 * 0.78)
        self.assertEqual(current, 19)
        self.assertGreater(current, previous)

    def test_widget_applies_compact_margin_and_transparent_background(self) -> None:
        config = self._default_config()
        config["show_background"] = False
        widget = TyresWidget("tires", config)
        widget.resize(390, 400)
        widget._apply_responsive_metrics()

        margins = widget.main_layout.contentsMargins()
        self.assertEqual(
            (margins.left(), margins.top(), margins.right(), margins.bottom()),
            (6, 6, 6, 6),
        )
        self.assertIn(
            "background: transparent; border: none;",
            widget.styleSheet(),
        )
        widget.deleteLater()


if __name__ == "__main__":
    unittest.main()
