from __future__ import annotations

import unittest

from src.telemetry.models import DriverData, SessionData
from src.widget.fuel_time.fuel_time_tracker import FuelTimeTracker
from src.widget.lap_projection import project_race_laps


class RaceLapProjectionTests(unittest.TestCase):
    @staticmethod
    def driver(
        *,
        position: int,
        class_position: int,
        vehicle_class: str,
        laps: int,
        distance: float,
        pace: float,
        laps_behind: int = 0,
        is_player: bool = False,
    ) -> DriverData:
        return DriverData(
            position=position,
            position_in_class=class_position,
            vehicle_class=vehicle_class,
            laps=laps,
            lap_distance_m=distance,
            last_lap_s=pace,
            laps_behind_leader=laps_behind,
            is_player=is_player,
        )

    def test_leader_crossing_with_two_seconds_left_starts_extra_lap(self) -> None:
        leader = self.driver(
            position=1,
            class_position=1,
            vehicle_class="HYPERCAR",
            laps=10,
            distance=990.0,
            pace=100.0,
        )
        session = SessionData(
            session=10,
            remaining_time_s=2.0,
            track_length_m=1000.0,
            drivers=[leader],
        )

        result = project_race_laps(session, leader, [leader])

        self.assertIsNotNone(result)
        self.assertEqual(result.final_laps, 12.0)
        self.assertAlmostEqual(result.global_finish_horizon_s or 0.0, 101.0)

    def test_slow_class_crossing_after_zero_but_before_leader_finish_gets_extra_lap(self) -> None:
        overall = self.driver(
            position=1,
            class_position=1,
            vehicle_class="HYPERCAR",
            laps=10,
            distance=990.0,
            pace=100.0,
        )
        gt_leader = self.driver(
            position=2,
            class_position=1,
            vehicle_class="LMGT3",
            laps=8,
            distance=950.0,
            pace=120.0,
            laps_behind=2,
        )
        session = SessionData(
            session=10,
            remaining_time_s=2.0,
            track_length_m=1000.0,
            drivers=[overall, gt_leader],
        )

        result = project_race_laps(session, gt_leader, [gt_leader])

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.class_final_laps, 9.7916666667)
        self.assertAlmostEqual(result.final_laps, 9.7916666667)
        self.assertEqual(result.finish_laps, 10.0)

    def test_class_car_reaching_line_only_after_checkered_finishes_that_lap(self) -> None:
        overall = self.driver(
            position=1,
            class_position=1,
            vehicle_class="HYPERCAR",
            laps=10,
            distance=990.0,
            pace=100.0,
        )
        gt_leader = self.driver(
            position=2,
            class_position=1,
            vehicle_class="LMGT3",
            laps=8,
            distance=0.0,
            pace=120.0,
            laps_behind=2,
        )
        session = SessionData(
            session=10,
            remaining_time_s=2.0,
            track_length_m=1000.0,
            drivers=[overall, gt_leader],
        )

        result = project_race_laps(session, gt_leader, [gt_leader])

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.final_laps, 8.8416666667)
        self.assertEqual(result.finish_laps, 9.0)

    def test_prediction_continues_when_session_clock_is_zero(self) -> None:
        leader = self.driver(
            position=1,
            class_position=1,
            vehicle_class="HYPERCAR",
            laps=10,
            distance=100.0,
            pace=100.0,
        )
        session = SessionData(
            session=10,
            remaining_time_s=0.0,
            current_time_s=3600.0,
            track_length_m=1000.0,
            drivers=[leader],
        )

        result = project_race_laps(session, leader, [leader])

        self.assertIsNotNone(result)
        self.assertEqual(result.final_laps, 11.0)
        self.assertAlmostEqual(result.global_finish_horizon_s or 0.0, 90.0)

    def test_player_total_subtracts_confirmed_class_lap_deficit(self) -> None:
        overall = self.driver(
            position=1,
            class_position=1,
            vehicle_class="HYPERCAR",
            laps=10,
            distance=500.0,
            pace=100.0,
        )
        class_leader = self.driver(
            position=5,
            class_position=1,
            vehicle_class="LMGT3",
            laps=8,
            distance=500.0,
            pace=120.0,
            laps_behind=2,
        )
        player = self.driver(
            position=9,
            class_position=3,
            vehicle_class="LMGT3",
            laps=7,
            distance=500.0,
            pace=121.0,
            laps_behind=3,
            is_player=True,
        )
        session = SessionData(
            session=10,
            remaining_time_s=200.0,
            track_length_m=1000.0,
            drivers=[overall, class_leader, player],
        )

        result = project_race_laps(
            session,
            player,
            [class_leader, player],
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.confirmed_laps_down, 1)
        self.assertEqual(result.final_laps, result.class_final_laps - 1.0)
        self.assertEqual(result.remaining_laps, result.final_laps - 7.5)

    def test_fixed_lap_race_keeps_official_limit(self) -> None:
        player = self.driver(
            position=1,
            class_position=1,
            vehicle_class="LMGT3",
            laps=4,
            distance=400.0,
            pace=90.0,
            is_player=True,
        )
        session = SessionData(
            session=10,
            max_laps=20,
            track_length_m=1000.0,
            drivers=[player],
        )

        result = project_race_laps(session, player, [player])

        self.assertIsNotNone(result)
        self.assertEqual(result.final_laps, 20.0)
        self.assertAlmostEqual(result.remaining_laps, 15.6)

    def test_fixed_lap_race_subtracts_confirmed_player_lap_deficit(self) -> None:
        leader = self.driver(
            position=1,
            class_position=1,
            vehicle_class="LMGT3",
            laps=10,
            distance=500.0,
            pace=90.0,
        )
        player = self.driver(
            position=2,
            class_position=2,
            vehicle_class="LMGT3",
            laps=9,
            distance=500.0,
            pace=91.0,
            laps_behind=1,
            is_player=True,
        )
        session = SessionData(
            session=10,
            max_laps=20,
            track_length_m=1000.0,
            drivers=[leader, player],
        )

        result = project_race_laps(session, player, [leader, player])

        self.assertIsNotNone(result)
        self.assertEqual(result.class_final_laps, 20.0)
        self.assertEqual(result.final_laps, 19.0)
        self.assertAlmostEqual(result.remaining_laps, 9.5)

    def test_finished_player_does_not_receive_another_predicted_lap(self) -> None:
        player = self.driver(
            position=1,
            class_position=1,
            vehicle_class="LMGT3",
            laps=18,
            distance=0.0,
            pace=90.0,
            is_player=True,
        )
        player.finish_status = 1
        session = SessionData(
            session=10,
            remaining_time_s=0.0,
            current_time_s=3600.0,
            track_length_m=1000.0,
            drivers=[player],
        )

        result = project_race_laps(session, player, [player])

        self.assertIsNotNone(result)
        self.assertEqual(result.final_laps, 18.0)
        self.assertEqual(result.remaining_laps, 0.0)

    def test_fuel_time_uses_the_same_player_projection_at_zero(self) -> None:
        leader = self.driver(
            position=1,
            class_position=1,
            vehicle_class="LMGT3",
            laps=10,
            distance=100.0,
            pace=100.0,
        )
        player = self.driver(
            position=2,
            class_position=2,
            vehicle_class="LMGT3",
            laps=9,
            distance=100.0,
            pace=101.0,
            laps_behind=1,
            is_player=True,
        )
        session = SessionData(
            session=10,
            remaining_time_s=0.0,
            current_time_s=3600.0,
            track_length_m=1000.0,
            drivers=[leader, player],
        )

        projection = project_race_laps(session, player, [leader, player])
        remaining, reference = FuelTimeTracker({})._remaining_laps(
            session,
            player,
        )

        self.assertIsNotNone(projection)
        self.assertAlmostEqual(
            remaining or 0.0,
            projection.finish_remaining_laps,
        )
        self.assertIn("lider geral", reference)


if __name__ == "__main__":
    unittest.main()
