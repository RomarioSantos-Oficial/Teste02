from __future__ import annotations

import unittest

from src.widget.fuel_time.fuel_time_widget import FuelTimeWidget


class FuelTimeWidgetUnitTests(unittest.TestCase):
    def test_fuel_ratio_uses_two_decimals_rounded_up(self) -> None:
        self.assertEqual(FuelTimeWidget._fuel_ratio(0.201), "0.21")
        self.assertEqual(FuelTimeWidget._fuel_ratio(0.209), "0.21")
        self.assertEqual(FuelTimeWidget._fuel_ratio(2.001), "2.01")

    def test_fuel_ratio_preserves_exact_values_and_missing_state(self) -> None:
        self.assertEqual(FuelTimeWidget._fuel_ratio(0.2), "0.20")
        self.assertEqual(FuelTimeWidget._fuel_ratio(2.01), "2.01")
        self.assertEqual(FuelTimeWidget._fuel_ratio(None), "--")


if __name__ == "__main__":
    unittest.main()
