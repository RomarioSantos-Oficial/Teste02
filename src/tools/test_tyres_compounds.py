from __future__ import annotations

import unittest

from src.telemetry.models import PlayerData, WheelData
from src.widget.tyres.tyres_logic import TyresLogic
from src.widget.tyres.tyres_models import TyreWheelViewData


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TyresCompoundTests(unittest.TestCase):
    @staticmethod
    def _wheel(
        *,
        inner_c: float = 75.0,
        carcass_c: float = 68.0,
        surface_c: float = 72.0,
        rotation_rad_s: float = 80.0,
    ) -> WheelData:
        return WheelData(
            surface_left_c=surface_c - 1.0,
            surface_center_c=surface_c,
            surface_right_c=surface_c + 1.0,
            inner_left_c=inner_c,
            inner_center_c=inner_c,
            inner_right_c=inner_c,
            carcass_temp_c=carcass_c,
            rotation_rad_s=rotation_rad_s,
            wear=1.0,
        )

    @staticmethod
    def _config(source: str = "inner_average") -> dict:
        return {
            "temperature_source": source,
            "lmp3_temperature_mode": True,
            "lmp3_temperature_source": "inner_average",
            "lmp3_detection_keywords": "lmp3",
            "gte_temperature_mode": True,
            "gte_temperature_source": "carcass",
            "gte_detection_keywords": "gte,lmgt3,gt3",
            "hyper_temperature_mode": True,
            "hyper_temperature_source": "lmu_weighted",
            "hyper_detection_keywords": "hyper,hypercar,lmh,lmdh",
            "temperature_stale_fallback_enabled": True,
            "temperature_stale_timeout_s": 3.0,
            "temperature_stale_epsilon_c": 0.02,
            "temperature_stale_aux_delta_c": 0.35,
            "temperature_stale_min_speed_kmh": 20.0,
        }

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

    def test_hyper_uses_weighted_source_instead_of_frozen_inner_only(self) -> None:
        player = PlayerData(
            vehicle_class="Hyper",
            vehicle_model="Porsche 963",
            speed_kmh=180.0,
            wheels=[self._wheel()],
        )
        logic = TyresLogic(self._config("inner_average"))

        wheel = logic.build_view(player).wheels[0]

        self.assertAlmostEqual(logic.main_temperature_c(wheel), 72.62)
        self.assertFalse(logic.temperature_source_stale(0))

    def test_lmp2_falls_back_when_inner_temperature_really_freezes(self) -> None:
        clock = _Clock()
        player = PlayerData(
            vehicle_class="LMP2",
            speed_kmh=180.0,
            wheels=[self._wheel()],
        )
        logic = TyresLogic(self._config(), clock=clock)
        first = logic.build_view(player).wheels[0]
        self.assertEqual(logic.main_temperature_c(first), 75.0)

        clock.advance(3.1)
        player.wheels[0].carcass_temp_c = 72.0
        player.wheels[0].surface_left_c = 79.0
        player.wheels[0].surface_center_c = 80.0
        player.wheels[0].surface_right_c = 81.0
        frozen = logic.build_view(player).wheels[0]

        self.assertTrue(logic.temperature_source_stale(0))
        self.assertAlmostEqual(logic.main_temperature_c(frozen), 73.98)

    def test_stale_inner_source_returns_when_lmu_resumes_it(self) -> None:
        clock = _Clock()
        player = PlayerData(
            vehicle_class="LMP2",
            speed_kmh=180.0,
            wheels=[self._wheel()],
        )
        logic = TyresLogic(self._config(), clock=clock)
        logic.build_view(player)
        clock.advance(3.1)
        player.wheels[0].carcass_temp_c = 72.0
        logic.build_view(player)
        self.assertTrue(logic.temperature_source_stale(0))

        clock.advance(0.1)
        player.wheels[0].inner_left_c = 76.0
        player.wheels[0].inner_center_c = 76.0
        player.wheels[0].inner_right_c = 76.0
        recovered = logic.build_view(player).wheels[0]

        self.assertFalse(logic.temperature_source_stale(0))
        self.assertEqual(logic.main_temperature_c(recovered), 76.0)

    def test_stationary_car_does_not_trigger_false_stale_detection(self) -> None:
        clock = _Clock()
        player = PlayerData(
            vehicle_class="LMP2",
            speed_kmh=0.0,
            wheels=[self._wheel(rotation_rad_s=0.0)],
        )
        logic = TyresLogic(self._config(), clock=clock)
        logic.build_view(player)
        clock.advance(10.0)
        player.wheels[0].carcass_temp_c = 80.0
        stationary = logic.build_view(player).wheels[0]

        self.assertFalse(logic.temperature_source_stale(0))
        self.assertEqual(logic.main_temperature_c(stationary), 75.0)

    def test_gt3_keeps_configured_carcass_rule(self) -> None:
        player = PlayerData(
            vehicle_class="LMGT3",
            speed_kmh=180.0,
            wheels=[self._wheel(carcass_c=69.0)],
        )
        logic = TyresLogic(self._config())

        wheel = logic.build_view(player).wheels[0]

        self.assertEqual(logic.main_temperature_c(wheel), 69.0)

    def test_lmp3_uses_inner_average_instead_of_global_surface(self) -> None:
        player = PlayerData(
            vehicle_class="LMP3",
            vehicle_model="Ginetta G61-LT-P325 Evo",
            speed_kmh=180.0,
            wheels=[self._wheel(inner_c=72.0, carcass_c=75.0, surface_c=57.0)],
        )
        logic = TyresLogic(self._config("surface_average"))

        wheel = logic.build_view(player).wheels[0]

        self.assertEqual(logic.main_temperature_c(wheel), 72.0)

    def test_lmp3_profile_can_be_disabled(self) -> None:
        config = self._config("surface_average")
        config["lmp3_temperature_mode"] = False
        player = PlayerData(
            vehicle_class="LMP3",
            wheels=[self._wheel(inner_c=72.0, surface_c=57.0)],
        )
        logic = TyresLogic(config)

        wheel = logic.build_view(player).wheels[0]

        self.assertEqual(logic.main_temperature_c(wheel), 57.0)

    def test_lmp3_exact_class_does_not_depend_on_keywords(self) -> None:
        config = self._config("surface_average")
        config["lmp3_detection_keywords"] = ""
        player = PlayerData(
            vehicle_class="LMP3",
            wheels=[self._wheel(inner_c=72.0, surface_c=57.0)],
        )
        logic = TyresLogic(config)

        wheel = logic.build_view(player).wheels[0]

        self.assertEqual(logic.main_temperature_c(wheel), 72.0)

    def test_surface_source_is_not_replaced_by_inner_stale_fallback(self) -> None:
        clock = _Clock()
        player = PlayerData(
            vehicle_class="LMP2",
            speed_kmh=180.0,
            wheels=[self._wheel()],
        )
        logic = TyresLogic(self._config("surface_average"), clock=clock)
        logic.build_view(player)
        clock.advance(3.1)
        player.wheels[0].carcass_temp_c = 72.0
        player.wheels[0].surface_left_c = 79.0
        player.wheels[0].surface_center_c = 80.0
        player.wheels[0].surface_right_c = 81.0
        wheel = logic.build_view(player).wheels[0]

        self.assertTrue(logic.temperature_source_stale(0))
        self.assertEqual(logic.main_temperature_c(wheel), 80.0)


if __name__ == "__main__":
    unittest.main()
