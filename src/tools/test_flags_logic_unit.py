from __future__ import annotations

import unittest

from src.telemetry.models import DriverData, SessionData
from src.widget.flags.flags_logic import FlagsLogic


class FlagsLogicUnitTests(unittest.TestCase):
    @staticmethod
    def _session(**overrides: object) -> SessionData:
        values: dict[str, object] = {
            "connected": True,
            "session": 10,
            "game_phase": 5,
            "track_length_m": 5000.0,
            "sector_flags": (0, 0, 0),
            "drivers": [
                DriverData(
                    slot_id=1,
                    driver_name="Player",
                    vehicle_class="LMGT3",
                    position=4,
                    is_player=True,
                    speed_kmh=180.0,
                    lap_distance_m=1000.0,
                ),
                DriverData(
                    slot_id=2,
                    driver_name="Running Car",
                    vehicle_class="LMGT3",
                    position=3,
                    speed_kmh=160.0,
                    lap_distance_m=1200.0,
                ),
            ],
        }
        values.update(overrides)
        return SessionData(**values)

    def test_sector_value_alone_does_not_open_local_yellow(self) -> None:
        alert = FlagsLogic({}).get_yellow_flag_car_info(
            self._session(sector_flags=(0, 1, 0))
        )

        self.assertFalse(alert.active)

    def test_stale_full_course_state_does_not_open_outside_phase_six(self) -> None:
        alert = FlagsLogic({}).get_yellow_flag_car_info(
            self._session(yellow_flag_state=2)
        )

        self.assertFalse(alert.active)

    def test_full_course_phase_is_recognized(self) -> None:
        alert = FlagsLogic({}).get_yellow_flag_car_info(
            self._session(game_phase=6)
        )

        self.assertTrue(alert.active)
        self.assertEqual(alert.driver, "FULL COURSE YELLOW")

    def test_live_stale_sector_snapshot_does_not_open_yellow(self) -> None:
        session = self._session(
            sector_flags=(11, 1, 1),
            yellow_flag_state=0,
            yellow_flag_state_name="NONE",
        )
        session.drivers[0].flag = 6

        alert = FlagsLogic({}).get_yellow_flag_car_info(session)

        self.assertFalse(alert.active)

    def test_moving_hazard_keeps_correct_distance_and_arrival_time(self) -> None:
        session = self._session(sector_flags=(1, 0, 0))
        session.drivers[1].driver_name = "Moving Hazard"
        session.drivers[1].speed_kmh = 60.0
        session.drivers[1].lap_distance_m = 1300.0
        session.drivers[1].under_yellow = True

        alert = FlagsLogic({}).get_yellow_flag_car_info(session)

        self.assertTrue(alert.active)
        self.assertEqual(alert.driver, "HAZARD")
        self.assertEqual(alert.distance, 300.0)
        self.assertAlmostEqual(alert.tempo_gap, 9.0)

    def test_stopped_player_uses_lmu_yel_fallback(self) -> None:
        session = self._session(sector_flags=(1, 0, 0))
        session.drivers[0].speed_kmh = 0.0
        session.drivers[1].under_yellow = True
        session.drivers[1].speed_kmh = 5.0
        session.drivers[1].lap_distance_m = 1005.0

        alert = FlagsLogic({}).get_yellow_flag_car_info(session)

        self.assertTrue(alert.active)
        self.assertFalse(alert.player_is_hazard)
        self.assertEqual(alert.driver, "CAR")
        self.assertEqual(alert.category, "LMGT3")
        self.assertEqual(len(alert.cars), 1)
        self.assertEqual(alert.cars[0].driver, "CAR")

    def test_unconfirmed_sector_uses_strict_reference_speed_limit(self) -> None:
        session = self._session(sector_flags=(1, 0, 0))
        session.drivers[1].speed_kmh = 60.0
        session.drivers[1].lap_distance_m = 1300.0

        alert = FlagsLogic({}).get_yellow_flag_car_info(session)

        self.assertFalse(alert.active)

        session.drivers[0].flag = 1
        alert = FlagsLogic({}).get_yellow_flag_car_info(session)

        self.assertTrue(alert.active)
        self.assertEqual(alert.distance, 300.0)

    def test_paused_game_rejects_stale_yellow_data(self) -> None:
        session = self._session(
            game_phase=9,
            sector_flags=(1, 0, 0),
        )
        session.drivers[1].under_yellow = True
        session.drivers[1].speed_kmh = 0.0

        snapshot = FlagsLogic({}).update(session)

        self.assertFalse(snapshot.yellow.active)

    def test_blue_arrival_uses_relative_closing_speed(self) -> None:
        session = self._session()
        session.drivers[0].flag = 6
        session.drivers[0].speed_kmh = 150.0
        session.drivers[1].position = 3
        session.drivers[1].speed_kmh = 250.0
        session.drivers[1].lap_distance_m = 920.0

        alert = FlagsLogic({}).get_blue_flag_car_info(session)

        self.assertTrue(alert.active)
        self.assertEqual(alert.distance, -80.0)
        self.assertAlmostEqual(alert.tempo_gap, 2.9)

    def test_blue_radar_includes_faster_car_slightly_ahead_at_flag_onset(self) -> None:
        session = self._session()
        session.drivers[0].flag = 6
        session.drivers[0].speed_kmh = 150.0
        session.drivers[0].position = 8
        session.drivers[1].position = 2
        session.drivers[1].speed_kmh = 250.0
        session.drivers[1].lap_distance_m = 1080.0

        alert = FlagsLogic({}).get_blue_flag_car_info(session)

        self.assertTrue(alert.active)
        self.assertEqual(len(alert.cars), 1)
        self.assertEqual(alert.cars[0].driver, "CAR")
        self.assertEqual(alert.cars[0].distance, 80.0)

    def test_blue_radar_excludes_car_outside_three_second_window(self) -> None:
        session = self._session()
        session.drivers[0].flag = 6
        session.drivers[0].position = 8
        session.drivers[1].position = 2
        session.drivers[1].lap_distance_m = 1800.0

        alert = FlagsLogic({}).get_blue_flag_car_info(session)

        self.assertTrue(alert.active)
        self.assertEqual(alert.driver, "BANDEIRA AZUL")
        self.assertEqual(alert.cars, [])

    def test_flagged_yellow_car_is_not_dropped_by_nearby_alert_window(self) -> None:
        session = self._session(sector_flags=(1, 0, 0))
        session.drivers[1].under_yellow = True
        session.drivers[1].speed_kmh = 180.0
        session.drivers[1].lap_distance_m = 1500.0

        alert = FlagsLogic({}).get_yellow_flag_car_info(session)

        self.assertTrue(alert.active)
        self.assertEqual(alert.driver, "CAR")
        self.assertEqual(alert.category, "LMGT3")

    def test_yellow_radar_excludes_car_outside_twelve_second_window(self) -> None:
        session = self._session(sector_flags=(1, 0, 0))
        session.drivers[1].under_yellow = True
        session.drivers[1].speed_kmh = 180.0
        session.drivers[1].lap_distance_m = 1700.0

        alert = FlagsLogic({}).get_yellow_flag_car_info(session)

        self.assertFalse(alert.active)

    def test_flag_radar_uses_tinypedal_pose_and_relative_orientation(self) -> None:
        logic = FlagsLogic({})
        player = DriverData(
            is_player=True,
            radar_position_valid=True,
            radar_longitudinal_m=100.0,
            radar_lateral_m=200.0,
            radar_orientation_yaw_rad=0.0,
        )
        car = DriverData(
            radar_position_valid=True,
            radar_longitudinal_m=103.0,
            radar_lateral_m=204.0,
            radar_orientation_yaw_rad=0.25,
        )

        x, y, orientation = logic._flag_radar_pose(player, car, 4.0)

        self.assertAlmostEqual(x, -3.0)
        self.assertAlmostEqual(y, -4.0)
        self.assertAlmostEqual(orientation, 0.25)

    def test_yellow_radar_keeps_every_eligible_car(self) -> None:
        session = self._session(sector_flags=(1, 0, 0))
        player = session.drivers[0]
        cars = []
        for slot in range(2, 67):
            cars.append(
                DriverData(
                    slot_id=slot,
                    driver_name=f"Hazard {slot}",
                    vehicle_class="LMGT3",
                    position=slot,
                    position_in_class=slot,
                    speed_kmh=5.0,
                    lap_distance_m=1050.0 + slot,
                    under_yellow=True,
                    path_lateral_m=7.0 if slot == 2 else 1.0,
                    track_edge_m=6.0,
                )
            )
        session.drivers = [player, *cars]

        alert = FlagsLogic({}).get_yellow_flag_car_info(session)

        self.assertEqual(len(alert.cars), 65)
        self.assertEqual(alert.cars[0].path_lateral_m, 7.0)
        self.assertEqual(alert.cars[0].track_edge_m, 6.0)
        self.assertEqual(alert.cars[0].player_path_lateral_m, 0.0)

    def test_clear_track_does_not_create_yellow_from_a_running_car(self) -> None:
        alert = FlagsLogic({}).get_yellow_flag_car_info(self._session())

        self.assertFalse(alert.active)


if __name__ == "__main__":
    unittest.main()
