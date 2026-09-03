from __future__ import annotations

import unittest
from unittest.mock import patch

from src.telemetry.models import DriverData, PlayerData, SessionData
from src.widget.lap_timer.lap_timer_tracker import LapTimerTracker
from src.widget.lap_timer.lap_timer_widget import format_lap


class LapTimerTrackerTests(unittest.TestCase):
    def session(self, *, max_laps: int = 0) -> SessionData:
        player = PlayerData(lap=4, delta_best_s=-1.0)
        leader = DriverData(
            vehicle_class="GTE", position=1, position_in_class=1,
            laps=5, last_lap_s=90.0, best_lap_s=89.8,
        )
        driver = DriverData(
            is_player=True, vehicle_class="GTE", position=8,
            position_in_class=3, laps=4, time_into_lap_s=32.5,
            last_lap_s=92.4, best_lap_s=91.8, estimated_lap_s=91.9,
            best_sector1_s=30.0, best_sector2_s=30.5,
            best_sector3_s=31.3, lap_distance_m=2000.0,
        )
        return SessionData(
            connected=True, in_realtime=True, player=player,
            drivers=[leader, driver], track_name="Test", session=10,
            remaining_time_s=600.0, max_laps=max_laps,
            track_length_m=5000.0,
        )

    def test_direct_lap_times_and_positions(self) -> None:
        data = LapTimerTracker().update(self.session())
        self.assertEqual(data.last_lap_s, 92.4)
        self.assertEqual(data.best_lap_s, 91.8)
        self.assertAlmostEqual(data.theoretical_lap_s, 91.8)
        self.assertEqual(data.completed_laps, 4)
        self.assertEqual(data.current_lap, 5)
        self.assertEqual((data.position, data.class_position), (8, 3))
        self.assertAlmostEqual(data.predicted_lap_s, 90.8)

    def test_prediction_follows_live_delta(self) -> None:
        session = self.session()
        tracker = LapTimerTracker()
        self.assertAlmostEqual(tracker.update(session).predicted_lap_s, 90.8)
        session.player.delta_best_s = 0.7
        self.assertAlmostEqual(tracker.update(session).predicted_lap_s, 92.5)

    def test_fixed_lap_race_is_exact(self) -> None:
        data = LapTimerTracker().update(self.session(max_laps=20))
        self.assertEqual(data.estimated_total_laps, 20.0)
        self.assertAlmostEqual(data.remaining_laps or 0.0, 15.6)

    def test_timed_race_produces_position_aware_estimate(self) -> None:
        data = LapTimerTracker().update(self.session())
        self.assertIsNotNone(data.estimated_total_laps)
        self.assertIsNotNone(data.remaining_laps)
        self.assertGreater(data.estimated_total_laps or 0.0, 4.0)

    def test_lap_formatter(self) -> None:
        self.assertEqual(format_lap(92.487, 3), "1:32.487")
        self.assertEqual(format_lap(92.487, 2), "1:32.49")

    def test_stale_lower_sample_does_not_move_stopwatch_backwards(self) -> None:
        session = self.session()
        driver = next(row for row in session.drivers if row.is_player)
        driver.time_into_lap_s = 6.0
        tracker = LapTimerTracker()
        with patch("src.widget.lap_timer.lap_timer_tracker.time.monotonic", return_value=100.0):
            tracker.update(session)
        driver.time_into_lap_s = 4.0
        with patch("src.widget.lap_timer.lap_timer_tracker.time.monotonic", return_value=100.1):
            tracker.update(session)
            self.assertGreaterEqual(tracker.current_lap_time(), 6.09)

    def test_authoritative_lap_change_resets_stopwatch(self) -> None:
        session = self.session()
        driver = next(row for row in session.drivers if row.is_player)
        driver.time_into_lap_s = 92.0
        tracker = LapTimerTracker()
        with patch("src.widget.lap_timer.lap_timer_tracker.time.monotonic", return_value=200.0):
            tracker.update(session)
        driver.laps += 1
        driver.time_into_lap_s = 0.3
        with patch("src.widget.lap_timer.lap_timer_tracker.time.monotonic", return_value=200.1):
            tracker.update(session)
            self.assertAlmostEqual(tracker.current_lap_time(), 0.3)

    def test_live_scoring_prevents_stale_rest_lap_and_timer(self) -> None:
        session = self.session()
        driver = next(row for row in session.drivers if row.is_player)
        driver.laps = 3
        driver.time_into_lap_s = 344.0
        driver.lap_start_event_time_s = 100.0
        driver.live_scoring = {
            "laps": 4,
            "time_into_lap_s": 26.027,
            "lap_start_event_time_s": 400.0,
            "lap_distance_m": 2100.0,
        }
        tracker = LapTimerTracker()
        with patch("src.widget.lap_timer.lap_timer_tracker.time.monotonic", return_value=500.0):
            data = tracker.update(session)
        self.assertEqual(data.completed_laps, 4)
        self.assertEqual(data.current_lap, 5)
        self.assertAlmostEqual(data.current_lap_s, 26.027)


if __name__ == "__main__":
    unittest.main()
