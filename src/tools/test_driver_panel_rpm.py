from __future__ import annotations

import math
import unittest

from src.widget.driver_panel.driver_panel_renderer import format_rpm_readout


class RPMReadoutTests(unittest.TestCase):
    def test_readout_is_increased_by_exactly_25_percent(self) -> None:
        # The displayed value is now 75% above the previous display
        # (which already represented 125% of the raw telemetry RPM).
        self.assertEqual(format_rpm_readout(8000.0), "17.500 RPM")
        self.assertEqual(format_rpm_readout(8124.0), "17.771 RPM")
        self.assertEqual(format_rpm_readout(3000.0), "6.563 RPM")

    def test_readout_handles_zero_negative_and_non_finite_values(self) -> None:
        self.assertEqual(format_rpm_readout(0.0), "0 RPM")
        self.assertEqual(format_rpm_readout(-500.0), "0 RPM")
        self.assertEqual(format_rpm_readout(math.nan), "0 RPM")
        self.assertEqual(format_rpm_readout(math.inf), "0 RPM")


if __name__ == "__main__":
    unittest.main()
