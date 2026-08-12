from __future__ import annotations

import os
import socket
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from src.widget.url.url_server_widget import UrlServerWidget


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class UrlServerLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_disabling_stops_capture_and_closes_listening_port(self) -> None:
        port = free_port()
        enabled = {
            "enabled": True,
            "bind_host": "127.0.0.1",
            "port": port,
            "fps": 10,
            "published_widgets": [],
        }
        widget = UrlServerWidget("url", enabled)
        try:
            self.assertIsNotNone(widget._server)
            with urlopen(f"http://127.0.0.1:{port}/", timeout=1.0) as response:
                self.assertEqual(response.status, 200)

            widget.update_config({**enabled, "enabled": False})
            self.assertIsNone(widget._server)
            self.assertIsNone(widget._thread)
            self.assertFalse(widget._timer.isActive())
            with self.assertRaises(OSError):
                socket.create_connection(("127.0.0.1", port), timeout=0.2)
        finally:
            widget.stop_server()
            widget.deleteLater()

    def test_reenabling_restores_output_and_first_frame(self) -> None:
        port = free_port()
        enabled = {
            "enabled": True,
            "bind_host": "127.0.0.1",
            "port": port,
            "fps": 10,
            "published_widgets": ["delta"],
        }
        widget = UrlServerWidget("url", enabled)
        source = QLabel("DELTA")
        source.resize(272, 90)
        source.setStyleSheet("background:#112233;color:white")
        try:
            widget.set_sources({"delta": source})
            widget.set_output_active(True)
            self.assertTrue(widget.output_active)
            self.assertFalse(widget.frames.get("delta"))
            widget._mark_client_active("delta")
            widget.capture_frames()
            self.assertTrue(widget.frames.get("delta"))

            widget.update_config({**enabled, "enabled": False})
            self.assertFalse(widget.output_active)
            self.assertFalse(widget.frames)

            widget.update_config(enabled)
            self.assertTrue(widget.output_active)
            widget._mark_client_active("delta")
            widget.capture_frames()
            self.assertTrue(widget.frames.get("delta"))
            with urlopen(
                f"http://127.0.0.1:{port}/frame/delta.png",
                timeout=1.0,
            ) as response:
                self.assertEqual(response.status, 200)
                self.assertGreater(len(response.read()), 100)
        finally:
            widget.stop_server()
            source.deleteLater()
            widget.deleteLater()

    def test_unpublished_widget_has_no_page_or_frame(self) -> None:
        port = free_port()
        config = {
            "enabled": True,
            "bind_host": "127.0.0.1",
            "port": port,
            "fps": 10,
            "published_widgets": [],
        }
        widget = UrlServerWidget("url", config)
        try:
            with self.assertRaises(HTTPError) as page_error:
                urlopen(f"http://127.0.0.1:{port}/widget/delta", timeout=1.0)
            self.assertEqual(page_error.exception.code, 404)
            with self.assertRaises(HTTPError) as frame_error:
                urlopen(f"http://127.0.0.1:{port}/frame/delta.png", timeout=1.0)
            self.assertEqual(frame_error.exception.code, 404)
        finally:
            widget.stop_server()
            widget.deleteLater()

    def test_published_widget_without_first_frame_returns_no_content(self) -> None:
        port = free_port()
        config = {
            "enabled": True,
            "bind_host": "127.0.0.1",
            "port": port,
            "fps": 10,
            "published_widgets": ["delta"],
        }
        widget = UrlServerWidget("url", config)
        source = QLabel("DELTA")
        source.resize(272, 90)
        try:
            widget.set_sources({"delta": source})
            with urlopen(
                f"http://127.0.0.1:{port}/frame/delta.png",
                timeout=1.0,
            ) as response:
                self.assertEqual(response.status, 204)
                self.assertEqual(response.read(), b"")
        finally:
            widget.stop_server()
            source.deleteLater()
            widget.deleteLater()


if __name__ == "__main__":
    unittest.main()
