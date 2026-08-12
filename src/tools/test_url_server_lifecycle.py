from __future__ import annotations

import os
import socket
import unittest
from urllib.request import urlopen

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

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


if __name__ == "__main__":
    unittest.main()
