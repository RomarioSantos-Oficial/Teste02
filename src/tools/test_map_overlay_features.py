from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QColor, QPainter
from PySide6.QtWidgets import QApplication

from src.widget.map.map_editor import MapEditor
from src.widget.map.map_widget import (
    TrackMapWidget,
    map_leader_roles,
    map_vehicle_marker_size,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class MapOverlayFeaturesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = {
            "cache_directory": str(self.root / "maps"),
            "save_map_cache": False,
            "load_map_cache": False,
            "vehicle_size": 18.0,
            "player_marker_scale": 1.10,
            "leader_marker_size": 14.0,
            "smooth_vehicle_motion": True,
            "colors": {
                "vehicle_player": "#FF54B8",
                "vehicle_outline_player": "#FFFFFF",
                "vehicle_player_marker": "#FF54B8",
            },
            "class_colors": {"HYPERCAR": "#123456"},
        }
        self.widget = TrackMapWidget("map-test", self.config)

    def tearDown(self) -> None:
        self.widget._motion_timer.stop()
        self.widget.close()
        self.temporary.cleanup()

    def test_player_marker_defaults_to_ten_percent_larger(self) -> None:
        self.assertAlmostEqual(
            map_vehicle_marker_size(18.0, 1.0, True, 1.10),
            19.8,
        )
        self.assertAlmostEqual(
            map_vehicle_marker_size(18.0, 1.0, False, 1.10),
            18.0,
        )

    def test_leader_roles_can_mark_overall_and_class_leaders(self) -> None:
        driver = SimpleNamespace(position=1, position_in_class=1)
        self.assertEqual(
            map_leader_roles(driver, {}),
            ("overall",),
        )
        self.assertEqual(
            map_leader_roles(
                driver,
                {
                    "show_overall_leader_marker": False,
                    "show_class_leader_markers": True,
                },
            ),
            ("class",),
        )
        self.assertEqual(
            map_leader_roles(
                SimpleNamespace(position=2, position_in_class=1),
                {"show_class_leader_markers": False},
            ),
            (),
        )

    def test_overall_leader_crown_takes_priority_over_class_crown(self) -> None:
        driver = SimpleNamespace(position=1, position_in_class=1)
        self.assertEqual(map_leader_roles(driver, {}), ("overall",))
        self.assertEqual(
            map_leader_roles(
                SimpleNamespace(position=2, position_in_class=1),
                {},
            ),
            ("class",),
        )

    def test_player_fill_preserves_category_color(self) -> None:
        self.assertEqual(self.widget._class_color("Hypercar").name(), "#123456")
        player = SimpleNamespace(
            is_player=True,
            in_pits=False,
            vehicle_class="HYPERCAR",
        )
        self.assertEqual(
            self.widget._vehicle_color(player, None).name(),
            "#123456",
        )

    def test_leader_markers_use_class_tint_and_allow_per_class_overrides(self) -> None:
        driver = SimpleNamespace(
            vehicle_class="HYPERCAR",
            position=2,
            position_in_class=1,
        )
        text, image, color = self.widget._leader_marker_style(driver, "class")
        self.assertEqual(text, "🏆")
        self.assertEqual(image, "")
        self.assertEqual(color.name(), "#123456")

        self.config["same_class_leader_marker"] = False
        self.config["class_leader_marker_texts"] = {"HYPERCAR": "🥇"}
        self.widget.update_config(self.config)
        text, image, color = self.widget._leader_marker_style(driver, "class")
        self.assertEqual(text, "🥇")
        self.assertEqual(image, "")
        self.assertEqual(color.name(), "#123456")

        # A escolha individual por imagem também deve substituir o padrão.
        self.config["class_leader_marker_image"] = "/shared/trophy.png"
        self.config["class_leader_marker_images"] = {
            "HYPERCAR": "/classes/hypercar.png"
        }
        self.widget.update_config(self.config)
        text, image, color = self.widget._leader_marker_style(driver, "class")
        self.assertEqual(text, "🥇")
        self.assertEqual(image, "/classes/hypercar.png")

    def test_overall_leader_has_distinct_default_emblem(self) -> None:
        driver = SimpleNamespace(
            vehicle_class="HYPERCAR",
            position=1,
            position_in_class=1,
        )
        text, image, color = self.widget._leader_marker_style(driver, "overall")
        self.assertEqual(text, "👑")
        self.assertEqual(image, "")
        self.assertEqual(color.name(), "#f5c451")

    def test_player_marker_ring_width_is_independently_configurable(self) -> None:
        self.config["vehicle_outline_player_width"] = 6.5
        self.config["colors"]["vehicle_player_marker"] = "#12ABCD"
        editor = MapEditor(self.config)
        self.assertEqual(editor.config["vehicle_outline_player_width"], 6.5)
        self.assertEqual(editor.config["colors"]["vehicle_player_marker"], "#12ABCD")
        editor.close()

    def test_interpolation_handles_world_position_and_lap_wrap(self) -> None:
        self.widget.session = SimpleNamespace(track_length_m=1000.0)
        driver = SimpleNamespace(
            driver_id="player-1",
            world_x=0.0,
            world_z=0.0,
            lap_distance_m=990.0,
        )
        self.widget._capture_vehicle_positions([driver], now=1.0)
        driver.world_x = 10.0
        driver.world_z = 20.0
        driver.lap_distance_m = 10.0
        self.widget._capture_vehicle_positions([driver], now=1.1)
        position = self.widget._position_at(
            self.widget._driver_motion_key(driver),
            now=1.15,
        )
        self.assertAlmostEqual(position[0], 5.0)
        self.assertAlmostEqual(position[1], 10.0)
        self.assertAlmostEqual(position[2], 0.0)

    def test_track_distance_position_is_interpolated_without_world_jitter(self) -> None:
        points = [
            SimpleNamespace(distance_m=0.0, world_x=0.0, world_y=0.0),
            SimpleNamespace(distance_m=100.0, world_x=100.0, world_y=0.0),
            SimpleNamespace(distance_m=200.0, world_x=100.0, world_y=100.0),
        ]
        position = self.widget._track_position_at_distance(points, 150.0, 300.0)
        self.assertEqual(position, (100.0, 50.0))
        position = self.widget._track_position_at_distance(points, 250.0, 300.0)
        self.assertEqual(position, (50.0, 50.0))

    def test_long_pause_snaps_to_latest_position(self) -> None:
        self.widget.session = SimpleNamespace(track_length_m=1000.0)
        driver = SimpleNamespace(
            driver_id="player-1",
            world_x=0.0,
            world_z=0.0,
            lap_distance_m=100.0,
        )
        self.widget._capture_vehicle_positions([driver], now=1.0)
        driver.world_x = 25.0
        driver.world_z = 50.0
        driver.lap_distance_m = 150.0
        self.widget._capture_vehicle_positions([driver], now=1.5)
        self.assertEqual(self.widget._motion_duration, 0.0)
        self.assertEqual(
            self.widget._interpolated_driver_position(driver),
            (25.0, 50.0, 150.0),
        )

    def test_player_image_is_cached_and_drawn_inside_a_circle(self) -> None:
        image_path = self.root / "player.png"
        source = QImage(80, 40, QImage.Format.Format_ARGB32)
        source.fill(QColor("#FF0000"))
        self.assertTrue(source.save(str(image_path)))
        self.config.update(
            {
                "player_marker_image": str(image_path),
                "vehicle_size": 20.0,
                "player_marker_scale": 1.0,
                "show_vehicle_standings": False,
            }
        )
        self.widget.update_config(self.config)
        cached = self.widget._cached_marker_pixmap(str(image_path), 20.0)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.size().width(), 40)
        self.assertEqual(cached.size().height(), 40)
        self.assertEqual(cached.devicePixelRatioF(), 2.0)

        canvas = QImage(60, 60, QImage.Format.Format_ARGB32)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        self.widget._draw_vehicle(
            painter,
            QPointF(30.0, 30.0),
            SimpleNamespace(is_player=True),
            None,
        )
        painter.end()
        self.assertEqual(canvas.pixelColor(20, 20).alpha(), 0)
        self.assertGreater(canvas.pixelColor(30, 30).alpha(), 0)
        self.assertEqual(canvas.pixelColor(19, 30).name(), "#ff54b8")

    def test_editor_exposes_and_emits_custom_marker_settings(self) -> None:
        editor = MapEditor(self.config)
        emitted: list[dict] = []
        editor.config_changed.connect(emitted.append)
        editor._set("leader_marker_text", "👑")
        editor._set("player_marker_image", "/tmp/player.png")
        self.assertEqual(editor.config["leader_marker_text"], "👑")
        self.assertEqual(editor.config["player_marker_image"], "/tmp/player.png")
        self.assertEqual(len(emitted), 2)
        editor.close()

    def test_map_defaults_are_present_in_all_catalog_copies(self) -> None:
        defaults = json.loads(
            (PROJECT_ROOT / "src/config/map_defaults.json").read_text(
                encoding="utf-8"
            )
        )
        catalog = json.loads(
            (PROJECT_ROOT / "src/config/widgets.json").read_text(
                encoding="utf-8"
            )
        )
        configs = [
            catalog["widgets"]["map"],
            catalog["defaults"]["map"],
            *(profile["widgets"]["map"] for profile in catalog["profiles"].values()),
        ]
        expected = {
            "show_overall_leader_marker": True,
            "show_class_leader_markers": True,
            "smooth_vehicle_motion": True,
            "player_marker_scale": 1.10,
            "leader_marker_size": 14.0,
            "leader_marker_text": "♛",
            "leader_marker_image": "",
            "player_marker_image": "",
            "leader_marker_text": "👑",
            "leader_marker_image": "",
            "class_leader_marker_text": "🏆",
            "class_leader_marker_image": "",
            "same_class_leader_marker": True,
            "class_leader_marker_texts": {
                "HYPERCAR": "", "LMP2": "", "LMP3": "", "LMGT3": "", "GTE": ""
            },
            "class_leader_marker_images": {
                "HYPERCAR": "", "LMP2": "", "LMP3": "", "LMGT3": "", "GTE": ""
            },
            "vehicle_outline_player_width": 3.0,
            "use_track_distance_positions": True,
            "vehicle_number_font_size": 10.0,
        }
        for config in [defaults, *configs]:
            for key, value in expected.items():
                self.assertEqual(config[key], value, key)
            self.assertEqual(config["colors"]["vehicle_player"], "#FF54B8")
            self.assertEqual(config["colors"]["vehicle_player_marker"], "#FF54B8")
            self.assertEqual(config["colors"]["leader_marker_overall"], "#F5C451")
            self.assertEqual(config["colors"]["vehicle_player_marker"], "#FF54B8")


if __name__ == "__main__":
    unittest.main()
