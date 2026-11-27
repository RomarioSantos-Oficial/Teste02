from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.widget.delta.delta_widget import DeltaWidget
from src.widget.standings.standings_logic import StandingsLogic


class FakeDriver:
    def __init__(
        self,
        *,
        track_limits_points=None,
        track_limits_steps=None,
        penalties=0,
        penalty_type="",
        penalty_time_s=0.0,
        finish_status=0,
        finish_status_name="",
    ):
        self.track_limits_points = track_limits_points
        self.track_limits_steps = track_limits_steps
        self.penalties = penalties
        self.penalty_type = penalty_type
        self.penalty_time_s = penalty_time_s
        self.finish_status = finish_status
        self.finish_status_name = finish_status_name


class FakeSession:
    def __init__(self, **values):
        self.track_limits_current = values.get("track_limits_current", 0.0)
        self.track_limits_limit = values.get("track_limits_limit", 5.0)
        self.track_limits_steps_per_point = values.get("track_limits_steps_per_point", 4)
        self.track_limits_steps_per_penalty = values.get("track_limits_steps_per_penalty", 20)


class DeltaPenaltyAlignmentTests(unittest.TestCase):
    @staticmethod
    def read_track_limits(session, driver):
        fake_self = SimpleNamespace(
            config={},
            _read_number=DeltaWidget._read_number,
        )
        return DeltaWidget._track_limit_data(fake_self, session, driver)

    def test_penalty_count_is_not_used_as_track_limit_points(self):
        session = FakeSession(track_limits_current=0.0, track_limits_limit=5.0)
        driver = FakeDriver(penalties=3)
        self.assertEqual(self.read_track_limits(session, driver), (0.0, 5.0))

    def test_driver_track_limit_points_match_standings_source_priority(self):
        session = FakeSession(track_limits_current=0.0, track_limits_limit=5.0)
        driver = FakeDriver(track_limits_points=1.25)
        self.assertEqual(self.read_track_limits(session, driver), (1.25, 5.0))
        self.assertEqual(
            StandingsLogic._driver_track_limits_text(driver, session, True),
            "1.25/5",
        )

    def test_track_limit_steps_are_converted_using_session_ratio(self):
        session = FakeSession(
            track_limits_current=0.0,
            track_limits_limit=5.0,
            track_limits_steps_per_point=4,
        )
        driver = FakeDriver(track_limits_steps=6)
        self.assertEqual(self.read_track_limits(session, driver), (1.5, 5.0))

    def test_sporting_penalties_use_standings_formatter(self):
        session = FakeSession()
        self.assertEqual(
            StandingsLogic._penalty_text(
                FakeDriver(penalties=1, penalty_type="DRIVE_THROUGH"),
                session,
                True,
            ),
            "DT",
        )
        self.assertEqual(
            StandingsLogic._penalty_text(
                FakeDriver(finish_status=3, finish_status_name="DQ"),
                session,
                True,
            ),
            "DQ",
        )
        self.assertEqual(
            StandingsLogic._penalty_text(FakeDriver(), session, True),
            "--",
        )


if __name__ == "__main__":
    unittest.main()
