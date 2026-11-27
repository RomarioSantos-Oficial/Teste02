from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
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
        self.assertEqual(config["panel_margin"], 4.0)
        self.assertEqual(tyres_panel_margin(config, 1.0), 4)
        self.assertEqual(tyres_panel_margin(config, 0.55), 2)

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
        self.assertEqual(
            tyres_wear_font_size(config, 20, 0.55),
            current,
        )
        self.assertEqual(
            tyres_wear_font_size(config, 20, 2.2),
            current,
        )

    def test_widget_applies_compact_margin_and_transparent_background(self) -> None:
        config = self._default_config()
        config["show_background"] = False
        widget = TyresWidget("tires", config)
        widget.resize(390, 400)
        widget._apply_responsive_metrics()

        margins = widget.main_layout.contentsMargins()
        self.assertEqual(
            (margins.left(), margins.top(), margins.right(), margins.bottom()),
            (4, 4, 4, 4),
        )
        self.assertIn(
            "background: transparent; border: none;",
            widget.styleSheet(),
        )
        widget.deleteLater()

    def test_resizing_keeps_wheels_separate_and_wear_centered(self) -> None:
        for width in (230, 292, 390, 600):
            with self.subTest(width=width):
                config = self._default_config()
                config["internal_scale"] = 2.2
                widget = TyresWidget("tires", config)
                widget.resize(width, 500)
                widget.show()
                self.app.processEvents()
                widget._apply_responsive_metrics()
                self.app.processEvents()

                for group in widget.wheel_groups:
                    self.assertFalse(
                        group.tyre_frame.geometry().intersects(
                            group.brake_frame.geometry()
                        )
                    )
                    tire_center = group.tyre_frame.mapTo(
                        group,
                        QPoint(group.tyre_frame.width() // 2, 0),
                    ).x()
                    wear_center = group.wear_label.mapTo(
                        group,
                        QPoint(group.wear_label.width() // 2, 0),
                    ).x()
                    self.assertEqual(tire_center, wear_center)
                    tire_bottom = group.tyre_frame.mapTo(
                        group,
                        QPoint(0, group.tyre_frame.height()),
                    ).y()
                    wear_top = group.wear_label.mapTo(
                        group,
                        QPoint(0, 0),
                    ).y()
                    self.assertGreaterEqual(wear_top, tire_bottom)

                widget.close()


if __name__ == "__main__":
    unittest.main()
