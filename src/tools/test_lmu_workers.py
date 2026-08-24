from __future__ import annotations

import time
import unittest

from src.telemetry.lmu_workers import FastPlayerFrame, SessionTelemetryWorker
from src.telemetry.models import SessionData


class _FakeAdapter:
    def __init__(self) -> None:
        self.reads = 0
        self.closed = False

    def read(self) -> SessionData:
        self.reads += 1
        return SessionData(connected=True, current_time_s=float(self.reads))

    def close(self) -> None:
        self.closed = True


class TelemetryWorkerTests(unittest.TestCase):
    def test_fast_frame_is_immutable(self) -> None:
        frame = FastPlayerFrame(sequence=1, throttle=0.5)
        with self.assertRaises(Exception):
            frame.throttle = 1.0  # type: ignore[misc]

    def test_session_worker_publishes_latest_without_queue(self) -> None:
        adapter = _FakeAdapter()
        worker = SessionTelemetryWorker(
            interval_s=0.020,
            adapter_factory=lambda: adapter,  # type: ignore[arg-type]
        )
        worker.start()
        deadline = time.monotonic() + 0.5
        sequence = 0
        session = SessionData()
        while sequence < 2 and time.monotonic() < deadline:
            sequence, session = worker.snapshot()
            time.sleep(0.005)
        worker.close()

        self.assertGreaterEqual(sequence, 2)
        self.assertTrue(session.connected)
        self.assertEqual(session.current_time_s, float(sequence))
        self.assertTrue(adapter.closed)


if __name__ == "__main__":
    unittest.main()
