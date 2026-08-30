from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.widget.flags.flags_widget import FlagsWidget


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FlagsLayoutUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _config() -> dict:
        return json.loads(
            (PROJECT_ROOT / "src/config/flags_v3_defaults.json").read_text(
                encoding="utf-8"
            )
        )

    def test_flags_can_shrink_to_110_pixels_with_proportional_content(self) -> None:
        widget = FlagsWidget("flags", self._config())
        widget.set_edit_mode(True)
        widget.resize(110, max(50, widget.height()))
        widget._apply_responsive_metrics()
        self.app.processEvents()
        widget._fit_content()
        self.app.processEvents()

        self.assertEqual(widget.minimumWidth(), 110)
        self.assertEqual(widget.width(), 110)
        self.assertLessEqual(widget.main_layout.minimumSize().width(), 110)
        self.assertAlmostEqual(widget._responsive_scale, 110 / 520, places=3)
        self.assertEqual(widget.yellow_radar.width(), 34)
        widget.close()

    def test_legacy_minimum_scale_does_not_restore_old_220_pixel_limit(self) -> None:
        config = self._config()
        config["responsive_min_scale"] = 0.48
        widget = FlagsWidget("flags", config)
        widget.set_edit_mode(True)
        widget.resize(110, max(50, widget.height()))
        widget._apply_responsive_metrics()
        self.app.processEvents()

        self.assertEqual(widget.width(), 110)
        self.assertLess(widget._responsive_scale, 0.48)
        widget.close()


if __name__ == "__main__":
    unittest.main()
