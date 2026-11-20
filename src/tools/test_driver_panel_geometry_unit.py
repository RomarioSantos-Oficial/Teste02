from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from src.ui.main_menu_window import MainMenuWindow
from src.ui.overlay_manager import OverlayManager
from src.widget.driver_panel.driver_panel_editor import DriverPanelEditor
from src.widget.driver_panel.driver_panel_widget import DriverPanelWidget


class DriverPanelGeometryUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _config() -> dict:
        return {
            "position": {"x": 0.10, "y": 0.20},
            "size": {"width": 0.20, "height": 0.12},
            "scale": 1.0,
            "elements": {},
            "pedal_elements": {},
            "colors": {},
        }

    def test_compact_minimum_is_available(self) -> None:
        self.assertEqual(DriverPanelWidget.MINIMUM_WIDTH, 180)
        self.assertEqual(DriverPanelWidget.MINIMUM_HEIGHT, 70)

    def test_history_rate_follows_configured_sample_rate(self) -> None:
        config = self._config()
        config["sample_rate_hz"] = 60
        widget = DriverPanelWidget("driver_panel", config)
        widget.apply_config()
        self.assertAlmostEqual(widget._history_interval_s, 1.0 / 60.0)
        widget.deleteLater()

    def test_graph_ignores_single_sample_pedal_spike(self) -> None:
        config = self._config()
        config["sample_rate_hz"] = 60
        widget = DriverPanelWidget("driver_panel", config)
        widget._history_interval_s = 0.0
        player = type(
            "Player",
            (),
            {
                "throttle": 0.0,
                "brake": 0.0,
                "clutch": 0.0,
                "steering": 0.0,
                "rpm": 3000.0,
                "max_rpm": 9000.0,
                "speed_kmh": 30.0,
                "gear": 1,
            },
        )()

        for _ in range(3):
            widget.update_telemetry(player)
        player.throttle = 1.0
        widget.update_telemetry(player)
        player.throttle = 0.0
        widget.update_telemetry(player)

        self.assertEqual(widget.throttle_history[-1], 0.0)
        for _ in range(5):
            player.throttle = 1.0
            widget.update_telemetry(player)
        self.assertEqual(widget.throttle_history[-1], 1.0)
        widget.deleteLater()

    def test_timed_graph_keeps_original_samples_when_history_exceeds_point_limit(self) -> None:
        config = self._config()
        config["graph_history_points"] = 2
        widget = DriverPanelWidget("driver_panel", config)
        widget.history_times.extend([1.0, 2.0, 3.0, 4.0])
        widget.throttle_history.extend([0.0, 0.4, 0.6, 1.0])
        widget.brake_history.extend([1.0, 0.6, 0.4, 0.0])
        widget.clutch_history.extend([0.0, 0.0, 0.0, 0.0])

        throttle, brake, _, _, _, _ = widget._visible_history(now=10.5)

        self.assertEqual([point[1] for point in throttle], [0.0, 0.4, 0.6, 1.0])
        self.assertEqual([point[1] for point in brake], [1.0, 0.6, 0.4, 0.0])
        widget.deleteLater()

    def test_graph_ignores_single_sample_pedal_spike(self) -> None:
        config = self._config()
        config["pedal_smoothing"] = 0.0
        widget = DriverPanelWidget("driver_panel", config)
        widget._history_interval_s = 0.0
        player = type(
            "Player",
            (),
            {
                "throttle": 0.0,
                "brake": 0.0,
                "clutch": 0.0,
                "steering": 0.0,
                "rpm": 3000.0,
                "max_rpm": 9000.0,
                "speed_kmh": 30.0,
                "gear": 1,
            },
        )()

        for _ in range(3):
            widget.update_telemetry(player)
        player.throttle = 1.0
        widget.update_telemetry(player)
        player.throttle = 0.0
        widget.update_telemetry(player)

        self.assertEqual(widget.throttle_history[-1], 0.0)
        widget.deleteLater()

    def test_normalized_geometry_can_reach_compact_minimum(self) -> None:
        config = self._config()
        config["size"] = {"width": 0.01, "height": 0.01}
        widget = DriverPanelWidget("driver_panel", config)
        widget.apply_normalized_geometry(QRect(0, 0, 1920, 1080))
        self.assertEqual(widget.width(), 180)
        self.assertEqual(widget.height(), 70)
        widget.deleteLater()

    def test_editor_separates_geometry_from_appearance_changes(self) -> None:
        editor = DriverPanelEditor(self._config())
        geometry_events: list[tuple[str, str, object]] = []
        appearance_events: list[dict] = []
        editor.geometry_changed.connect(
            lambda section, key, value: geometry_events.append(
                (section, key, value)
            )
        )
        editor.config_changed.connect(appearance_events.append)

        editor._set_geometry_nested("size", "width", 0.35)
        self.assertEqual(geometry_events, [("size", "width", 0.35)])
        self.assertEqual(appearance_events, [])

        editor._set_nested("elements", "rpm", False)
        self.assertEqual(len(appearance_events), 1)
        editor.deleteLater()

    def test_driver_panel_drag_ratios_are_not_clamped_to_five_percent(self) -> None:
        self.assertEqual(
            OverlayManager._geometry_minimum_ratios("driver_panel"),
            (0.01, 0.01),
        )
        self.assertEqual(
            OverlayManager._geometry_minimum_ratios("standings"),
            (0.05, 0.05),
        )

    def test_editing_width_preserves_current_height_and_position(self) -> None:
        class OverlayProbe:
            def __init__(self, config: dict) -> None:
                self.config_data = {"widgets": {"driver_panel": config}}
                self.received: tuple[str, dict, bool] | None = None

            def update_widget_config(
                self,
                widget_id: str,
                config: dict,
                *,
                preserve_geometry: bool,
            ) -> None:
                self.received = widget_id, config, preserve_geometry

        current = self._config()
        current["position"] = {"x": 0.47, "y": 0.68}
        current["size"] = {"width": 0.19, "height": 0.09}
        overlay = OverlayProbe(current)
        menu = type("MenuProbe", (), {"overlay_manager": overlay})()

        MainMenuWindow._update_driver_panel_geometry(
            menu, "size", "width", 0.30
        )

        self.assertIsNotNone(overlay.received)
        widget_id, updated, preserve = overlay.received or ("", {}, True)
        self.assertEqual(widget_id, "driver_panel")
        self.assertFalse(preserve)
        self.assertEqual(updated["size"], {"width": 0.30, "height": 0.09})
        self.assertEqual(updated["position"], {"x": 0.47, "y": 0.68})


if __name__ == "__main__":
    unittest.main()
