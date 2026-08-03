from __future__ import annotations

import math
import time
from dataclasses import dataclass


@dataclass(slots=True)
class SmoothValue:
    value: float = 0.0
    target: float = 0.0
    response: float = 12.0

    def set_target(self, target: float) -> None:
        self.target = float(target)

    def reset(self, value: float = 0.0) -> None:
        self.value = float(value)
        self.target = float(value)

    def step(self, dt: float) -> float:
        dt = max(0.0, min(0.25, float(dt)))
        if dt <= 0:
            return self.value

        alpha = 1.0 - math.exp(-self.response * dt)
        self.value += (self.target - self.value) * alpha
        return self.value


class TimedFade:
    """Controla anúncio temporário com fade de entrada e saída."""

    def __init__(self) -> None:
        self._started_at = 0.0
        self._visible_seconds = 5.0
        self._fade_seconds = 0.25
        self._always_visible = False
        self._active = False

    def start(
        self,
        visible_seconds: float,
        fade_seconds: float,
        always_visible: bool,
    ) -> None:
        self._started_at = time.monotonic()
        self._visible_seconds = max(0.1, float(visible_seconds))
        self._fade_seconds = max(0.01, float(fade_seconds))
        self._always_visible = bool(always_visible)
        self._active = True

    def stop(self) -> None:
        self._active = False

    def reset(self) -> None:
        self._active = False
        self._started_at = 0.0

    @property
    def active(self) -> bool:
        return self._active

    def alpha(self) -> float:
        if not self._active:
            return 0.0

        if self._always_visible:
            return 1.0

        elapsed = time.monotonic() - self._started_at
        fade = self._fade_seconds
        hold_end = self._visible_seconds
        end = hold_end + fade

        if elapsed < fade:
            return max(0.0, min(1.0, elapsed / fade))

        if elapsed <= hold_end:
            return 1.0

        if elapsed < end:
            return max(0.0, min(1.0, 1.0 - (elapsed - hold_end) / fade))

        self._active = False
        return 0.0
