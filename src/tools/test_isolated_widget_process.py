from __future__ import annotations

import pickle
import time
import unittest

from src.telemetry.models import DriverData, SessionData
from src.ui.isolated_widget_process import SessionBusPublisher, SharedSessionBus
from src.widget.standings.standings_assets import (
    hydrate_session_driver_countries,
    publish_driver_country,
)


class _StaticSessionSource:
    def __init__(self, session: SessionData) -> None:
        self.session = session

    def snapshot(self) -> tuple[int, SessionData]:
        return 1, self.session


class IsolatedWidgetCountryTests(unittest.TestCase):
    def test_hydration_fills_missing_country_without_overwriting_session(self) -> None:
        missing = DriverData(driver_name="Country Bus Missing Test")
        existing = DriverData(
            driver_name="Country Bus Existing Test",
            nationality="Germany",
            country_code="DE",
        )
        session = SessionData(drivers=[missing, existing])
        publish_driver_country(missing.driver_name, "Brazil", "BR")
        publish_driver_country(existing.driver_name, "France", "FR")

        updated = hydrate_session_driver_countries(session)

        self.assertEqual(updated, 1)
        self.assertEqual(
            (missing.nationality, missing.country_code),
            ("Brazil", "BR"),
        )
        self.assertEqual(
            (existing.nationality, existing.country_code),
            ("Germany", "DE"),
        )

    def test_publisher_serializes_country_for_isolated_delta(self) -> None:
        driver = DriverData(driver_name="Country Bus Delta Test")
        session = SessionData(connected=True, drivers=[driver])
        publish_driver_country(driver.driver_name, "Brazil", "BR")
        bus = SharedSessionBus()
        publisher = SessionBusPublisher(_StaticSessionSource(session), bus)

        publisher.start()
        deadline = time.monotonic() + 1.0
        while int(bus.sequence.value) < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        publisher.close()

        self.assertEqual(int(bus.sequence.value), 1)
        with bus.lock:
            length = int(bus.length.value)
            payload = bytes(memoryview(bus.buffer).cast("B")[:length])
        received = pickle.loads(payload)
        received_driver = received.drivers[0]
        self.assertEqual(
            (received_driver.nationality, received_driver.country_code),
            ("Brazil", "BR"),
        )


if __name__ == "__main__":
    unittest.main()
