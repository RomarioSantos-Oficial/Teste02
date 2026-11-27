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
            "layout": {"rpm_segments": 28, "shift_start": 0.78, "red_start": 0.92},
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
            for rpm_ratio, flash_phase in ((0.88, False), (0.91, False), (0.94, False), (0.96, False), (1.00, False), (1.00, True)):
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


if __name__ == "__main__":
    unittest.main()
