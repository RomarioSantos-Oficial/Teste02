from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2


def default_delta_history_path() -> Path:
    """Arquivo temporario da corrida atual, fora da pasta instalada."""
    base = Path(
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("APPDATA")
        or Path.home()
    )
    return (
        base
        / "SectorFlow"
        / "session_cache"
        / "standings_delta_history.json"
    )


class DeltaHistoryStore:
    """Persiste um pequeno snapshot JSON sem bloquear o desenho do STR."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        debounce_s: float = 0.5,
    ) -> None:
        self.path = Path(path) if path is not None else default_delta_history_path()
        self.temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        self.debounce_s = max(0.0, float(debounce_s))
        self._condition = threading.Condition()
        self._pending: tuple[int, dict[str, Any]] | None = None
        self._deadline = 0.0
        self._generation = 0
        self._closed = False
        self._thread: threading.Thread | None = None

    def load(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, json.JSONDecodeError):
            self.delete()
            return None
        if not isinstance(payload, dict):
            self.delete()
            return None
        return payload

    def schedule_save(self, payload: dict[str, Any]) -> None:
        with self._condition:
            if self._closed:
                return
            self._generation += 1
            first_pending = self._pending is None
            self._pending = (self._generation, payload)
            if first_pending:
                self._deadline = time.monotonic() + self.debounce_s
            self._ensure_thread_locked()
            self._condition.notify_all()

    def delete(self) -> None:
        with self._condition:
            self._generation += 1
            self._pending = None
            self._deadline = 0.0
            self._condition.notify_all()
        self._remove_path(self.temporary_path)
        self._remove_path(self.path)

    def close(self, *, flush: bool = True) -> None:
        with self._condition:
            if self._closed:
                return
            self._closed = True
            if not flush:
                self._generation += 1
                self._pending = None
            elif self._pending is not None:
                self._deadline = 0.0
            thread = self._thread
            self._condition.notify_all()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def _ensure_thread_locked(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._worker,
            name="SectorFlow-DeltaHistory",
            daemon=True,
        )
        self._thread.start()

    def _worker(self) -> None:
        while True:
            with self._condition:
                while self._pending is None:
                    if self._closed:
                        return
                    self._condition.wait()
                delay = self._deadline - time.monotonic()
                if delay > 0.0 and not self._closed:
                    self._condition.wait(delay)
                    continue
                generation, payload = self._pending
                self._pending = None
                self._deadline = 0.0

            self._write_atomic(generation, payload)

            with self._condition:
                if self._closed and self._pending is None:
                    return

    def _write_atomic(self, generation: int, payload: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            self.temporary_path.write_text(encoded, encoding="utf-8")
            with self._condition:
                is_current = generation == self._generation
                if is_current:
                    self.temporary_path.replace(self.path)
            if not is_current:
                self._remove_path(self.temporary_path)
        except (OSError, TypeError, ValueError):
            self._remove_path(self.temporary_path)

    @staticmethod
    def _remove_path(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
