from __future__ import annotations

import unittest
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from src.widget.radar.radar_widget import RadarWidget


class RadarWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_hidden_radar_reappears_when_nearby_car_arrives(self) -> None:
        widget = RadarWidget(
            "radar",
            {
                "enabled": True,
                "auto_hide_when_clear": True,
                "radar_radius_m": 15.0,
                "ahead_multiplier": 1.5,
                "behind_multiplier": 1.25,
                "colors": {},
            },
        )
        player = SimpleNamespace(
            is_player=True,
            in_garage=False,
            api_spatial_position=False,
            relative_rotated_x_m=0.0,
            relative_rotated_y_m=0.0,
        )
        far = SimpleNamespace(
            is_player=False,
            in_garage=False,
            api_spatial_position=False,
            relative_rotated_x_m=30.0,
            relative_rotated_y_m=30.0,
        )
        near = SimpleNamespace(
            is_player=False,
            in_garage=False,
            api_spatial_position=False,
            relative_rotated_x_m=2.0,
            relative_rotated_y_m=-5.0,
        )

        widget.update_from_session(
            SimpleNamespace(drivers=[player, far], track_length_m=5000.0)
        )
        self.assertFalse(widget.isVisible())
        self.assertEqual(widget.targets, [])

        # O OverlayManager continua chamando update_from_session mesmo com o
        # widget oculto. Ao surgir um carro proximo, o Radar deve reaparecer.
        widget.update_from_session(
            SimpleNamespace(drivers=[player, near], track_length_m=5000.0)
        )
        self.assertTrue(widget.isVisible())
        self.assertEqual(len(widget.targets), 1)
        self.assertEqual(widget.targets[0][1:3], (2.0, -5.0))
        widget.close()


if __name__ == "__main__":
    unittest.main()
