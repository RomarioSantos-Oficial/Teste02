from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.telemetry.lmu_penalty_log import LMUPenaltyLogReader
from src.telemetry.models import DriverData, SessionData
from src.widget.standings.standings_logic import StandingsLogic


class LMUPenaltyLogReaderTests(unittest.TestCase):
    def test_reads_exact_result_and_keeps_numeric_trace_untyped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log_dir = Path(temporary)
            results = log_dir / "Results"
            results.mkdir()
            (results / "currentR1.xml").write_text(
                '<Penalty Driver="Other Driver#1234" ID="8" '
                'Penalty="Stop/Go" Time="10" Laps="0" '
                'Reason="Speeding In Pitlane" et="40.0">',
                encoding="utf-8",
            )
            (log_dir / "trace_current.txt").write_text(
                '50.0s score.cpp: Local penalty et=45.0 1 0 0 0 '
                '"Track Limits"\n',
                encoding="utf-8",
            )
            session = SessionData(
                connected=True,
                session=10,
                track_name="Test",
                current_event_time_s=50.0,
                drivers=[
                    DriverData(
                        slot_id=0,
                        driver_name="Player",
                        is_player=True,
                        penalties=1,
                    ),
                    DriverData(
                        slot_id=8,
                        driver_name="Other Driver",
                        penalties=1,
                    ),
                ],
            )

            LMUPenaltyLogReader(log_dir).enrich(session)

            self.assertEqual(session.drivers[0].penalty_type, "")
            self.assertEqual(session.drivers[0].penalty_time_s, 0.0)
            self.assertEqual(session.drivers[1].penalty_type, "Stop/Go")
            self.assertEqual(session.drivers[1].penalty_time_s, 10.0)

    def test_formats_each_exact_penalty_type(self) -> None:
        cases = (
            ("Drive Thru", 10.0, "DT"),
            ("Stop/Go", 10.0, "SG10"),
            ("Time", 20.0, "+20"),
            ("Disqualify", 0.0, "DQ"),
        )
        for penalty_type, seconds, expected in cases:
            with self.subTest(penalty_type=penalty_type):
                session = SessionData(
                    connected=True,
                    session=10,
                    drivers=[
                        DriverData(
                            slot_id=1,
                            driver_name="Driver",
                            vehicle_class="LMGT3",
                            position=1,
                            penalties=1,
                            penalty_type=penalty_type,
                            penalty_time_s=seconds,
                        )
                    ],
                )
                row = StandingsLogic({}).build(
                    session, {}, "MEM"
                ).categories[0].rows[0]
                self.assertEqual(row.penalty_text, expected)

    def test_newer_numeric_trace_invalidates_stale_named_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log_dir = Path(temporary)
            results = log_dir / "Results"
            results.mkdir()
            (results / "currentR1.xml").write_text(
                '<Penalty Driver="Player" Penalty="Drive Thru" '
                'Time="0" et="65.2">',
                encoding="utf-8",
            )
            (log_dir / "trace_current.txt").write_text(
                'score.cpp: Local penalty et=108.6 0 10 0 0 '
                '"Track Limits"\n',
                encoding="utf-8",
            )
            session = SessionData(
                connected=True,
                session=10,
                track_name="Test",
                current_event_time_s=120.0,
                drivers=[
                    DriverData(
                        slot_id=0,
                        driver_name="Player",
                        is_player=True,
                        penalties=1,
                    )
                ],
            )

            LMUPenaltyLogReader(log_dir).enrich(session)

            self.assertEqual(session.drivers[0].penalty_type, "")
            self.assertEqual(session.drivers[0].penalty_time_s, 0.0)


if __name__ == "__main__":
    unittest.main()
