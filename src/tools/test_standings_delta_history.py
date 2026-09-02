from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.telemetry.models import DriverData, SessionData
from src.widget.standings.delta_history_store import DeltaHistoryStore
from src.widget.standings.standings_logic import StandingsLogic


class StandingsDeltaHistoryTests(unittest.TestCase):
    @staticmethod
    def _config(**updates) -> dict:
        config = {
            "enabled": True,
            "show_delta": True,
            "delta_sample_laps": 5,
            "maximum_categories": 1,
            "player_category_rows": 10,
        }
        config.update(updates)
        return config

    @staticmethod
    def _session() -> tuple[SessionData, DriverData, DriverData]:
        player = DriverData(
            slot_id=1,
            steam_id="player-1",
            driver_name="Player",
            vehicle_class="LMGT3",
            position=1,
            laps=0,
            is_player=True,
        )
        rival = DriverData(
            slot_id=2,
            steam_id="rival-2",
            driver_name="Rival",
            vehicle_class="LMGT3",
            position=2,
            laps=0,
        )
        session = SessionData(
            connected=True,
            track_name="Test Track",
            session=10,
            current_time_s=100.0,
            max_laps=20,
            server_name="Test Server",
            start_event_time_s=10.0,
            drivers=[player, rival],
        )
        return session, player, rival

    @staticmethod
    def _rival_delta(logic: StandingsLogic, session: SessionData) -> str:
        view = logic.build(session, {}, "MEM")
        return next(
            row.rolling_delta_text
            for category in view.categories
            for row in category.rows
            if row.slot_id == 2
        )

    def test_rolling_window_uses_available_laps_then_drops_oldest(self) -> None:
        session, player, rival = self._session()
        logic = StandingsLogic(self._config())
        logic.build(session, {}, "MEM")

        observed = []
        for lap_number, difference in enumerate((1, 2, 3, 4, 5, 6), 1):
            player.laps = rival.laps = lap_number
            player.last_lap_s = 70.0
            rival.last_lap_s = 70.0 + difference
            session.current_time_s += 70.0
            observed.append(self._rival_delta(logic, session))

        self.assertEqual(
            observed,
            ["+1.0", "+1.5", "+2.0", "+2.5", "+3.0", "+4.0"],
        )

    def test_first_observed_completed_lap_is_used_immediately(self) -> None:
        session, player, rival = self._session()
        player.laps = rival.laps = 1
        player.last_lap_s = 70.0
        rival.last_lap_s = 72.0

        logic = StandingsLogic(self._config())

        self.assertEqual(self._rival_delta(logic, session), "+2.0")
        self.assertEqual(
            sorted(
                sample.lap_number
                for history in logic._delta_lap_history.values()
                for sample in history
            ),
            [1, 1],
        )

    def test_empty_saved_first_lap_is_recovered_without_waiting(self) -> None:
        session, player, rival = self._session()
        player.laps = rival.laps = 1
        player.last_lap_s = 70.0
        rival.last_lap_s = 72.0
        logic = StandingsLogic(self._config())
        self._rival_delta(logic, session)
        for history in logic._delta_lap_history.values():
            history.clear()

        self.assertEqual(self._rival_delta(logic, session), "+2.0")

    def test_history_keeps_at_most_ten_numbered_laps(self) -> None:
        session, player, rival = self._session()
        logic = StandingsLogic(self._config(delta_sample_laps=10))
        view = logic.build(session, {}, "MEM")
        player_row = next(
            row for category in view.categories for row in category.rows
            if row.is_player
        )
        for lap_number in range(1, 13):
            player.laps = rival.laps = lap_number
            player.last_lap_s, rival.last_lap_s = 70.0, 71.0
            session.current_time_s += 71.0
            view = logic.build(session, {}, "MEM")
            player_row = next(
                row for category in view.categories for row in category.rows
                if row.is_player
            )
        history = logic._delta_lap_history[player_row.delta_identity]
        self.assertEqual(len(history), 10)
        self.assertEqual(
            [sample.lap_number for sample in history],
            list(range(3, 13)),
        )

    def test_other_category_is_not_collected_or_compared(self) -> None:
        session, player, rival = self._session()
        rival.vehicle_class = "Hypercar"
        logic = StandingsLogic(self._config(maximum_categories=2))
        logic.build(session, {}, "MEM")
        player.laps = rival.laps = 1
        player.last_lap_s, rival.last_lap_s = 70.0, 80.0
        view = logic.build(session, {}, "MEM")
        rival_row = next(
            row for category in view.categories for row in category.rows
            if row.slot_id == rival.slot_id
        )
        self.assertEqual(rival_row.rolling_delta_text, "--")
        self.assertNotIn(rival_row.delta_identity, logic._delta_lap_history)

    def test_history_is_restored_only_for_same_race(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "delta.json"
            session, player, rival = self._session()
            logic = StandingsLogic(
                self._config(),
                delta_history_store=DeltaHistoryStore(path, debounce_s=0.0),
            )
            logic.build(session, {}, "MEM")
            for lap_number, times in enumerate(((70.0, 71.0), (72.0, 74.0)), 1):
                player.laps = rival.laps = lap_number
                player.last_lap_s, rival.last_lap_s = times
                session.current_time_s += max(times)
                logic.build(session, {}, "MEM")
            logic.close()
            self.assertTrue(path.is_file())

            restored = StandingsLogic(
                self._config(),
                delta_history_store=DeltaHistoryStore(path, debounce_s=0.0),
            )
            self.assertEqual(self._rival_delta(restored, session), "+1.5")
            restored.close()

            different_session = StandingsLogic(
                self._config(),
                delta_history_store=DeltaHistoryStore(path, debounce_s=0.0),
            )
            session.track_name = "Another Track"
            self.assertEqual(
                self._rival_delta(different_session, session),
                "+2.0",
            )
            different_session.close()
            replacement = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(replacement["session"]["track"], "Another Track")
            self.assertTrue(all(
                [sample["number"] for sample in entry["laps"]] == [2]
                for entry in replacement["drivers"].values()
            ))

    def test_disabling_delta_clears_memory_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "delta.json"
            session, player, rival = self._session()
            logic = StandingsLogic(
                self._config(),
                delta_history_store=DeltaHistoryStore(path, debounce_s=0.0),
            )
            logic.build(session, {}, "MEM")
            player.laps = rival.laps = 1
            player.last_lap_s, rival.last_lap_s = 70.0, 71.0
            logic.build(session, {}, "MEM")
            logic.close()
            self.assertTrue(path.exists())

            store = DeltaHistoryStore(path, debounce_s=0.0)
            active = StandingsLogic(
                self._config(),
                delta_history_store=store,
            )
            active.build(session, {}, "MEM")
            active.update_config(self._config(show_delta=False))
            self.assertEqual(active._delta_lap_history, {})
            self.assertFalse(path.exists())
            active.close()

    def test_non_race_session_never_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "delta.json"
            session, _, _ = self._session()
            session.session = 2
            logic = StandingsLogic(
                self._config(),
                delta_history_store=DeltaHistoryStore(path, debounce_s=0.0),
            )
            logic.build(session, {}, "MEM")
            logic.close()
            self.assertFalse(path.exists())

    def test_finish_clears_file_but_disconnect_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "delta.json"
            session, _, _ = self._session()
            logic = StandingsLogic(
                self._config(),
                delta_history_store=DeltaHistoryStore(path, debounce_s=0.0),
            )
            logic.build(session, {}, "MEM")
            logic.close()
            self.assertTrue(path.exists())

            store = DeltaHistoryStore(path, debounce_s=0.0)
            resumed = StandingsLogic(
                self._config(),
                delta_history_store=store,
            )
            resumed.observe_session_lifecycle(SessionData(connected=False))
            self.assertTrue(path.exists())
            session.race_finished = True
            resumed.observe_session_lifecycle(session)
            self.assertFalse(path.exists())
            resumed.close()

    def test_single_menu_frame_does_not_clear_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "delta.json"
            path.write_text("{}", encoding="utf-8")
            store = DeltaHistoryStore(path, debounce_s=0.0)
            logic = StandingsLogic(
                self._config(),
                delta_history_store=store,
            )
            menu_frame = SessionData(
                connected=True,
                session=10,
                application_location=0,
            )
            with patch(
                "src.widget.standings.standings_logic.time.monotonic",
                side_effect=(10.0, 11.5, 12.1),
            ):
                logic.observe_session_lifecycle(menu_frame)
                self.assertTrue(path.exists())
                logic.observe_session_lifecycle(menu_frame)
                self.assertTrue(path.exists())
                logic.observe_session_lifecycle(menu_frame)
                self.assertFalse(path.exists())
            logic.close()

    def test_corrupt_json_is_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "delta.json"
            path.write_text("{invalid", encoding="utf-8")
            store = DeltaHistoryStore(path, debounce_s=0.0)
            self.assertIsNone(store.load())
            self.assertFalse(path.exists())
            store.close()

    def test_json_contains_no_driver_names_or_raw_steam_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "delta.json"
            session, _, _ = self._session()
            logic = StandingsLogic(
                self._config(),
                delta_history_store=DeltaHistoryStore(path, debounce_s=0.0),
            )
            logic.build(session, {}, "MEM")
            logic.close()
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            self.assertNotIn("Player", raw)
            self.assertNotIn("Rival", raw)
            self.assertNotIn("player-1", raw)
            self.assertNotIn("rival-2", raw)
            self.assertLessEqual(len(payload["drivers"]), 2)


if __name__ == "__main__":
    unittest.main()
