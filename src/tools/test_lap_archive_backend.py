from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main as api


def payload(scope: str, seconds: float, name: str, car: str = "Ferrari 296 GT3") -> dict:
    return {
        "scope": scope,
        "track": "Silverstone",
        "category": "LMGT3",
        "car_model": car,
        "car_filename": "ferrari_296_gt3",
        "car_number": "17",
        "lap_seconds": seconds,
        "sector1": 33.0,
        "sector2": 33.0,
        "sector3": seconds - 66.0,
        "display_name": name,
        "trace": [
            {
                "distance": index / 39,
                "elapsed_s": seconds * index / 39,
                "throttle": 0.7,
                "brake": 0.1,
                "speed_kmh": 190.0,
            }
            for index in range(40)
        ],
    }


class LapRankingBackendTests(unittest.TestCase):
    def test_all_shared_ranking_reads_require_discord_account(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "server.sqlite3"
            with (
                patch.object(api, "DATABASE_PATH", database),
                patch.object(api, "APP_BASE_URL", "https://sectorflow.example"),
                patch.object(api, "DISCORD_CLIENT_ID", "client-id"),
                patch.object(api, "DISCORD_CLIENT_SECRET", "client-secret"),
                patch.object(api, "APP_SECRET", b"s" * 32),
            ):
                api._initialise()
                record = api.upload_best(
                    payload("category", 100.0, "Driver A"), user_id="discord-user-a"
                )
                token = api._token("discord-user-b")
                headers = {"Authorization": f"Bearer {token}"}
                with TestClient(api.app) as client:
                    anonymous = [
                        client.get("/v1/rankings?track=Silverstone&category=LMGT3&scope=category"),
                        client.get("/v1/rankings/all"),
                        client.get(f"/v1/rankings/{record['record_id']}/telemetry"),
                    ]
                    self.assertTrue(all(response.status_code == 401 for response in anonymous))
                    self.assertEqual(
                        client.get("/v1/rankings/all", headers=headers).status_code, 200
                    )
                    category = client.get(
                        "/v1/rankings?track=Silverstone&category=LMGT3&scope=category",
                        headers=headers,
                    )
                    self.assertEqual(category.status_code, 200)
                    self.assertEqual(category.json()["items"][0]["display_name"], "Driver A")
                    telemetry = client.get(
                        f"/v1/rankings/{record['record_id']}/telemetry", headers=headers
                    )
                    self.assertEqual(telemetry.status_code, 200)
                    self.assertEqual(len(telemetry.json()["trace"]), 40)
                    forged_owner = payload("category", 99.0, "Driver B")
                    forged_owner["user_id"] = "discord-user-a"
                    upload = client.post("/v1/laps/best", json=forged_owner, headers=headers)
                    self.assertEqual(upload.status_code, 200)
                    client.put(
                        "/v1/me/profile", json={"driver_name": "Updated B"}, headers=headers
                    )
                    rows = client.get("/v1/rankings/all", headers=headers).json()["items"]
                    names = {row["display_name"] for row in rows}
                    self.assertEqual(names, {"Driver A", "Updated B"})
                    self.assertEqual(client.delete("/v1/me", headers=headers).status_code, 200)
                    remaining = client.get("/v1/rankings/all", headers=headers).json()["items"]
                    self.assertEqual([row["display_name"] for row in remaining], ["Driver A"])

    def test_database_health_account_separation_names_rankings_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "server.sqlite3"
            with patch.object(api, "DATABASE_PATH", database):
                api._initialise()
                self.assertEqual(api.health()["database"], "ok")

                account_a_category = api.upload_best(
                    payload("category", 100.0, "Old Game Name"), user_id="discord-user-a"
                )
                api.upload_best(
                    payload("model", 99.0, "Old Game Name"), user_id="discord-user-a"
                )
                api.upload_best(
                    payload("category", 102.0, "Different Driver"), user_id="discord-user-b"
                )
                api.upload_best(
                    payload("model", 103.0, "Different Driver"), user_id="discord-user-b"
                )

                slower = api.upload_best(
                    payload("category", 101.0, "Stale Name"), user_id="discord-user-a"
                )
                self.assertEqual(slower["status"], "unchanged")

                api.update_profile({"driver_name": "Updated LMU Name"}, user_id="discord-user-a")
                category_rows = api.rankings(
                    track="Silverstone", category="LMGT3", scope="category", car_model="",
                    car_filename="", limit=100,
                )["items"]
                self.assertEqual([row["display_name"] for row in category_rows], ["Updated LMU Name", "Different Driver"])

                all_rows = api.all_rankings(track="", category="", scope="", limit=1000, offset=0)["items"]
                self.assertEqual(len(all_rows), 4)
                self.assertNotIn("user_id", all_rows[0])
                self.assertEqual(sum(row["display_name"] == "Updated LMU Name" for row in all_rows), 2)
                self.assertIsNotNone(api.all_rankings(track="Silverstone", category="LMGT3", scope="model", limit=1, offset=0)["next_offset"])

                trace_id = account_a_category["record_id"]
                trace = api.ranking_telemetry(trace_id)
                self.assertEqual(trace["display_name"], "Updated LMU Name")
                self.assertEqual(len(trace["trace"]), 40)

                api.delete_my_data(user_id="discord-user-a")
                remaining = api.all_rankings(track="", category="", scope="", limit=1000, offset=0)["items"]
                self.assertEqual(len(remaining), 2)
                self.assertTrue(all(row["display_name"] == "Different Driver" for row in remaining))


if __name__ == "__main__":
    unittest.main()
