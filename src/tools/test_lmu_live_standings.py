from __future__ import annotations

import json
import unittest

from src.telemetry.lmu_live_standings import LMULiveStandingsClient
from src.telemetry.models import DriverData, SessionData


class LMULiveStandingsClientTests(unittest.TestCase):
    def test_reads_dt_sg_and_time_from_internal_ui_message(self) -> None:
        client = LMULiveStandingsClient(enabled=False)
        message = json.dumps({
            "topic": "LiveStandings",
            "body": [
                {
                    "driverName": "Player",
                    "position": 1,
                    "player": True,
                    "penalties": {"DT": 0, "SG": 1, "TIME": 0},
                    "finishStatus": "FSTAT_NONE",
                },
                {
                    "driverName": "Opponent#1234",
                    "position": 2,
                    "penalties": {"DT": 1, "SG": 0, "TIME": 0},
                },
                {
                    "driverName": "Timed",
                    "position": 3,
                    "penalties": {"DT": 0, "SG": 0, "TIME": 20},
                },
            ],
        })
        self.assertTrue(client._process_message(message))
        session = SessionData(drivers=[
            DriverData(driver_name="Player", position=1, is_player=True),
            DriverData(driver_name="Opponent", position=2),
            DriverData(driver_name="Timed", position=3),
        ])

        client.enrich(session)

        self.assertEqual(session.drivers[0].penalty_type, "Stop/Go")
        self.assertEqual(session.drivers[1].penalty_type, "Drive Thru")
        self.assertEqual(session.drivers[2].penalty_type, "Time")
        self.assertEqual(session.drivers[2].penalty_time_s, 20.0)


if __name__ == "__main__":
    unittest.main()
