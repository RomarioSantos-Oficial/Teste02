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
            radar_position_valid=True,
            radar_longitudinal_m=0.0,
            radar_lateral_m=0.0,
            radar_orientation_yaw_rad=0.0,
            radar_elapsed_time_s=1.0,
        )
        far = SimpleNamespace(
            is_player=False,
            in_garage=False,
            api_spatial_position=False,
            radar_position_valid=True,
            radar_longitudinal_m=-30.0,
            radar_lateral_m=-30.0,
            radar_orientation_yaw_rad=0.0,
            radar_elapsed_time_s=1.0,
            slot_id=3,
        )
        near = SimpleNamespace(
            is_player=False,
            in_garage=False,
            api_spatial_position=False,
            radar_position_valid=True,
            radar_longitudinal_m=-2.0,
            radar_lateral_m=5.0,
            radar_orientation_yaw_rad=0.0,
            radar_elapsed_time_s=1.0,
            slot_id=2,
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
        self.assertAlmostEqual(widget.targets[0][1], 2.0)
        self.assertAlmostEqual(widget.targets[0][2], -5.0)
        widget.close()

    def test_api_fallback_requires_both_lap_and_lateral_positions(self) -> None:
        widget = RadarWidget("radar", {"radar_radius_m": 15.0, "colors": {}})
        player = SimpleNamespace(
            spatial_position_valid=False,
            api_spatial_position=True,
            api_lateral_position=False,
            lap_distance_m=100.0,
            path_lateral_m=0.0,
        )
        other = SimpleNamespace(
            spatial_position_valid=False,
            api_spatial_position=True,
            api_lateral_position=False,
            lap_distance_m=105.0,
            path_lateral_m=10.0,
        )
        self.assertEqual(widget._relative_position(player, other, 1000.0), (0.0, 0.0, "INVALID"))
        player.api_lateral_position = other.api_lateral_position = True
        self.assertEqual(widget._relative_position(player, other, 1000.0), (10.0, -5.0, "API"))

    def test_shared_memory_radar_matches_tinypedal_coordinate_rotation(self) -> None:
        widget = RadarWidget("radar", {"radar_radius_m": 15.0, "colors": {}})
        player = SimpleNamespace(
            radar_position_valid=True,
            radar_longitudinal_m=100.0,
            radar_lateral_m=200.0,
            radar_orientation_yaw_rad=0.0,
        )
        other = SimpleNamespace(
            radar_position_valid=True,
            radar_longitudinal_m=103.0,
            radar_lateral_m=204.0,
            radar_orientation_yaw_rad=0.25,
            radar_elapsed_time_s=2.0,
            slot_id=2,
        )
        # TinyPedal rotates the delta by player_yaw - pi and draws this raw
        # y coordinate directly (it does not invert it a second time).
        x, y, source = widget._relative_position(player, other, 5000.0, 2.0)
        self.assertEqual(source, "MEM")
        self.assertAlmostEqual(x, -3.0)
        self.assertAlmostEqual(y, -4.0)
        widget.close()


if __name__ == "__main__":
    unittest.main()
