from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .driver import DriverDecision
from .state import UnifiedState


class TelemetryRecorder:
    """Append versioned state/decision samples as UTF-8 JSON Lines."""

    def __init__(self, path: str | Path = "data/autonomous/observe.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, state: UnifiedState, decision: DriverDecision) -> None:
        row = {
            "schema_version": 1,
            "recorded_at_unix_s": time.time(),
            "state": state.to_dict(),
            "decision": decision.to_dict(),
        }
        encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(encoded + "\n")
