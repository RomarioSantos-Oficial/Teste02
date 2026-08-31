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

    def test_official_local_yellow_remains_visible_without_slow_car(self) -> None:
        alert = FlagsLogic({}).get_yellow_flag_car_info(
            self._session(sector_flags=(0, 1, 0))
        )

        self.assertTrue(alert.active)
        self.assertEqual(alert.driver, "BANDEIRA AMARELA")
        self.assertEqual(alert.cars, [])

    def test_full_course_state_is_recognized_during_phase_transition(self) -> None:
        alert = FlagsLogic({}).get_yellow_flag_car_info(
            self._session(yellow_flag_state=2)
        )

        self.assertTrue(alert.active)
        self.assertEqual(alert.driver, "FULL COURSE YELLOW")

    def test_clear_track_does_not_create_yellow_from_a_running_car(self) -> None:
        alert = FlagsLogic({}).get_yellow_flag_car_info(self._session())

        self.assertFalse(alert.active)


if __name__ == "__main__":
    unittest.main()
