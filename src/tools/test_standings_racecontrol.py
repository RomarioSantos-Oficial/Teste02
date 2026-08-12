from __future__ import annotations

import json
import threading
import tempfile
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.widget.standings.lmu_online_client import LMUOnlineIdentityClient
from src.widget.standings.standings_assets import badge_asset_key
from src.widget.standings.standings_online import LocalStandingsEnrichment


class FakeRaceControlClient(LMUOnlineIdentityClient):
    EVENT_ID = "11111111-2222-3333-4444-555555555555"

    def __init__(self) -> None:
        super().__init__(
            Path.cwd(),
            {
                "online_enrichment": True,
                "use_cloud_profiles": True,
            },
        )
        self.requests: list[tuple[str, str, Any]] = []

    def _find_event_id_in_logs(self) -> str:
        return self.EVENT_ID

    def _request_json(
        self,
        url: str,
        *,
        method: str = "GET",
        body: Any | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 2.5,
    ) -> Any:
        del headers, timeout
        self.requests.append((url, method, body))
        if url.endswith("/rest/watch/standings"):
            return [
                {
                    "driverName": "Alice Driver",
                    "carClass": "LMGT3",
                    "carNumber": "27",
                }
            ]
        if url.endswith("/rest/multiplayer/teams"):
            return {
                "drivers": {
                    "Alice Driver": {
                        "nationality": "BR",
                        "badge": "Good Driver",
                    }
                }
            }
        if url.endswith("/rest/profile/getAuthSessionTicket"):
            return {"authSessionTicket": "temporary-ticket"}
        if url.endswith("/authenticate"):
            return {
                "accessToken": "temporary-session-token",
                "player": {
                    "name": "Alice Driver",
                    "username": "Alice Driver",
                    "profile": {"nationality": "BR"},
                    "driverRank": {
                        "rank": "Gold",
                        "tier": 2,
                        "progress": 0.64,
                    },
                    "safetyRank": {"rank": "Silver", "tier": 3},
                },
            }
        if url.endswith("/api/v1/players"):
            return [
                {
                    "name": "Alice Driver",
                    "username": "Alice Driver",
                    "steamId": "steam-test-001",
                    "nationality": "BR",
                    "badge": "Good Driver",
                    "driverRank": {
                        "rank": "Gold",
                        "tier": 2,
                        "progress": 0.64,
                    },
                    "safetyRank": {"rank": "Silver", "tier": 3},
                }
            ]
        if "/api/v1/event/my-split/" in url:
            return {"splitNo": 6, "totalSplits": 8}
        return {}


class RaceControlClientTests(unittest.TestCase):
    def test_event_id_is_never_reused_from_an_older_lmu_trace(self) -> None:
        client = LMUOnlineIdentityClient(Path.cwd(), {})
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            old = directory / "trace_old.txt"
            current = directory / "trace_current.txt"
            old.write_text(
                'Joining race server for online event '
                'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
                encoding="utf-8",
            )
            current.write_text("current offline practice", encoding="utf-8")
            os.utime(old, (1, 1))
            os.utime(current, (2, 2))
            client._log_directories = lambda: [directory]
            self.assertEqual(client._find_event_id_in_logs(), "")
            current.write_text(
                'Joining race server for online event '
                '11111111-2222-3333-4444-555555555555',
                encoding="utf-8",
            )
            self.assertEqual(
                client._find_event_id_in_logs(),
                "11111111-2222-3333-4444-555555555555",
            )

    def test_split_session_signature_changes_only_between_sessions(self) -> None:
        practice = SimpleNamespace(
            connected=True, track_name="Track", session=1,
            drivers=[SimpleNamespace(driver_name="A")],
        )
        practice_roster_changed = SimpleNamespace(
            connected=True, track_name="Track", session=1,
            drivers=[SimpleNamespace(driver_name="A"), SimpleNamespace(driver_name="B")],
        )
        qualify = SimpleNamespace(
            connected=True, track_name="Track", session=5,
            drivers=[SimpleNamespace(driver_name="A")],
        )
        self.assertEqual(
            LMUOnlineIdentityClient._make_split_session_signature(practice),
            LMUOnlineIdentityClient._make_split_session_signature(
                practice_roster_changed
            ),
        )
        self.assertNotEqual(
            LMUOnlineIdentityClient._make_split_session_signature(practice),
            LMUOnlineIdentityClient._make_split_session_signature(qualify),
        )

    def test_reset_clears_event_and_split_session_cache(self) -> None:
        client = FakeRaceControlClient()
        client._observed_event_id = client.EVENT_ID
        client._split_session_signature = "Track|5"
        client._split_by_event_id[client.EVENT_ID] = "S 6/9"
        client.reset()
        self.assertEqual(client._observed_event_id, "")
        self.assertEqual(client._split_session_signature, "")
        self.assertEqual(client._split_by_event_id, {})

    def test_collection_restart_hides_and_rechecks_split(self) -> None:
        client = FakeRaceControlClient()
        session = SimpleNamespace(
            connected=True, track_name="Track", session=5,
            drivers=[SimpleNamespace(driver_name="Alice Driver")],
        )
        first = client.refresh_sync(session)
        self.assertEqual(first.split_label, "S 6/8")
        client.hide_split()
        self.assertEqual(client.snapshot().split_label, "")
        client.request_split_recheck(session)
        second = client.refresh_sync(session)
        self.assertEqual(second.split_label, "S 6/8")
        split_requests = [
            request for request in client.requests
            if "/api/v1/event/my-split/" in request[0]
        ]
        self.assertEqual(len(split_requests), 2)

    def test_event_probe_does_not_cancel_slow_raceos_refresh(self) -> None:
        client = FakeRaceControlClient()
        started = threading.Event()
        release = threading.Event()

        def slow_worker(session, generation):
            del session, generation
            started.set()
            release.wait(1.0)

        client._refresh_worker = slow_worker
        session = SimpleNamespace(
            track_name="Track", session=5, max_laps=0, drivers=[]
        )
        client.trigger_refresh(session)
        self.assertTrue(started.wait(1.0))
        generation = client._generation
        client._last_event_probe = 0.0
        client.trigger_refresh(session)
        self.assertEqual(client._generation, generation)
        self.assertEqual(client._observed_event_id, client.EVENT_ID)
        release.set()
        client._thread.join(1.0)

    def test_formats_raceos_division_as_split_label(self) -> None:
        self.assertEqual(
            LMUOnlineIdentityClient._split_label_from_payload(
                {"splitNo": 6, "totalSplits": 8}
            ),
            "S 6/8",
        )
        self.assertEqual(
            LMUOnlineIdentityClient._split_label_from_payload({"splitNo": 6}),
            "",
        )
        self.assertEqual(
            LMUOnlineIdentityClient._split_label_from_payload(
                {"division": 5, "maxSplit": 50}
            ),
            "S 5/50",
        )
        self.assertEqual(
            LMUOnlineIdentityClient._split_label_from_payload(
                {"splitNo": "6", "numOfSplits": "9"}
            ),
            "S 6/9",
        )

    def test_split_is_requested_only_once_after_valid_response(self) -> None:
        client = FakeRaceControlClient()
        session = SimpleNamespace(drivers=[])
        first = client.refresh_sync(session)
        second = client.refresh_sync(session)
        split_requests = [
            request for request in client.requests
            if "/api/v1/event/my-split/" in request[0]
        ]
        self.assertEqual(first.split_label, "S 6/8")
        self.assertEqual(second.split_label, "S 6/8")
        self.assertEqual(len(split_requests), 1)

    def test_split_is_checked_once_at_start_of_each_session(self) -> None:
        client = FakeRaceControlClient()
        driver = SimpleNamespace(driver_name="Alice Driver", steam_id="")
        practice = SimpleNamespace(
            connected=True, track_name="Track", session=1,
            max_laps=0, drivers=[driver],
        )
        qualify = SimpleNamespace(
            connected=True, track_name="Track", session=5,
            max_laps=0, drivers=[driver],
        )
        client.trigger_refresh(practice)
        client._thread.join(2.0)
        client.trigger_refresh(practice)
        if client._thread is not None:
            client._thread.join(2.0)
        client.trigger_refresh(qualify)
        client._thread.join(2.0)
        split_requests = [
            request for request in client.requests
            if "/api/v1/event/my-split/" in request[0]
        ]
        self.assertEqual(len(split_requests), 2)
        self.assertEqual(client.snapshot().split_label, "S 6/8")

    def test_official_badge_codes_map_to_local_images(self) -> None:
        expected = {
            "sr-noob": "rookie",
            "sr-rookie": "rookie",
            "sr-probation": "probation",
            "sr-warning": "warning",
            "sr-danger": "warning",
            "sr-clean": "gooddriver",
            "sr-saint": "trusteddrive",
            "s397": "staff",
            "content-creator": "creator",
            "irl-driver": "realdriver",
        }
        self.assertEqual(
            {value: badge_asset_key(value) for value in expected},
            expected,
        )

    def test_local_teams_dictionary_keeps_driver_name(self) -> None:
        parser = object.__new__(LocalStandingsEnrichment)
        metadata = {}
        parser._parse_payload(
            {
                "drivers": {
                    "Alice Driver": {
                        "nationality": "BR",
                        "badge": "Good Driver",
                    }
                }
            },
            metadata,
            "/rest/multiplayer/teams",
        )
        self.assertEqual(metadata["alicedriver"].country_code, "BR")
        self.assertEqual(metadata["alicedriver"].nationality, "BR")
        self.assertEqual(metadata["alicedriver"].badge, "Good Driver")

    def test_local_profile_endpoint_captures_player_country(self) -> None:
        parser = object.__new__(LocalStandingsEnrichment)
        metadata = {}
        parser._parse_payload(
            {
                "name": "Local Driver",
                "nick": "Local Driver",
                "nationality": "BR",
                "steamID": "steam-test-002",
            },
            metadata,
            "/rest/profile/profileInfo/getProfileInfo",
        )
        self.assertEqual(metadata["localdriver"].country_code, "BR")
        self.assertEqual(
            metadata["localdriver"].steam_id,
            "steam-test-002",
        )

    def test_local_team_list_captures_embedded_badge_dr_and_sr(self) -> None:
        parser = object.__new__(LocalStandingsEnrichment)
        metadata = {}
        parser._parse_payload(
            {
                "teams": [
                    {
                        "drivers": [
                            {
                                "displayName": "Alice Driver #1234",
                                "metadata": json.dumps(
                                    {
                                        "profile": {
                                            "nationality": "BR",
                                            "contactBadge": "Good Driver",
                                        },
                                        "driverRank": {
                                            "rank": "Gold",
                                            "tier": 2,
                                            "percentage": 0.64,
                                        },
                                        "safetyRank": {
                                            "rank": "Silver",
                                            "tier": 3,
                                        },
                                    }
                                ),
                            }
                        ]
                    }
                ]
            },
            metadata,
            "/rest/multiplayer/teams",
        )
        driver = metadata["alicedriver1234"]
        self.assertEqual(driver.country_code, "BR")
        self.assertEqual(driver.badge, "Good Driver")
        self.assertEqual(driver.driver_rank, "Gold 2")
        self.assertEqual(driver.driver_rank_progress, 64.0)
        self.assertEqual(driver.safety_rank, "Silver 3")

    def test_local_roles_supply_badge_when_lmu_reports_none(self) -> None:
        parser = object.__new__(LocalStandingsEnrichment)
        metadata = {}
        parser._parse_payload(
            {
                "drivers": {
                    "Race Admin": {
                        "nationality": "GB",
                        "badge": "none",
                        "roles": ["Admin"],
                    }
                }
            },
            metadata,
            "/rest/multiplayer/teams",
        )
        self.assertEqual(metadata["raceadmin"].badge, "Admin")

    def test_snapshot_matches_lmu_hash_suffix(self) -> None:
        parser = object.__new__(LocalStandingsEnrichment)
        parser._lock = threading.RLock()
        parser._metadata = {}
        parser._source_text = "LMU REST"
        parser._last_error = ""
        parser._parse_payload(
            {
                "drivers": {
                    "Alice Driver #1234": {
                        "driverRank": {"rank": "Gold", "tier": 2}
                    }
                }
            },
            parser._metadata,
            "/rest/multiplayer/teams",
        )
        snapshot, _, _ = parser.snapshot(["Alice Driver"])
        self.assertEqual(snapshot["alicedriver"].driver_rank, "Gold 2")

    def test_collects_country_badge_dr_and_sr(self) -> None:
        client = FakeRaceControlClient()
        session = SimpleNamespace(
            track_name="Le Mans",
            session=13,
            max_laps=20,
            drivers=[
                SimpleNamespace(
                    driver_name="Alice Driver",
                    steam_id="steam-test-001",
                )
            ],
        )

        snapshot = client.refresh_sync(session)
        identity = client.lookup(
            "Alice Driver",
            steam_id="steam-test-001",
        )

        self.assertTrue(snapshot.local_api_available)
        self.assertTrue(snapshot.session_online)
        self.assertTrue(snapshot.cloud_available)
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.nationality, "BR")
        self.assertEqual(identity.badge, "Good Driver")
        self.assertEqual(identity.driver_rank, "Gold 2")
        self.assertAlmostEqual(identity.driver_rank_progress or 0.0, 0.64)
        self.assertEqual(identity.safety_rank, "Silver 3")

    def test_raceos_uses_batch_profile_lookup(self) -> None:
        client = FakeRaceControlClient()
        session = SimpleNamespace(
            track_name="Le Mans",
            session=13,
            max_laps=20,
            drivers=[SimpleNamespace(driver_name="Alice Driver", steam_id="")],
        )
        client.refresh_sync(session)
        request = next(
            item for item in client.requests if item[0].endswith("/api/v1/players")
        )
        _, method, body = request
        self.assertEqual(method, "POST")
        self.assertEqual(body, {"usernames": ["Alice Driver"]})

    def test_raceos_does_not_require_external_client_key(self) -> None:
        client = FakeRaceControlClient()
        session = SimpleNamespace(
            track_name="Le Mans",
            session=13,
            max_laps=20,
            drivers=[SimpleNamespace(driver_name="Alice Driver", steam_id="")],
        )
        snapshot = client.refresh_sync(session)
        self.assertTrue(snapshot.cloud_available)
        self.assertTrue(
            any(url.endswith("/authenticate") for url, _, _ in client.requests)
        )

    def test_raceos_uses_team_roster_when_session_is_missing(self) -> None:
        client = FakeRaceControlClient()
        snapshot = client.refresh_sync()
        self.assertTrue(snapshot.cloud_available)
        request = next(
            item for item in client.requests if item[0].endswith("/api/v1/players")
        )
        self.assertEqual(request[2], {"usernames": ["Alice Driver"]})


if __name__ == "__main__":
    unittest.main()
