from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from src.widget.driver_panel.driver_panel_renderer import (
    DriverPanelRenderer,
    DriverPanelViewData,
)
from src.widget.driver_panel.driver_panel_widget import DriverPanelWidget


class DriverPanelVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_renderer_draws_standard_and_compact_layouts(self) -> None:
        renderer = DriverPanelRenderer()
        config = {
            "colors": {
                "background": "#10151D",
                "panel": "#080C12",
                "graph_background": "#080C12",
                "pedals_background": "#080C12",
                "rpm_background": "#080C12",
                "steering_background": "#080C12",
                "throttle": "#50DF42",
                "brake": "#FF2438",
                "clutch": "#29A8FF",
            },
            "elements": {},
            "pedal_elements": {},
            "layout": {"rpm_segments": 10, "shift_start": 0.88, "rpm_flash_start": 0.99},
            "font": {"family": "Sans Serif", "scale": 1.0},
            "graph_show_grid": True,
            "graph_curve_glow": True,
        }
        data = DriverPanelViewData(
            speed_kmh=245.0,
            rpm=8120.0,
            max_rpm=9000.0,
            gear=5,
            throttle=0.82,
            brake=0.12,
            clutch=0.0,
            steering=0.2,
            max_throttle_seen=1.0,
            max_brake_seen=0.86,
        )
        for width, height in ((1380, 420), (520, 190), (240, 100)):
            for rpm_ratio, flash_phase in ((0.88, False), (0.91, False), (0.94, False), (0.96, False), (0.99, False), (0.991, False), (1.00, False), (1.00, True), (1.02, False)):
                image = QImage(width, height, QImage.Format.Format_ARGB32)
                image.fill(QColor(0, 0, 0, 0))
                painter = QPainter(image)
                flashing_data = DriverPanelViewData(
                    speed_kmh=data.speed_kmh,
                    rpm=data.max_rpm * rpm_ratio,
                    max_rpm=data.max_rpm,
                    gear=data.gear,
                    throttle=data.throttle,
                    brake=data.brake,
                    clutch=data.clutch,
                    steering=data.steering,
                    max_throttle_seen=data.max_throttle_seen,
                    max_brake_seen=data.max_brake_seen,
                    rpm_flash_phase=flash_phase,
                )
                renderer.draw(
                    painter, QRectF(0, 0, width, height), flashing_data,
                    [0.1, 0.2, 0.4, 0.7, 0.82],
                    [0.0, 0.2, 0.9, 0.3, 0.12],
                    [0.0, 0.0, 0.0, 0.0, 0.0],
                    [], [], [], config,
                )
                painter.end()
                self.assertFalse(image.isNull())
                self.assertNotEqual(image.pixelColor(width // 2, height // 2).alpha(), 0)


    def test_steering_marker_tracks_the_rim_without_a_center_dot(self) -> None:
        renderer = DriverPanelRenderer()
        image = QImage(200, 200, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        renderer._wheel(
            painter,
            QRectF(0, 0, 200, 200),
            DriverPanelViewData(steering=0.25),
            {},
            QColor("#FFFFFF"),
            {
                "elements": {"steering": True, "steering_marker": True, "speed": False},
                "steering_visual_degrees": 180,
                "colors": {"wheel": "#292929", "steering_marker": "#FFD21F"},
            },
            1.0,
        )
        painter.end()
        self.assertEqual(image.pixelColor(100, 100).alpha(), 0)
        marker_color = image.pixelColor(155, 45)
        self.assertGreater(marker_color.red(), 220)
        self.assertGreater(marker_color.green(), 150)
        self.assertLess(marker_color.blue(), 80)


    def test_rpm_flash_phase_uses_configured_frequency(self) -> None:
        phase = DriverPanelWidget._rpm_flash_phase_at
        self.assertTrue(phase(0.000, 10))
        self.assertFalse(phase(0.100, 10))
        self.assertTrue(phase(0.200, 10))
        self.assertFalse(phase(0.010, 100))
        self.assertTrue(phase(0.020, 100))

    def test_rpm_warning_starts_at_exactly_99_percent(self) -> None:
        renderer = DriverPanelRenderer()

        def sample_light(ratio: float) -> QColor:
            image = QImage(1000, 100, QImage.Format.Format_ARGB32)
            image.fill(QColor(0, 0, 0, 0))
            painter = QPainter(image)
            renderer._rpm_header(
                painter,
                QRectF(0, 0, 1000, 100),
                20.0,
                20.0,
                DriverPanelViewData(
                    rpm=9000.0 * ratio,
                    max_rpm=9000.0,
                    rpm_flash_phase=True,
                ),
                {
                    "layout": {
                        "shift_start": 0.88,
                        "shift_light_1": 0.91,
                        "shift_light_2": 0.94,
                        "shift_light_3": 0.96,
                        "rpm_flash_start": 0.99,
                    },
                    "colors": {"rpm_high": "#FF2438", "rpm_flash": "#9B5CFF"},
                    "font": {"family": "Sans Serif", "scale": 1.0},
                },
                QColor("#FFFFFF"),
                1.0,
            )
            painter.end()
            return image.pixelColor(541, 14)

        below_limit = sample_light(0.989)
        at_limit = sample_light(0.99)
        self.assertGreater(below_limit.red(), 220)
        self.assertLess(below_limit.blue(), 100)
        self.assertGreater(at_limit.blue(), 200)
        self.assertLess(at_limit.red(), 220)


    def test_rpm_bar_uses_requested_color_thresholds_and_flashes_at_97(self) -> None:
        renderer = DriverPanelRenderer()
        colors = {
            "rpm_green": "#2BD158",
            "rpm_yellow": "#FFC400",
            "rpm_blue": "#258DFF",
            "rpm_high": "#FF2438",
            "rpm_flash": "#9B5CFF",
        }
        config = {
            "colors": colors,
            "layout": {
                "rpm_green_start": 0.88,
                "rpm_yellow_1_start": 0.90,
                "rpm_yellow_2_start": 0.92,
                "rpm_blue_1_start": 0.95,
                "rpm_blue_2_start": 0.969,
                "rpm_bar_flash_start": 0.97,
            },
        }
        rect = QRectF(0, 0, 1000, 100)

        def sample(ratio: float, phase: bool = False) -> list[QColor]:
            image = QImage(1000, 100, QImage.Format.Format_ARGB32)
            image.fill(QColor(0, 0, 0, 0))
            painter = QPainter(image)
            renderer._rpm(
                painter, rect,
                DriverPanelViewData(rpm=9000 * ratio, max_rpm=9000, rpm_flash_phase=phase),
                config, {}, QColor("#FFFFFF"), QColor("#AAAAAA"), 1.0,
            )
            painter.end()
            # centers of the ten RPM blocks (the bar is inset 2px and has 3px gaps)
            return [image.pixelColor(round(2 + (i + 0.5) * ((996 - 27) / 10 + 3)), 50) for i in range(10)]

        at_green = sample(0.88)
        self.assertEqual(at_green[0].name(), "#2bd158")
        self.assertEqual(at_green[1].name(), "#171717")
        at_yellow = sample(0.90)
        self.assertEqual(at_yellow[1].name(), "#ffc400")
        at_blue = sample(0.95)
        self.assertEqual(at_blue[3].name(), "#258dff")
        self.assertEqual(at_blue[4].name(), "#171717")
        at_second_blue = sample(0.969)
        self.assertEqual(at_second_blue[4].name(), "#258dff")
        flashing = sample(0.97, True)
        self.assertEqual(flashing[0].name(), "#9b5cff")
        self.assertEqual(flashing[4].name(), "#9b5cff")

if __name__ == "__main__":
    unittest.main()
