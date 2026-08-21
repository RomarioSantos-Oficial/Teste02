from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent, QPaintEvent, QPainter
from PySide6.QtWidgets import QWidget

from .delta_animation import SmoothValue, TimedFade
from .delta_logo_manager import DeltaLogoManager
from .delta_models import DeltaViewData, FastestLapData
from .delta_renderer import DeltaRenderer
from .delta_sector_tracker import DeltaSectorTracker
from .delta_session_tracker import DeltaSessionTracker


class DeltaWidget(QWidget):
    geometry_changed = Signal(
        str,
        float,
        float,
        float,
        float,
    )
    selected = Signal(str)

    def __init__(
        self,
        widget_id: str,
        config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.widget_id = widget_id
        self.config = config
        self.project_root = (
            Path(__file__).resolve().parents[3]
        )

        self.logo_manager = DeltaLogoManager(
            self.project_root,
            str(
                config.get(
                    "logo_directory",
                    "images/logos",
                )
            ),
        )
        self.session_tracker = DeltaSessionTracker(
            self.logo_manager
        )
        self.sector_tracker = DeltaSectorTracker(
            tolerance_s=float(
                config.get(
                    "sector_tolerance_seconds",
                    0.001,
                )
            )
        )
        self.renderer = DeltaRenderer(
            self.logo_manager
        )

        self.view_data = DeltaViewData()
        self._target_delta = 0.0
        self._smooth_delta = SmoothValue(
            response=float(
                config.get(
                    "delta_smoothing",
                    12.0,
                )
            )
        )
        self._fastest_fade = TimedFade()
        self._fastest_data: list[FastestLapData] = []
        self._last_fastest_count = 0
        self._sector_visible_until = 0.0
        self._sector_was_visible = False
        self._delta_history: deque[float] = deque(
            maxlen=max(
                20,
                int(
                    config.get(
                        "history_points",
                        240,
                    )
                ),
            )
        )

        self.edit_mode = False
        self._dragging = False
        self._resizing = False
        self._drag_offset = QPoint()
        self._resize_start_global = QPoint()
        self._resize_start_size = None
        self._fitting_content = False
        self._last_tick = time.monotonic()

        # 420 px era exatamente a largura salva em telas 1920 px. Por isso o
        # usuário conseguia aumentar, mas nunca diminuir o Delta.
        self.setMinimumSize(180, 70)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.setWindowTitle(
            "Sector Flow Drive - Delta V2.1"
        )

        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(
            self._animate
        )
        self._animation_timer.start(33)

        self.apply_config()

    def apply_config(self) -> None:
        self.setWindowOpacity(
            float(
                self.config.get(
                    "opacity",
                    0.96,
                )
            )
        )
        self._smooth_delta.response = max(
            1.0,
            float(
                self.config.get(
                    "delta_smoothing",
                    12.0,
                )
            ),
        )

        history_points = max(
            20,
            int(
                self.config.get(
                    "history_points",
                    240,
                )
            ),
        )

        if (
            self._delta_history.maxlen
            != history_points
        ):
            self._delta_history = deque(
                self._delta_history,
                maxlen=history_points,
            )

        self.sector_tracker.tolerance_s = max(
            0.0001,
            float(
                self.config.get(
                    "sector_tolerance_seconds",
                    0.001,
                )
            ),
        )

        self.logo_manager.set_directory(
            str(
                self.config.get(
                    "logo_directory",
                    "images/logos",
                )
            )
        )
        self._fit_content_if_enabled()
        self.update()

    def apply_normalized_geometry(
        self,
        screen_geometry,
    ) -> None:
        position = self.config.get(
            "position",
            {},
        )
        size = self.config.get(
            "size",
            {},
        )
        scale = float(
            self.config.get(
                "scale",
                1.0,
            )
        )

        width = max(
            self.minimumWidth(),
            int(
                screen_geometry.width()
                * float(
                    size.get(
                        "width",
                        0.56,
                    )
                )
                * scale
            ),
        )
        configured_height = max(
            self.minimumHeight(),
            int(
                screen_geometry.height()
                * float(
                    size.get(
                        "height",
                        0.36,
                    )
                )
                * scale
            ),
        )
        height = (
            self.renderer.preferred_height(
                width,
                self.config,
                self._fastest_count(),
                self.view_data.sector_visible,
            )
            if bool(
                self.config.get(
                    "auto_fit_content",
                    True,
                )
            )
            else configured_height
        )

        x = int(
            screen_geometry.left()
            + screen_geometry.width()
            * float(
                position.get(
                    "x",
                    0.22,
                )
            )
        )
        y = int(
            screen_geometry.top()
            + screen_geometry.height()
            * float(
                position.get(
                    "y",
                    0.18,
                )
            )
        )

        self.setGeometry(
            x,
            y,
            width,
            max(
                self.minimumHeight(),
                height,
            ),
        )

    def update_from_session(
        self,
        session: Any,
    ) -> None:
        if session is None:
            return

        # A sessao so existe nesta atualizacao de telemetria. Guardar o valor
        # aqui evita que o timer de animacao tente acessar uma variavel local
        # inexistente entre dois quadros.
        self.view_data.split_label = str(
            getattr(session, "split_label", "") or ""
        ).strip()

        player = getattr(
            session,
            "player",
            None,
        )
        raw_delta = (
            float(
                getattr(
                    player,
                    "delta_best_s",
                    0.0,
                )
                or 0.0
            )
            if player
            else 0.0
        )

        self._target_delta = raw_delta
        self._smooth_delta.set_target(
            raw_delta
        )
        self._delta_history.append(
            raw_delta
        )

        result = self.session_tracker.update(
            session,
            announce_initial_fastest=bool(
                self.config.get(
                    "announce_initial_fastest",
                    False,
                )
            ),
            scope=str(
                self.config.get(
                    "fastest_lap_scope",
                    "player_class",
                )
            ),
        )

        if result.session_changed:
            self._fastest_fade.reset()
            self._fastest_data = []
            self._delta_history.clear()
            self._smooth_delta.reset(
                raw_delta
            )
            self.sector_tracker.reset()

        always_visible = bool(
            self.config.get(
                "fastest_lap_always_visible",
                False,
            )
        )

        if result.new_announcement is not None:
            # Mesmo no escopo "todas as classes", o disparo representa uma
            # nova volta de apenas uma classe. Não repete junto os recordes
            # antigos das demais categorias.
            self._fastest_data = [
                result.new_announcement
            ]
            self._fastest_fade.start(
                visible_seconds=float(
                    self.config.get(
                        "fastest_lap_show_seconds",
                        5.0,
                    )
                ),
                fade_seconds=float(
                    self.config.get(
                        "fastest_lap_fade_seconds",
                        0.30,
                    )
                ),
                always_visible=always_visible,
            )

        elif (
            always_visible
            and result.current_fastest is not None
        ):
            if not self._fastest_data:
                self._fastest_data = [
                    result.current_fastest
                ]

            if not self._fastest_fade.active:
                self._fastest_fade.start(
                    visible_seconds=float(
                        self.config.get(
                            "fastest_lap_show_seconds",
                            5.0,
                        )
                    ),
                    fade_seconds=float(
                        self.config.get(
                            "fastest_lap_fade_seconds",
                            0.30,
                        )
                    ),
                    always_visible=True,
                )

        self.view_data.session_key = (
            result.session_key
        )
        self.view_data.session_time_text = (
            self._format_duration(
                float(
                    getattr(
                        session,
                        "remaining_time_s",
                        0.0,
                    )
                    or 0.0
                )
            )
        )
        self.view_data.session_name = (
            self._session_name(
                int(
                    getattr(
                        session,
                        "session",
                        0,
                    )
                    or 0
                )
            )
        )
        self.view_data.track_state = (
            self._track_state(session)
        )

        outstanding = self._player_penalties(
            session
        )
        current, limit = self._track_limit_data(
            session,
            outstanding,
        )

        self.view_data.penalties = outstanding
        self.view_data.penalties_current = current
        self.view_data.penalties_limit = limit
        sector_values = self.sector_tracker.update(session, result.session_key)
        changed_index = self.sector_tracker.last_changed_index
        if changed_index is not None:
            self.view_data.sectors = [sector_values[changed_index]]
            self._sector_visible_until = time.monotonic() + max(
                0.5, float(self.config.get("sector_show_seconds", 5.0))
            )
            self.view_data.sector_visible = True
            self._fit_content_if_enabled()

        self.update()

    def update_config(
        self,
        config: dict[str, Any],
    ) -> None:
        self.config = config
        self.apply_config()

    def set_edit_mode(
        self,
        enabled: bool,
    ) -> None:
        self.edit_mode = bool(enabled)
        # Mantém o redimensionamento acessível mesmo se novos controles
        # filhos forem adicionados ao Delta no futuro.
        for child in self.findChildren(QWidget):
            child.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                self.edit_mode,
            )
        self.setCursor(
            Qt.CursorShape.SizeAllCursor
            if enabled
            else Qt.CursorShape.ArrowCursor
        )
        self.update()

    def clear_history(self) -> None:
        self._delta_history.clear()
        self.update()

    def reset_session_state(self) -> None:
        self.session_tracker.reset()
        self.sector_tracker.reset()
        self._fastest_fade.reset()
        self._fastest_data = []
        self._delta_history.clear()
        self._smooth_delta.reset(0.0)
        self.view_data = DeltaViewData()
        self._fit_content_if_enabled()
        self.update()

    def paintEvent(
        self,
        event: QPaintEvent,
    ) -> None:
        del event

        painter = QPainter(self)
        self.renderer.draw(
            painter,
            QRectF(self.rect()),
            self.view_data,
            list(self._delta_history),
            self.config,
            self.edit_mode,
        )

        if self.edit_mode:
            self._draw_resize_handle(
                painter
            )

    def mousePressEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if (
            not self.edit_mode
            or event.button()
            != Qt.MouseButton.LeftButton
        ):
            event.ignore()
            return

        self.selected.emit(self.widget_id)

        if self._is_resize_zone(event.position()):
            self._resizing = True
            self._resize_start_global = (
                event.globalPosition().toPoint()
            )
            self._resize_start_size = (
                self.size()
            )
            self.setCursor(
                Qt.CursorShape.SizeFDiagCursor
            )
        else:
            self._dragging = True
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self.frameGeometry().topLeft()
            )
            self.setCursor(
                Qt.CursorShape.ClosedHandCursor
            )

        event.accept()

    def mouseMoveEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if not self.edit_mode:
            event.ignore()
            return

        if (
            self._resizing
            and self._resize_start_size
            is not None
        ):
            delta = (
                event.globalPosition().toPoint()
                - self._resize_start_global
            )
            start_w = self._resize_start_size.width()
            start_h = max(1, self._resize_start_size.height())
            width_from_x = start_w + delta.x()
            width_from_y = start_w + delta.y() * (start_w / start_h)
            width = max(
                self.minimumWidth(),
                round(width_from_x if abs(delta.x()) >= abs(delta.y()) else width_from_y),
            )

            if bool(
                self.config.get(
                    "auto_fit_content",
                    True,
                )
            ):
                height = (
                    self.renderer.preferred_height(
                        width,
                        self.config,
                        self._fastest_count(),
                        self.view_data.sector_visible,
                    )
                )
            else:
                height = max(
                    self.minimumHeight(),
                    self._resize_start_size.height()
                    + delta.y(),
                )

            self.resize(width, height)
            event.accept()
            return

        if self._dragging:
            self.move(
                event.globalPosition().toPoint()
                - self._drag_offset
            )
            event.accept()
            return

        self.setCursor(
            Qt.CursorShape.SizeFDiagCursor
            if self._is_resize_zone(event.position())
            else Qt.CursorShape.SizeAllCursor
        )

    def mouseReleaseEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if (
            event.button()
            != Qt.MouseButton.LeftButton
        ):
            event.ignore()
            return

        changed = (
            self._dragging
            or self._resizing
        )
        self._dragging = False
        self._resizing = False
        self.setCursor(
            Qt.CursorShape.SizeAllCursor
            if self.edit_mode
            else Qt.CursorShape.ArrowCursor
        )

        if changed:
            self._emit_normalized_geometry()
            event.accept()
            return

        event.ignore()

    def _animate(self) -> None:
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now

        self.view_data.delta_s = (
            self._smooth_delta.step(dt)
        )
        alpha = self._fastest_fade.alpha()

        if (
            alpha <= 0
            and not bool(
                self.config.get(
                    "fastest_lap_always_visible",
                    False,
                )
            )
        ):
            self._fastest_data = []

        self.view_data.fastest_lap = (
            self._fastest_data[0]
            if self._fastest_data
            else None
        )
        self.view_data.fastest_laps = list(self._fastest_data)
        self.view_data.fastest_alpha = alpha
        self.view_data.sector_visible = now < self._sector_visible_until
        if not self.view_data.sector_visible:
            self.view_data.sectors = []

        if self.view_data.sector_visible != self._sector_was_visible:
            self._sector_was_visible = self.view_data.sector_visible
            self._fit_content_if_enabled()

        visible_count = self._fastest_count()

        if visible_count != self._last_fastest_count:
            self._last_fastest_count = visible_count
            self._fit_content_if_enabled()

        self.update()

    def _fastest_is_visible(self) -> bool:
        return (
            bool(self._fastest_data)
            and self.view_data.fastest_alpha
            > 0.001
        )

    def _fastest_count(self) -> int:
        return len(self._fastest_data) if self._fastest_is_visible() else 0

    def _fit_content_if_enabled(self) -> None:
        if (
            self._fitting_content
            or not bool(
                self.config.get(
                    "auto_fit_content",
                    True,
                )
            )
        ):
            return

        if self.width() <= 0:
            return

        preferred = (
            self.renderer.preferred_height(
                self.width(),
                self.config,
                self._fastest_count(),
                self.view_data.sector_visible,
            )
        )
        preferred = max(
            self.minimumHeight(),
            preferred,
        )

        if abs(
            self.height() - preferred
        ) <= 2:
            return

        self._fitting_content = True
        self.resize(
            self.width(),
            preferred,
        )
        self._fitting_content = False

    def _draw_resize_handle(
        self,
        painter: QPainter,
    ) -> None:
        rect = self._resize_handle_rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(
            Qt.GlobalColor.white
        )
        painter.drawRect(rect)

    def _resize_handle_rect(
        self,
    ) -> QRectF:
        size = max(
            18,
            int(
                min(
                    self.width(),
                    self.height(),
                )
                * 0.045
            ),
        )

        return QRectF(
            self.width() - size - 3,
            self.height() - size - 3,
            size,
            size,
        )

    def _is_resize_zone(self, position) -> bool:
        """Área maior que o desenho para facilitar pegar a borda do Delta."""
        edge = max(28.0, min(self.width(), self.height()) * 0.10)
        return (
            position.x() >= self.width() - edge
            or position.y() >= self.height() - edge
        )

    def _emit_normalized_geometry(
        self,
    ) -> None:
        screen = self.screen()

        if screen is None:
            return

        rect = screen.geometry()

        self.geometry_changed.emit(
            self.widget_id,
            (
                self.x()
                - rect.left()
            )
            / rect.width(),
            (
                self.y()
                - rect.top()
            )
            / rect.height(),
            self.width()
            / rect.width(),
            self.height()
            / rect.height(),
        )

    def _track_limit_data(
        self,
        session: Any,
        outstanding_penalties: int,
    ) -> tuple[float, float]:
        """
        Prefere os valores reais calculados pelo SessionData atualizado.

        O denominador vem exclusivamente dos dados da sessão do LMU.
        Quando a API não fornece o limite, nenhum valor inventado é usado.
        """
        # Não inventa um limite fixo. O valor deve vir da sessão.
        fallback_limit = 0.0

        current = self._read_number(
            session,
            "track_limits_current",
        )
        limit = self._read_number(
            session,
            "track_limits_limit",
        )

        if current is None:
            player = getattr(
                session,
                "player",
                None,
            )
            steps = self._read_number(
                player,
                "track_limits_steps",
            )
            steps_per_point = self._read_number(
                session,
                "track_limits_steps_per_point",
            )

            if (
                steps is not None
                and steps_per_point is not None
                and steps_per_point > 0
            ):
                current = (
                    steps
                    / steps_per_point
                )

        if limit is None or limit <= 0:
            steps_per_penalty = self._read_number(
                session,
                "track_limits_steps_per_penalty",
            )
            steps_per_point = self._read_number(
                session,
                "track_limits_steps_per_point",
            )

            if (
                steps_per_penalty is not None
                and steps_per_penalty > 0
                and steps_per_point is not None
                and steps_per_point > 0
            ):
                limit = (
                    steps_per_penalty
                    / steps_per_point
                )

        if current is None:
            current = float(
                max(
                    0,
                    outstanding_penalties,
                )
            )

        if limit is None or limit <= 0:
            limit = fallback_limit

        increment = max(
            0.01,
            float(
                self.config.get(
                    "penalty_increment",
                    0.25,
                )
            ),
        )

        # Mantém a leitura visual nos intervalos usados pelo jogo:
        # 0.00, 0.25, 0.50, 0.75, 1.00...
        current = round(current / increment) * increment

        return (
            max(0.0, current),
            max(0.0, limit),
        )

    @staticmethod
    def _read_number(
        source: Any,
        name: str,
    ) -> float | None:
        if source is None:
            return None

        try:
            value = getattr(source, name)
        except AttributeError:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _player_penalties(
        session: Any,
    ) -> int:
        for row in (
            getattr(
                session,
                "drivers",
                [],
            )
            or []
        ):
            if bool(
                getattr(
                    row,
                    "is_player",
                    False,
                )
            ):
                return int(
                    getattr(
                        row,
                        "penalties",
                        0,
                    )
                    or 0
                )

        return 0

    @staticmethod
    def _format_duration(
        seconds: float,
    ) -> str:
        if seconds <= 0:
            return "--:--:--"

        total = int(seconds)
        hours, remainder = divmod(
            total,
            3600,
        )
        minutes, secs = divmod(
            remainder,
            60,
        )

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{secs:02d}"
        )

    @staticmethod
    def _session_name(
        code: int,
    ) -> str:
        names = {
            0: "Test Day",
            1: "Practice 1",
            2: "Practice 2",
            3: "Practice 3",
            4: "Practice 4",
            5: "Qualifying 1",
            6: "Qualifying 2",
            7: "Qualifying 3",
            8: "Qualifying 4",
            9: "Warmup",
            10: "Race",
            11: "Race 2",
            12: "Race 3",
            13: "Race 4",
        }

        return names.get(
            code,
            f"Session {code}",
        )

    @staticmethod
    def _track_state(
        session: Any,
    ) -> str:
        raining = float(
            getattr(
                session,
                "raining",
                0.0,
            )
            or 0.0
        )
        wetness = float(
            getattr(
                session,
                "avg_path_wetness",
                0.0,
            )
            or 0.0
        )
        grip = int(
            getattr(
                session,
                "track_grip_level",
                0,
            )
            or 0
        )

        # O estado da pista deve seguir a quantidade de agua acumulada
        # na trajetoria informada pelo LMU, e nao apenas a intensidade
        # instantanea da chuva.
        if wetness >= 0.28:
            return "Wet"

        if wetness >= 0.02 or raining > 0.05:
            return "Damp"

        labels = {
            0: "Green",
            1: "Low Grip",
            2: "Medium Grip",
            3: "High Grip",
            4: "Saturated",
        }

        return labels.get(
            grip,
            "Dry",
        )
