from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.widget.battery.battery_tracker import BatteryLapTracker


def session_for(vehicle_class: str, **player_values):
    player = SimpleNamespace(
        battery_fraction=player_values.get("battery_fraction", 0.0),
        state_of_charge=player_values.get("state_of_charge", 0.0),
        virtual_energy=player_values.get("virtual_energy", 0.0),
        electric_motor_state=player_values.get("electric_motor_state", 0),
        regen_kw=0.0,
        electric_motor_torque_nm=0.0,
        electric_motor_rpm=0.0,
        lap=1,
    )
    row = SimpleNamespace(
        is_player=True,
        vehicle_class=vehicle_class,
        lap_distance_m=100.0,
        in_pits=False,
        in_garage=False,
    )
    return SimpleNamespace(
        player=player,
        drivers=[row],
        track_name="Test Track",
        session=10,
        max_laps=0,
        current_time_s=10.0,
        track_length_m=5000.0,
    )


class BatteryTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = BatteryLapTracker(
            {"allow_virtual_energy_fallback": False}
        )

    def test_hypercar_with_battery_is_available(self) -> None:
        data = self.tracker.update(
            session_for("HYPERCAR", battery_fraction=0.65)
        )
        self.assertTrue(data.available)
        self.assertEqual(data.charge_pct, 65.0)

    def test_lmu_hyper_class_name_is_available(self) -> None:
        # Nome exato publicado atualmente pelo LMU para o BMW M Hybrid V8.
        data = self.tracker.update(
            session_for("Hyper", battery_fraction=1.0)
        )
        self.assertTrue(data.available)
        self.assertEqual(data.charge_pct, 100.0)

    def test_gt3_is_unavailable_even_with_generic_energy_fields(self) -> None:
        data = self.tracker.update(
            session_for(
                "LMGT3",
                battery_fraction=0.75,
                virtual_energy=0.90,
                electric_motor_state=2,
            )
        )
        self.assertFalse(data.available)

    def test_switching_from_hypercar_to_gt3_clears_availability(self) -> None:
        self.assertTrue(
            self.tracker.update(
                session_for("HYPERCAR", battery_fraction=0.55)
            ).available
        )
        self.assertFalse(
            self.tracker.update(
                session_for("LMGT3", battery_fraction=0.55)
            ).available
        )


if __name__ == "__main__":
    unittest.main()
