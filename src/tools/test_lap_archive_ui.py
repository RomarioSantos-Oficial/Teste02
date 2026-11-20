from __future__ import annotations

import tempfile
import unittest
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog

from src.laps.archive import LapArchiveStore
from src.ui.lap_archive_page import DiscordLoginGateDialog, LapArchivePage


class LapArchiveUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temporary.name) / "laps.sqlite3"
        self.settings_path = Path(self.temporary.name) / "lap_cloud.json"
        patches = [
            patch("src.ui.lap_archive_page.LapArchiveStore", side_effect=lambda: LapArchiveStore(self.store_path)),
            patch("src.ui.lap_archive_page.cloud_settings_path", return_value=self.settings_path),
            patch("src.ui.lap_archive_page.local_owner_key", return_value="offline"),
            patch("src.ui.lap_archive_page.set_active_owner_key"),
        ]
        self.patchers = patches
        for patcher in self.patchers:
            patcher.start()
        self.page = LapArchivePage()

    def tearDown(self) -> None:
        self.page.close()
        self.page.deleteLater()
        QApplication.processEvents()
        for patcher in self.patchers:
            patcher.stop()
        self.temporary.cleanup()

    def test_lap_page_has_local_filtered_and_all_rankings_tabs(self) -> None:
        self.assertEqual(self.page.tabs.count(), 3)
        self.assertEqual(self.page.all_rank_table.columnCount(), 12)
        self.assertEqual(self.page.rank_table.columnCount(), 9)

    def test_all_rankings_reset_position_for_each_class_scope_and_model(self) -> None:
        self.page.cloud._access_token = "signed-in-token"
        rows = [
            {"record_id":"a1", "scope":"category", "track":"Track A", "category":"GT3", "car_key":"", "display_name":"A", "car_model":"Car A", "car_number":"1", "lap_seconds":90.0},
            {"record_id":"a2", "scope":"category", "track":"Track A", "category":"GT3", "car_key":"", "display_name":"B", "car_model":"Car B", "car_number":"2", "lap_seconds":91.0},
            {"record_id":"b1", "scope":"category", "track":"Track B", "category":"GT3", "car_key":"", "display_name":"C", "car_model":"Car C", "car_number":"3", "lap_seconds":80.0},
            {"record_id":"c1", "scope":"model", "track":"Track B", "category":"GT3", "car_key":"car-c", "display_name":"D", "car_model":"Car C", "car_number":"4", "lap_seconds":81.0},
        ]
        self.page._all_rankings_received(rows, "")
        positions = [self.page.all_rank_table.item(row, 0).text() for row in range(4)]
        self.assertEqual(positions, ["1", "2", "1", "1"])
        self.page.all_rank_table.selectRow(0)
        self.page._all_rank_selection_changed()
        self.assertEqual(self.page._selected_rank_id, "a1")
        self.assertTrue(self.page.all_compare_button.isEnabled())

    def test_online_rankings_require_discord_login(self) -> None:
        self.page.server_edit.setText("https://ranking.example")
        self.page.cloud.configure("https://ranking.example")
        with patch.object(self.page.cloud, "fetch_rankings") as fetch_rankings:
            with patch.object(self.page.cloud, "fetch_all_rankings") as fetch_all:
                self.page.track_combo.setEditText("Silverstone")
                self.page.category_combo.setEditText("LMGT3")
                self.page.refresh_rankings()
                self.page.refresh_all_rankings()
        fetch_rankings.assert_not_called()
        fetch_all.assert_not_called()
        self.assertIn("Discord", self.page.rank_status.text())
        self.assertIn("Discord", self.page.all_rank_status.text())

    def test_first_discord_profile_shares_best_laps_automatically(self) -> None:
        self.page.set_owner_key("discord-account-a")
        self.assertTrue(self.page.share_check.isChecked())
        self.assertTrue(self.page._share_is_enabled())

    def test_sign_in_fetches_rankings_on_startup(self) -> None:
        self.page.server_edit.setText("https://ranking.example")
        self.page.cloud.configure("https://ranking.example")
        self.page.cloud._access_token = "signed-in-token"
        self.page.cloud.account_key = "discord-account-a"
        self.page.track_combo.setEditText("Silverstone")
        self.page.category_combo.setEditText("LMGT3")
        with patch.object(self.page, "refresh_rankings") as refresh_category:
            with patch.object(self.page, "refresh_all_rankings") as refresh_all:
                self.page._login_changed("Discord account")
        refresh_category.assert_called_once()
        refresh_all.assert_called_once()

    def test_online_track_detection_selects_context_and_refreshes_rankings(self) -> None:
        self.page.server_edit.setText("https://ranking.example")
        self.page.cloud.configure("https://ranking.example")
        self.page.cloud._access_token = "signed-in-token"
        driver = type("Driver", (), {
            "is_player": True, "driver_name": "R. Lima", "vehicle_class": "LMGT3",
            "vehicle_model": "Ferrari 296 GT3", "vehicle_filename": "ferrari_296_gt3",
        })()
        session = type("Session", (), {
            "connected": True, "server_name": "Online Ranked Server",
            "track_name": "Silverstone", "drivers": [driver],
        })()
        with patch.object(self.page, "refresh_rankings") as refresh:
            self.page.update_session(session)
        self.assertEqual(self.page.track_combo.currentText(), "Silverstone")
        self.assertEqual(self.page.category_combo.currentText(), "LMGT3")
        refresh.assert_called_once()

    def test_offline_session_does_not_auto_query_shared_rankings(self) -> None:
        driver = type("Driver", (), {
            "is_player": True, "driver_name": "R. Lima", "vehicle_class": "LMGT3",
            "vehicle_model": "Ferrari 296 GT3", "vehicle_filename": "ferrari_296_gt3",
        })()
        session = type("Session", (), {
            "connected": True, "server_name": "Single Player",
            "track_name": "Silverstone", "drivers": [driver],
        })()
        with patch.object(self.page, "refresh_rankings") as refresh:
            self.page.update_session(session)
        refresh.assert_not_called()

    def test_session_completion_refreshes_rankings_after_upload_window(self) -> None:
        self.page.cloud._access_token = "signed-in-token"
        self.page.cloud.configure("https://ranking.example")
        self.page.server_edit.setText("https://ranking.example")
        self.page.track_combo.setEditText("Silverstone")
        self.page.category_combo.setEditText("LMGT3")
        self.page._session_refresh_due = time.time() - 1.0
        self.page._last_sync_check = 0.0
        with patch.object(self.page, "refresh_rankings") as refresh_category:
            with patch.object(self.page, "refresh_all_rankings") as refresh_all:
                self.page.sync_due_records()
        refresh_category.assert_called_once()
        refresh_all.assert_called_once()

    def test_startup_login_gate_can_be_skipped(self) -> None:
        dialog = DiscordLoginGateDialog(self.page)
        QTimer.singleShot(0, dialog.skip_button.click)
        result = dialog.exec()
        self.assertEqual(result, QDialog.DialogCode.Rejected)
        self.assertFalse(self.page.cloud.authenticated)

    def test_login_gate_rejects_invalid_server_url_before_network_access(self) -> None:
        dialog = DiscordLoginGateDialog(self.page)
        dialog.server_edit.setText("not-a-url")
        dialog._begin_login()
        self.assertFalse(self.page.cloud.base_url)
        self.assertTrue(dialog.login_button.isEnabled())

    def test_login_gate_opens_browser_and_exposes_copy_fallback(self) -> None:
        dialog = DiscordLoginGateDialog(self.page)
        dialog.show()
        self.app.processEvents()
        with patch("src.ui.lap_archive_page.QDesktopServices.openUrl", return_value=True) as open_url:
            self.page.cloud.login_url_ready.emit("https://discord.example/authorize")
            open_url.assert_called_once()
            self.assertTrue(dialog.retry_browser_button.isVisible())
            self.assertTrue(dialog.copy_link_button.isVisible())
        with patch("src.ui.lap_archive_page.QDesktopServices.openUrl", return_value=True):
            self.assertTrue(dialog._reopen_browser())
        dialog.copy_link_button.click()
        self.assertEqual(self.app.clipboard().text(), "https://discord.example/authorize")
        dialog.close()

    def test_login_gate_reports_browser_failure_with_manual_fallback(self) -> None:
        dialog = DiscordLoginGateDialog(self.page)
        dialog.show()
        self.app.processEvents()
        with patch("src.ui.lap_archive_page.QDesktopServices.openUrl", return_value=False):
            dialog._authorization_ready("https://discord.example/authorize")
        self.assertTrue(dialog.copy_link_button.isVisible())
        self.assertIn("Copie o link", dialog.status.text())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
