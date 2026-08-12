from __future__ import annotations

import time
from typing import Any


class SessionActivityTracker:
    """Stabilize LMU's transient player and frozen-frame states.

    LMU can briefly publish a scoring frame without ``mIsPlayer`` while
    changing screens.  TinyPedal tolerates five such frames and considers
    telemetry paused when the session clock has not advanced for two seconds.
    """

    def __init__(self, missing_player_limit: int = 5, freeze_seconds: float = 2.0) -> None:
        self.missing_player_limit = max(1, int(missing_player_limit))
        self.freeze_seconds = max(0.1, float(freeze_seconds))
        self._missing_player_frames = 0
        self._ever_synced = False
        self._last_event_time: float | None = None
        self._last_change_at = time.monotonic()

    def update(self, session: Any, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else float(now)
        connected = bool(getattr(session, "connected", False))
        raw_player_synced = bool(getattr(session, "player_synced", False))

        if connected and raw_player_synced:
            self._ever_synced = True
            self._missing_player_frames = 0
        else:
            self._missing_player_frames += 1
        stable_player = raw_player_synced or (
            self._ever_synced and self._missing_player_frames < self.missing_player_limit
        )

        event_time = float(getattr(session, "current_time_s", 0.0) or 0.0)
        if not connected:
            self._last_event_time = None
            self._last_change_at = now
        elif self._last_event_time is None or abs(event_time - self._last_event_time) > 1e-4:
            self._last_event_time = event_time
            self._last_change_at = now

        telemetry_paused = connected and now - self._last_change_at > self.freeze_seconds
        session.player_synced = stable_player
        session.telemetry_paused = telemetry_paused
        return stable_player and not telemetry_paused

    def reset(self) -> None:
        self._missing_player_frames = 0
        self._ever_synced = False
        self._last_event_time = None
        self._last_change_at = time.monotonic()
