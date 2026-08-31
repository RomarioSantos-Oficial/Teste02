from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from src.telemetry.models import DriverData, SessionData
from src.ui.overlay_manager import OverlayManager
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

    def test_resize_uses_one_horizontal_pixel_without_vertical_jump(self) -> None:
        self.assertEqual(
            FlagsWidget._resize_width_from_delta(160, QPoint(3, 20)),
            163,
        )
        self.assertEqual(
            FlagsWidget._resize_width_from_delta(160, QPoint(-4, -20)),
            156,
        )
        self.assertEqual(
            FlagsWidget._resize_width_from_delta(160, QPoint(0, 30)),
            160,
        )

    def test_saved_geometry_does_not_enlarge_flags_on_high_resolution(self) -> None:
        self.assertEqual(
            OverlayManager._geometry_minimum_ratios("flags"),
            (0.01, 0.01),
        )

    def test_yellow_reopens_after_isolated_host_hid_window(self) -> None:
        widget = FlagsWidget("flags", self._config())
        widget.show()
        widget.widget_visivel = True
        widget.hide()
        session = SessionData(
            connected=True,
            session=10,
            game_phase=5,
            track_length_m=5000.0,
            sector_flags=(1, 0, 0),
            drivers=[
                DriverData(
                    slot_id=1,
                    driver_name="Player",
                    vehicle_class="LMGT3",
                    position=1,
                    is_player=True,
                    speed_kmh=180.0,
                    lap_distance_m=1000.0,
                ),
                DriverData(
                    slot_id=2,
                    driver_name="Confirmed Hazard",
                    vehicle_class="LMGT3",
                    position=2,
                    speed_kmh=60.0,
                    lap_distance_m=1300.0,
                    under_yellow=True,
                ),
            ],
        )

        widget.update_from_session(session)
        self.app.processEvents()

        self.assertTrue(widget.yellow_ativa)
        self.assertTrue(widget.isVisible())
        widget.close()

    def test_compact_distance_panel_keeps_width_and_self_hazard_values(self) -> None:
        widget = FlagsWidget("flags", self._config())
        widget.resize(176, max(50, widget.height()))
        session = SessionData(
            connected=True,
            session=10,
            game_phase=5,
            track_length_m=5000.0,
            sector_flags=(1, 0, 0),
            drivers=[
                DriverData(
                    slot_id=1,
                    driver_name="Player",
                    vehicle_class="HYPER",
                    position=15,
                    is_player=True,
                    speed_kmh=0.0,
                    lap_distance_m=1000.0,
                    under_yellow=True,
                )
            ],
        )

        widget.update_from_session(session)
        widget._apply_responsive_metrics()
        self.app.processEvents()

        self.assertEqual(widget.yellow_distance.text(), "0m | 0.0s")
        self.assertGreater(widget.yellow_distance_frame.width(), 100)
        widget.close()

    def test_inactive_session_clears_stale_flag_and_prevents_reopen(self) -> None:
        widget = FlagsWidget("flags", self._config())
        session = SessionData(
            connected=True,
            session=10,
            game_phase=5,
            track_length_m=5000.0,
            sector_flags=(1, 0, 0),
            drivers=[
                DriverData(
                    slot_id=1,
                    driver_name="Player",
                    vehicle_class="HYPER",
                    position=1,
                    is_player=True,
                    speed_kmh=180.0,
                    lap_distance_m=1000.0,
                ),
                DriverData(
                    slot_id=2,
                    driver_name="Confirmed Hazard",
                    vehicle_class="HYPER",
                    position=2,
                    speed_kmh=30.0,
                    lap_distance_m=1200.0,
                    under_yellow=True,
                ),
            ],
        )

        widget.update_from_session(session)
        self.app.processEvents()
        self.assertTrue(widget.isVisible())

        widget.set_session_active(False)
        widget.verificar_visibilidade_widget()
        self.app.processEvents()

        self.assertFalse(widget.yellow_ativa)
        self.assertFalse(widget.widget_visivel)
        self.assertFalse(widget.isVisible())
        widget.close()


if __name__ == "__main__":
    unittest.main()
