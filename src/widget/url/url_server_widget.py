from __future__ import annotations

import html
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPoint, QTimer, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class UrlServerWidget(QWidget):
    """Controlador invisivel que publica renderizacoes Qt para Browser Source."""

    def __init__(self, widget_id: str, config: dict[str, Any], parent=None) -> None:
        super().__init__(parent); self.widget_id = widget_id; self.config = config
        self.sources: dict[str, QWidget] = {}; self.frames: dict[str, bytes] = {}
        self.output_active = False
        self._lock = threading.RLock(); self._server: _Server | None = None; self._thread: threading.Thread | None = None
        self.last_error = ""; self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self._timer = QTimer(self); self._timer.timeout.connect(self.capture_frames)
        self.update_config(config)

    def show(self) -> None:  # controlador, nunca desenha uma janela local
        self.start_server()

    def hide(self) -> None:
        if not bool(self.config.get("enabled", False)): self.stop_server()

    def isVisible(self) -> bool:
        return self._server is not None

    def set_edit_mode(self, _enabled: bool) -> None: pass
    def apply_normalized_geometry(self, _screen) -> None: pass

    def update_config(self, config: dict[str, Any]) -> None:
        old = (self.config.get("bind_host"), self.config.get("port")) if self.config else None
        self.config = config
        fps = max(1, min(30, int(config.get("fps", 10))))
        interval = max(33, round(1000 / fps))
        new = (config.get("bind_host"), config.get("port"))
        if self._server is not None and old != new: self.stop_server()
        if bool(config.get("enabled", False)):
            self._timer.start(interval)
            self.start_server()
        else:
            self._timer.stop()
            self.output_active = False
            with self._lock:
                self.frames.clear()
            self.stop_server()

    def set_sources(self, sources: dict[str, QWidget]) -> None:
        self.sources = dict(sources); self.capture_frames()

    def set_output_active(self, active: bool) -> None:
        active = bool(active)
        if active == self.output_active: return
        self.output_active = active
        self.capture_frames()

    def capture_frames(self) -> None:
        if self._server is None: return
        rendered: dict[str, bytes] = {}
        for widget_id, widget in list(self.sources.items()):
            if widget.width() <= 1 or widget.height() <= 1: continue
            image = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QColor(0, 0, 0, 0))
            if self.output_active:
                painter = QPainter(image)
                widget.render(painter, QPoint()); painter.end()
            data = QByteArray(); buffer = QBuffer(data); buffer.open(QIODevice.OpenModeFlag.WriteOnly); image.save(buffer, "PNG")
            rendered[widget_id] = bytes(data)
        with self._lock: self.frames.update(rendered)

    def start_server(self) -> None:
        if self._server is not None or not bool(self.config.get("enabled", False)): return
        host = str(self.config.get("bind_host", "0.0.0.0")); port = int(self.config.get("port", 8765)); owner = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = unquote(urlparse(self.path).path)
                if path == "/" or path == "/index.html": self._send_html(owner._index_html())
                elif path.startswith("/widget/"): self._send_html(owner._widget_html(path.split("/", 2)[2]))
                elif path.startswith("/frame/") and path.endswith(".png"):
                    key = path[len("/frame/"):-4]
                    with owner._lock: payload = owner.frames.get(key)
                    if payload is None: self.send_error(404); return
                    self.send_response(200); self.send_header("Content-Type", "image/png"); self.send_header("Cache-Control", "no-store, no-cache"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
                else: self.send_error(404)
            def _send_html(self, text: str):
                payload=text.encode("utf-8"); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload)
            def log_message(self, *_args): pass
        try:
            self._server = _Server((host, port), Handler); self.last_error = ""
            self._thread = threading.Thread(target=self._server.serve_forever, name="SectorFlow-URL", daemon=True); self._thread.start()
        except OSError as exc:
            self.last_error = str(exc); self._server = None

    def stop_server(self) -> None:
        self._timer.stop()
        server, self._server = self._server, None
        thread, self._thread = self._thread, None
        if server is not None:
            server.shutdown(); server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def closeEvent(self, event) -> None: self.stop_server(); event.accept()

    def _index_html(self) -> str:
        port=int(self.config.get("port",8765)); rows="".join(f'<li><a href="/widget/{html.escape(k)}">{html.escape(k)}</a></li>' for k in self.sources)
        return f'<!doctype html><meta charset="utf-8"><title>Sector Flow URL</title><style>body{{font:16px Arial;background:#090d15;color:#fff}}a{{color:#67e8f9}}</style><h1>Sector Flow Widgets</h1><p>Porta {port}</p><ul>{rows}</ul>'

    def _widget_html(self, widget_id: str) -> str:
        if widget_id not in self.sources: return '<!doctype html><meta charset="utf-8"><body>Widget não publicado</body>'
        safe=html.escape(widget_id, quote=True); fps=max(1,min(30,int(self.config.get("fps",10)))); delay=round(1000/fps)
        return f'''<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;width:100%;height:100%;overflow:hidden;background:transparent}}img{{display:block;width:100%;height:100%;object-fit:contain}}</style></head><body><img id="w"><script>const i=document.getElementById('w');function tick(){{i.src='/frame/{safe}.png?t='+Date.now()}}tick();setInterval(tick,{delay});</script></body></html>'''

    def local_addresses(self) -> list[str]:
        port=int(self.config.get("port",8765)); values={f"http://127.0.0.1:{port}"}
        try:
            for address in socket.gethostbyname_ex(socket.gethostname())[2]:
                if not address.startswith("127."): values.add(f"http://{address}:{port}")
        except OSError: pass
        return sorted(values)
