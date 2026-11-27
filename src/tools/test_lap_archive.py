from __future__ import annotations

import itertools
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.laps import archive
from src.laps.archive import LapArchiveStore, LapRecord, LapRecorder


def make_record(owner: str, lap_s: float, scope: str = "category") -> LapRecord:
    trace = [
        {
            "distance": index / 239,
            "elapsed_s": lap_s * index / 239,
            "throttle": 0.6,
            "brake": 0.1,
            "speed_kmh": 180.0,
        }
        for index in range(240)
    ]
    return LapRecord(
        record_id=f"{owner}-{scope}-{lap_s}", scope=scope,
        track="Silverstone", category="LMGT3", car_model="Ferrari 296 GT3",
        car_filename="ferrari_296_gt3", car_number="17", slot_id=17,
        lap_seconds=lap_s, sector1=lap_s / 3, sector2=lap_s / 3,
        sector3=lap_s / 3, trace=trace, saved_at=time.time(),
        session_key=f"session-{owner}", owner_key=owner, driver_name="R. Lima",
    )


class LapArchiveStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = LapArchiveStore(Path(self.temporary.name) / "laps.sqlite3")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_personal_bests_are_isolated_by_account_and_improve_only(self) -> None:
        self.assertEqual(len(self.store.save_if_better(make_record("account-a", 100.0))), 2)
        self.assertEqual(self.store.save_if_better(make_record("account-a", 101.0)), [])
        self.assertEqual(len(self.store.save_if_better(make_record("account-a", 98.0))), 2)
        self.assertEqual(len(self.store.save_if_better(make_record("account-b", 105.0))), 2)

        self.assertEqual(self.store.best("Silverstone", "LMGT3", owner_key="account-a").lap_seconds, 98.0)
        self.assertEqual(self.store.best("Silverstone", "LMGT3", owner_key="account-b").lap_seconds, 105.0)
        self.assertEqual(len(self.store.all_personal_bests("account-a")), 2)
        self.assertEqual(len(self.store.all_personal_bests("account-b")), 2)

    def test_offline_import_is_explicit_and_retains_source_records(self) -> None:
        self.store.save_if_better(make_record("offline", 100.0))
        self.assertEqual(self.store.import_offline_records("account-a"), 2)
        self.assertEqual(len(self.store.all_personal_bests("offline")), 2)
        imported = self.store.all_personal_bests("account-a")
        self.assertEqual(len(imported), 2)
        self.assertTrue(all(record.pending_upload for record in imported))
        self.assertEqual(self.store.import_offline_records("account-a"), 0)

    def test_active_profile_setting_is_shared_without_persisting_legacy_owner_field(self) -> None:
        settings_path = Path(self.temporary.name) / "lap_cloud.json"
        previous = (
            archive._ACTIVE_OWNER_KEY,
            archive._OWNER_CONTEXT_CHECKED_AT,
            archive._OWNER_CONTEXT_MTIME_NS,
        )
        try:
            with patch("src.laps.archive.cloud_settings_path", return_value=settings_path):
                settings_path.write_text('{"owner_key":"old-account","api_url":"https://example.test"}', encoding="utf-8")
                archive.set_active_owner_key("discord-account-a")
                self.assertEqual(archive.local_owner_key(), "discord-account-a")
                settings = __import__("json").loads(settings_path.read_text(encoding="utf-8"))
                self.assertNotIn("owner_key", settings)
                self.assertEqual(settings["api_url"], "https://example.test")
                archive.set_active_owner_key("offline")
                self.assertEqual(archive.local_owner_key(), "offline")
        finally:
            (
                archive._ACTIVE_OWNER_KEY,
                archive._OWNER_CONTEXT_CHECKED_AT,
                archive._OWNER_CONTEXT_MTIME_NS,
            ) = previous

    def test_recorder_saves_a_complete_valid_lap_with_game_driver_identity(self) -> None:
        recorder = LapRecorder(self.store)
        recorder.set_owner_key("discord-account-a")
        clock = itertools.count()
        player = SimpleNamespace(current_lap_invalidated=False, throttle=0.6, brake=0.1, speed_kmh=180.0)
        driver = SimpleNamespace(
            is_player=True, slot_id=17, driver_name="R. Lima", laps=1,
            lap_distance_m=0.0, time_into_lap_s=0.0, lap_start_event_time_s=0.0,
            last_lap_s=0.0, last_lap_invalidated=False,
            last_sector1_s=33.0, last_sector2_s=33.0, last_sector3_s=34.0,
            vehicle_class="LMGT3", vehicle_model="Ferrari 296 GT3",
            vehicle_filename="ferrari_296_gt3", car_number="17",
        )
        session = SimpleNamespace(
            connected=True, telemetry_paused=False, is_replay_active=False,
            player_has_vehicle=True, in_realtime=True, race_finished=False,
            server_name="Official Online Server",
            track_name="Silverstone", session=1, start_event_time_s=5.0,
            track_length_m=5000.0, current_event_time_s=0.0,
            player=player, drivers=[driver],
        )
        saved = []
        with patch("src.laps.archive.time.monotonic", side_effect=lambda: next(clock) * 0.05):
            for index in range(61):
                fraction = index / 60
                driver.lap_distance_m = fraction * session.track_length_m
                driver.time_into_lap_s = fraction * 100.0
                saved.extend(recorder.observe(session))
            driver.laps = 2
            driver.lap_distance_m = 0.0
            driver.time_into_lap_s = 0.0
            driver.last_lap_s = 100.0
            saved.extend(recorder.observe(session))

        self.assertEqual(len(saved), 2)
        self.assertTrue(all(record.owner_key == "discord-account-a" for record in saved))
        self.assertTrue(all(record.driver_name == "R. Lima" for record in saved))
        self.assertTrue(all(record.car_number == "17" for record in saved))
        self.assertTrue(all(len(record.trace) == 240 for record in saved))

    def test_resampled_trace_uses_official_completed_lap_time_at_finish(self) -> None:
        samples = [
            (
                index / 60.0 * 0.99,
                index / 60.0 * 51.7,
                0.5,
                0.1,
                180.0,
            )
            for index in range(61)
        ]
        trace = LapRecorder._resample(samples, 5000.0, lap_seconds=52.0)
        self.assertIsNotNone(trace)
        self.assertAlmostEqual(trace[-1]["distance"], 1.0)
        self.assertAlmostEqual(trace[-1]["elapsed_s"], 52.0)

    def test_recorder_never_persists_offline_session_laps(self) -> None:
        recorder = LapRecorder(self.store)
        recorder.set_owner_key("discord-account-a")
        clock = itertools.count()
        player = SimpleNamespace(current_lap_invalidated=False, throttle=0.6, brake=0.1, speed_kmh=180.0)
        driver = SimpleNamespace(
            is_player=True, slot_id=17, driver_name="R. Lima", laps=1,
            lap_distance_m=0.0, time_into_lap_s=0.0, lap_start_event_time_s=0.0,
            last_lap_s=0.0, last_lap_invalidated=False,
            last_sector1_s=33.0, last_sector2_s=33.0, last_sector3_s=34.0,
            vehicle_class="LMGT3", vehicle_model="Ferrari 296 GT3",
            vehicle_filename="ferrari_296_gt3", car_number="17",
        )
        session = SimpleNamespace(
            connected=True, telemetry_paused=False, is_replay_active=False,
            player_has_vehicle=True, in_realtime=True, race_finished=False,
            server_name="Single Player", track_name="Silverstone", session=1,
            start_event_time_s=5.0, track_length_m=5000.0, current_event_time_s=0.0,
            player=player, drivers=[driver],
        )
        saved = []
        with patch("src.laps.archive.time.monotonic", side_effect=lambda: next(clock) * 0.05):
            for index in range(61):
                fraction = index / 60
                driver.lap_distance_m = fraction * session.track_length_m
                driver.time_into_lap_s = fraction * 100.0
                saved.extend(recorder.observe(session))
            driver.laps = 2
            driver.lap_distance_m = 0.0
            driver.time_into_lap_s = 0.0
            driver.last_lap_s = 100.0
            saved.extend(recorder.observe(session))

        self.assertEqual(saved, [])
        self.assertEqual(self.store.all_personal_bests("discord-account-a"), [])
        self.assertEqual(self.store.all_personal_bests("offline"), [])


if __name__ == "__main__":
    unittest.main()
