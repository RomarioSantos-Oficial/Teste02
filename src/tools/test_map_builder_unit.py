from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.telemetry.models import PlayerData
from src.widget.map.map_builder import TrackMapBuilder


class TrackMapBuilderValidityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = {
            "cache_directory": str(self.root / "maps"),
            "save_map_cache": True,
            "load_map_cache": True,
            "mapping_sample_distance_m": 2.0,
            "minimum_mapping_points": 30,
            "minimum_mapping_coverage": 0.90,
            "maximum_mapping_path_lateral_m": 35.0,
        }
        self.builder = TrackMapBuilder(self.root, self.config)
        self.player = PlayerData(lap=1)
        self.driver = SimpleNamespace(
            is_player=True,
            laps=1,
            lap_distance_m=0.0,
            world_x=0.0,
            world_z=0.0,
            current_sector=1,
            path_lateral_m=0.0,
            in_pits=False,
            in_garage=False,
            pit_state=0,
            current_lap_invalidated=False,
            last_lap_invalidated=False,
            last_lap_s=0.0,
        )
        self.session = SimpleNamespace(
            track_name="Validation Circuit",
            track_length_m=1000.0,
            current_time_s=0.0,
            player=self.player,
            drivers=[self.driver],
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _record_complete_lap(self) -> None:
        for index in range(41):
            progress = index / 40.0
            angle = progress * math.tau
            self.session.current_time_s = progress * 10.0
            self.driver.lap_distance_m = progress * 1000.0
            self.driver.world_x = math.cos(angle) * 100.0
            self.driver.world_z = math.sin(angle) * 100.0
            self.driver.current_sector = min(3, int(progress * 3) + 1)
            data = self.builder.update(self.session)
            self.assertFalse(data.complete)
            self.assertEqual(data.points, [])

    def _cross_finish_line(self) -> None:
        self.player.lap = 2
        self.driver.laps = 2
        self.driver.lap_distance_m = 0.0
        self.driver.world_x = 100.0
        self.driver.world_z = 0.0
        self.driver.current_sector = 1
        self.session.current_time_s = 10.1
        self.builder.update(self.session)

    def test_only_publishes_and_saves_after_valid_lap_confirmation(self) -> None:
        self._record_complete_lap()
        self._cross_finish_line()

        self.driver.last_lap_s = 60.0
        self.session.current_time_s = 10.5
        waiting = self.builder.update(self.session)
        self.assertFalse(waiting.complete)
        self.assertEqual(waiting.points, [])

        self.session.current_time_s = 11.2
        completed = self.builder.update(self.session)
        self.assertTrue(completed.complete)
        self.assertGreaterEqual(len(completed.points), 30)

        cache = self.root / "maps" / "validation_circuit_1000.json"
        payload = json.loads(cache.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 2)

    def test_discards_invalid_completed_lap(self) -> None:
        self._record_complete_lap()
        self._cross_finish_line()

        self.player.last_lap_invalidated = True
        self.driver.last_lap_invalidated = True
        self.driver.last_lap_s = 60.0
        self.session.current_time_s = 11.2
        result = self.builder.update(self.session)

        self.assertFalse(result.complete)
        self.assertEqual(result.points, [])
        self.assertEqual(self.builder.pending_points, [])
        self.assertFalse((self.root / "maps").exists())

    def test_waits_for_official_validity_instead_of_discarding_first_frame(self) -> None:
        self._record_complete_lap()
        self._cross_finish_line()

        # Primeiro quadro do LMU: mLastLapTime ainda está zerado e o fallback
        # do scoring marca a volta provisoriamente como inválida.
        self.player.last_lap_invalidated = True
        self.driver.last_lap_invalidated = True
        self.driver.last_lap_s = 0.0
        self.session.current_time_s = 10.2
        waiting = self.builder.update(self.session)
        self.assertFalse(waiting.complete)
        self.assertTrue(self.builder.pending_points)

        # Após a janela de confirmação chega o tempo oficial válido.
        self.player.last_lap_invalidated = False
        self.driver.last_lap_invalidated = False
        self.driver.last_lap_s = 60.0
        self.session.current_time_s = 11.2
        completed = self.builder.update(self.session)
        self.assertTrue(completed.complete)

    def test_invalid_current_lap_is_removed_from_recording(self) -> None:
        self._record_complete_lap()
        self.player.current_lap_invalidated = True
        self.driver.current_lap_invalidated = True

        result = self.builder.update(self.session)

        self.assertEqual(result.points, [])
        self.assertEqual(self.builder.current_points, [])
        self.assertTrue(self.builder.current_lap_rejected)

    def test_valid_timing_does_not_save_an_incomplete_lap_shape(self) -> None:
        for index in range(33):
            progress = index / 40.0
            angle = progress * math.tau
            self.session.current_time_s = progress * 10.0
            self.driver.lap_distance_m = progress * 1000.0
            self.driver.world_x = math.cos(angle) * 100.0
            self.driver.world_z = math.sin(angle) * 100.0
            self.builder.update(self.session)

        self._cross_finish_line()
        self.driver.last_lap_s = 60.0
        self.session.current_time_s = 11.2
        result = self.builder.update(self.session)

        self.assertFalse(result.complete)
        self.assertEqual(result.points, [])
        self.assertFalse((self.root / "maps").exists())

    def test_rejects_non_increasing_distance_points(self) -> None:
        self.driver.lap_distance_m = 100.0
        self.builder.update(self.session)
        self.driver.lap_distance_m = 90.0
        self.driver.world_x = 500.0
        self.builder.update(self.session)

        self.assertEqual(len(self.builder.current_points), 1)

    def test_legacy_cache_is_not_loaded(self) -> None:
        cache_dir = self.root / "maps"
        cache_dir.mkdir(parents=True)
        cache = cache_dir / "validation_circuit_1000.json"
        cache.write_text(
            json.dumps({"version": 1, "points": []}),
            encoding="utf-8",
        )

        result = self.builder.update(self.session)

        self.assertFalse(result.loaded_from_cache)


if __name__ == "__main__":
    unittest.main()
