from __future__ import annotations

import unittest

from src.telemetry.lmu_rest_client import LMULocalRestClient


class LMURestSafetyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = LMULocalRestClient(enabled=False)

    def test_suspends_after_one_second_outside_car(self) -> None:
        outside = {
            "playerVehicleLoaded": True,
            "inControlOfVehicle": True,
            "inMonitor": True,
        }
        self.client._update_vehicle_presence(outside, 10.0)
        self.client._update_vehicle_presence(outside, 10.9)
        self.assertTrue(self.client.data_flow_active)
        self.client._update_vehicle_presence(outside, 11.0)
        self.assertFalse(self.client.data_flow_active)

    def test_requires_two_confirmations_to_resume(self) -> None:
        self.client._set_data_flow_active(False, 20.0)
        inside = {
            "playerVehicleLoaded": True,
            "inControlOfVehicle": True,
            "inMonitor": False,
            "isReplayActive": False,
        }
        self.client._update_vehicle_presence(inside, 20.5)
        self.assertFalse(self.client.data_flow_active)
        self.client._update_vehicle_presence(inside, 21.0)
        self.assertTrue(self.client.data_flow_active)

    def test_monitor_wins_over_loaded_and_in_control(self) -> None:
        payload = {
            "playerVehicleLoaded": True,
            "inControlOfVehicle": True,
            "inMonitor": True,
        }
        self.client._update_vehicle_presence(payload, 30.0)
        self.client._update_vehicle_presence(payload, 31.0)
        self.assertFalse(self.client.data_flow_active)


if __name__ == "__main__":
    unittest.main()
