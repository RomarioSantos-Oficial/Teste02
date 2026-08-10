from __future__ import annotations

import unittest

from src.telemetry.models import PlayerData, WheelData
from src.widget.tyres.tyres_logic import TyresLogic
from src.widget.tyres.tyres_models import TyreWheelViewData


class TyresCompoundTests(unittest.TestCase):
    def test_lmu_weighted_temperature_matches_dox_formula(self) -> None:
        logic = TyresLogic({"temperature_source": "lmu_weighted"})
        wheel = TyreWheelViewData(
            carcass_temp_c=60.0,
            inner_left_c=70.0,
            inner_center_c=80.0,
            inner_right_c=90.0,
        )

        self.assertAlmostEqual(
            logic.main_temperature_c(wheel),
            73.2,
        )

    def test_mixed_compounds_use_each_wheels_optimal_temperature(self) -> None:
        player = PlayerData(
            front_tire_compound="Medium",
            rear_tire_compound="Medium",
            wheels=[
                WheelData(compound_type=1, optimal_temp_c=92.0),
                WheelData(compound_type=3, optimal_temp_c=50.0),
                WheelData(compound_type=1, optimal_temp_c=92.0),
                WheelData(compound_type=1, optimal_temp_c=92.0),
            ],
        )
        logic = TyresLogic({"colors": {
            "tyre_cold": "cold", "tyre_optimal": "optimal",
            "tyre_warm": "warm", "tyre_hot": "hot",
        }})
        view = logic.build_view(player)
        self.assertEqual(view.front_compound, "Medium/Wet")
        self.assertEqual(view.rear_compound, "Medium")
        self.assertEqual(view.wheels[1].compound_name, "Wet")
        self.assertEqual(logic.temperature_color(view.wheels[1], 50.0), "optimal")
        self.assertEqual(logic.temperature_color(view.wheels[1], 58.0), "warm")
        self.assertEqual(logic.temperature_color(view.wheels[0], 58.0), "cold")


if __name__ == "__main__":
    unittest.main()
