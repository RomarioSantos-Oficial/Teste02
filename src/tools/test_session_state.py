from __future__ import annotations

import unittest

from src.telemetry.models import SessionData
from src.telemetry.session_state import SessionActivityTracker


class SessionActivityTrackerTests(unittest.TestCase):
    def test_requires_a_real_player_before_missing_frame_grace(self) -> None:
        tracker = SessionActivityTracker(missing_player_limit=5)
        session = SessionData(connected=True, current_time_s=1.0)
        self.assertFalse(tracker.update(session, now=0.0))
        self.assertFalse(session.player_synced)

    def test_tolerates_four_missing_frames_after_sync(self) -> None:
        tracker = SessionActivityTracker(missing_player_limit=5)
        session = SessionData(connected=True, current_time_s=1.0, player_synced=True)
        self.assertTrue(tracker.update(session, now=0.0))
        for frame in range(1, 5):
            session.player_synced = False
            session.current_time_s += 0.1
            self.assertTrue(tracker.update(session, now=frame * 0.1))
        session.player_synced = False
        session.current_time_s += 0.1
        self.assertFalse(tracker.update(session, now=0.5))

    def test_pauses_after_unchanged_clock_for_two_seconds(self) -> None:
        tracker = SessionActivityTracker(freeze_seconds=2.0)
        session = SessionData(connected=True, current_time_s=10.0, player_synced=True)
        self.assertTrue(tracker.update(session, now=1.0))
        session.player_synced = True
        self.assertFalse(tracker.update(session, now=3.01))
        self.assertTrue(session.telemetry_paused)

    def test_resumes_when_clock_changes(self) -> None:
        tracker = SessionActivityTracker(freeze_seconds=2.0)
        session = SessionData(connected=True, current_time_s=10.0, player_synced=True)
        tracker.update(session, now=1.0)
        session.player_synced = True
        tracker.update(session, now=3.01)
        session.player_synced = True
        session.current_time_s = 10.1
        self.assertTrue(tracker.update(session, now=3.02))
        self.assertFalse(session.telemetry_paused)


if __name__ == "__main__":
    unittest.main()
