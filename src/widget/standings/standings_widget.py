# SectorFlow is an open-source overlay application for racing simulation.
# Copyright (C) 2022-2026 SectorFlow developers
# Based on the user-provided Standings Hybrid reference.
#
# This file is part of SectorFlow.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.


from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QLineF, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPaintEvent, QPainter, QPen, QResizeEvent, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from .standings_assets import (
    BadgeImageStore,
    BrandLogoStore,
    CountryFlagStore,
    badge_color,
    badge_text,
    brand_short,
    flag_emoji,
    publish_driver_country,
)
from .lmu_online_client import LMUOnlineIdentityClient
from .standings_logic import StandingsLogic, canonical_class, format_driver_name
from .standings_models import (
    CategoryBlock,
    DriverMetadata,
    StandingRow,
    StandingsView,
    normalize_identity,
)
from .standings_online import LocalStandingsEnrichment

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class StandingsWidget(QWidget):
    geometry_changed = Signal(str, float, float, float, float)
    selected = Signal(str)
    DESIGN_WIDTH = 1500.0
    DESIGN_HEIGHT = 820.0

    BASE_COLUMNS = (
        ("position", 46.0),
        ("change", 60.0),
        ("flag", 62.5),
        ("badge", 60.0),
        ("driver", 105.0),
        ("brand", 72.0),
        ("dr", 110.0),
        ("sr", 88.0),
        ("gain_dr", 76.0),
        ("number", 58.0),
        ("laps", 70.0),
        ("pit", 90.0),
        ("best", 140.0),
        ("last", 140.0),
        ("interval", 100.0),
        ("delta", 90.0),
        ("gap", 100.0),
        ("tyre", 76.0),
        ("energy", 105.0),
        ("damage", 80.0),
        ("track_limits", 88.0),
        ("penalty", 90.0),
    )
    # Nome e imagens podem ceder espaco. As demais colunas carregam dados
    # numericos e conservam a largura medida para a fonte uniforme da linha.
    FLEXIBLE_COLUMNS = {"driver", "flag", "tyre", "badge", "brand"}
    FLEXIBLE_MIN_WIDTHS = {
        "driver": 72.0,
        "flag": 24.0,
        "tyre": 24.0,
        "badge": 24.0,
        "brand": 24.0,
    }

    def __init__(
        self,
        widget_id: str,
        config: dict[str, Any],
        parent: QWidget | None = None,
        *,
        shared_enrichment: LocalStandingsEnrichment | None = None,
        shared_online_client: LMUOnlineIdentityClient | None = None,
    ) -> None:
        super().__init__(parent)
        self.widget_id = widget_id
        self.config = config
        self.logic = StandingsLogic(config)
        self._owns_enrichment = shared_enrichment is None
        self._owns_online_client = shared_online_client is None
        self.enrichment = shared_enrichment or LocalStandingsEnrichment(PROJECT_ROOT, config)
        self.online_client = shared_online_client or LMUOnlineIdentityClient(PROJECT_ROOT, config)
        self.logos = BrandLogoStore(PROJECT_ROOT, config)
        self.badge_images = BadgeImageStore(PROJECT_ROOT, config)
        self.flags = CountryFlagStore(PROJECT_ROOT, config, self)
        self.view = StandingsView()
        self.session: Any | None = None
        self.edit_mode = False
        self._column_content_scale = 1.0
        self._layout_width_scale = 1.0
        self._drawing_driver_row = False
        self.preview_mode = False
        self._last_build = 0.0
        self._scale = 1.0
        self._dragging = False
        self._resizing = False
        self._drag_offset = QPoint()
        self._resize_origin = QPoint()
        self._resize_width = 0
        self._resize_height = 0
        self._fitting_height = False
        self._fitting_width = False
        self.setWindowTitle("Sector Flow Drive - Standings")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # O limite antigo de 800x280 impedia o redimensionamento pelo puxador.
        # A altura agora acompanha automaticamente o conteudo desenhado.
        self.setMinimumSize(420, 60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(120)
        self.apply_config()

    def apply_config(self) -> None:
        self.logic.update_config(self.config)
        self.enrichment.update_config(self.config)
        self.online_client.update_config(self.config)
        self.logos.update_config(self.config)
        self.badge_images.update_config(self.config)
        self.flags.update_config(self.config)
        self.setWindowOpacity(max(0.10, min(1.0, float(self.config.get("opacity", 0.98)))))
        self._update_scale()
        self._rebuild(force=True)
        self._fit_width_to_columns()

    def update_config(self, config: dict[str, Any]) -> None:
        if "column_width_reference_total" not in config:
            config["column_width_reference_total"] = self.column_width_total()
        self.config = config
        self.apply_config()

    def apply_normalized_geometry(self, screen_geometry) -> None:
        position = self.config.get("position", {})
        size = self.config.get("size", {})
        external_scale = max(0.35, float(self.config.get("scale", 1.0)))
        base_width = (
            screen_geometry.width()
            * float(size.get("width", 0.74))
            * external_scale
        )
        # Cada largura acrescenta espaco ao painel em vez de comprimir as
        # outras colunas para continuar cabendo na largura anterior.
        configured = self.config.get("column_widths", {})
        enabled = self._enabled_columns()
        gain_factor = (
            145.0 / 110.0
            if bool(self.config.get("show_estimated_driver_rank_gain", False))
            and self._has_estimated_dr()
            else 1.0
        )
        # A referência precisa incluir todas as colunas. Quando ela era
        # calculada apenas com as colunas ativas, ligar SR mantinha a mesma
        # largura externa e comprimía/ocultava o conteúdo.
        configured_total = 0.0
        for key, value in self.BASE_COLUMNS:
            if not enabled.get(key, True):
                continue
            multiplier = gain_factor if key in {"dr", "sr"} else 1.0
            configured_total += self._effective_column_width(
                key,
                float(configured.get(key, value)),
            ) * multiplier
        horizontal_margin = max(
            2.0,
            float(self.config.get("panel_margin", 8.0)) * self._scale,
        )
        content_width = max(1.0, base_width - 2.0 * horizontal_margin)
        reference_total = max(
            1.0,
            float(
                self.config.get(
                    "column_width_reference_total",
                    configured_total,
                )
                or configured_total
            ),
        )
        width = max(
            self.minimumWidth(),
            int(
                content_width * configured_total / reference_total
                + 2.0 * horizontal_margin
            ),
            self._minimum_panel_width(),
        )
        width = min(width, max(self.minimumWidth(), screen_geometry.width()))
        height = max(self.minimumHeight(), int(screen_geometry.height() * float(size.get("height", 0.72)) * external_scale))
        x = int(screen_geometry.left() + screen_geometry.width() * float(position.get("x", 0.01)))
        x = max(
            screen_geometry.left(),
            min(x, screen_geometry.right() - width + 1),
        )
        y = int(screen_geometry.top() + screen_geometry.height() * float(position.get("y", 0.02)))
        self.resize(width, height)
        self.move(x, y)
        self._update_scale()

    def column_width_total(self) -> float:
        configured = self.config.get("column_widths", {})
        enabled = self._enabled_columns()
        gain_factor = (
            145.0 / 110.0
            if bool(self.config.get("show_estimated_driver_rank_gain", False))
            and self._has_estimated_dr()
            else 1.0
        )
        total = 0.0
        for key, default_width in self.BASE_COLUMNS:
            if not enabled.get(key, True):
                continue
            multiplier = gain_factor if key in {"dr", "sr"} else 1.0
            total += self._effective_column_width(
                key,
                float(configured.get(key, default_width)),
            ) * multiplier
        return max(1.0, total)

    def _effective_column_width(self, key: str, configured_width: float) -> float:
        width = max(24.0, float(configured_width))
        if key in {"driver", "flag", "tyre", "badge", "brand"}:
            return width

        samples: dict[str, tuple[str, float]] = {
            "position": ("99", .76),
            "change": ("99 ▲", .62),
            "dr": (
                "DR B3 100% +100%"
                if bool(self.config.get("show_estimated_driver_rank_gain", False))
                else "DR B3 100%",
                .50,
            ),
            # SR usa a mesma base geométrica do DR. Mesmo quando a API não
            # fornece progresso de SR, o terceiro bloco "--" preserva o
            # alinhamento e a largura entre as duas colunas.
            "sr": (
                "SR G3 100% +100%"
                if bool(self.config.get("show_estimated_driver_rank_gain", False))
                else "SR G3 100%",
                .50,
            ),
            "number": ("999", .68),
            "laps": ("999", .70),
            "pit": ("Pit 999s", .54),
            "best": ("9:59.999", .68),
            "last": ("9:59.999", .56),
            # INT e DELTA usam sinal e uma casa decimal. +99.9 representa
            # tres algarismos; valores reais maiores ampliam a coluna abaixo.
            "interval": ("+99.9", .68),
            "delta": ("+99.9", .68),
            "gap": ("+999.999", .68),
            "energy": ("~100.0 L", .68),
            "damage": ("100%", .68),
            "track_limits": ("99x/99x", .58),
            "penalty": ("+999", .62),
        }
        sample = samples.get(key)
        if sample is None:
            return width
        text, multiplier = sample
        live_samples: list[str] = []
        for category in self.view.categories:
            for row in category.rows:
                if key == "number":
                    live_samples.append(str(row.car_number or "--"))
                elif key == "best":
                    live_samples.append(format_lap(row.best_lap_s))
                elif key == "last":
                    live_samples.append(format_lap(row.last_lap_s))
                elif key == "interval":
                    live_samples.append(str(row.interval_text or "--"))
                elif key == "delta":
                    live_samples.append(str(row.rolling_delta_text or "--"))
                elif key == "energy":
                    if row.fuel_liters is not None:
                        prefix = "~" if row.fuel_is_estimated else ""
                        live_samples.append(
                            f"{prefix}{max(0.0, float(row.fuel_liters)):.1f} L"
                        )
                    elif row.energy_percent is not None:
                        live_samples.append(f"{float(row.energy_percent):.1f}%")
                elif key == "damage" and row.damage_percent is not None:
                    live_samples.append(f"{float(row.damage_percent):.0f}%")
        # As linhas dos pilotos usam fonte uniforme. A largura automatica
        # precisa medir o texto com esse tamanho integral, sem os antigos
        # multiplicadores individuais de cada coluna.
        multiplier = 1.0
        row_height = max(14.0, float(self.config.get("row_height", 54.0)))
        row_scale = max(.70, min(1.55, (row_height / 54.0) ** .5))
        pixel_size = min(
            float(self.config.get("font_size", 26)) * multiplier * row_scale,
            row_height * .68,
        )
        font = QFont(str(self.config.get("font_name", "Bahnschrift Condensed")))
        font.setBold(True)
        font.setPixelSize(max(3, round(pixel_size)))
        metrics = QFontMetrics(font)
        measured = max(
            [metrics.horizontalAdvance(text)]
            + [metrics.horizontalAdvance(value) for value in live_samples]
        )
        padding = max(6.0, pixel_size * .55)
        if key == "number":
            # Separa visualmente carros de três dígitos da coluna de voltas,
            # sem transformar a coluna em uma largura fixa.
            padding += max(6.0, pixel_size * .30)
        # Para colunas textuais, o conteúdo é a fonte da geometria.
        return max(24.0, float(measured) + padding)

    def update_from_session(self, session: Any) -> None:
        self.preview_mode = False
        self.session = session
        self.enrichment.use_live_mode()
        self.online_client.trigger_refresh(session)
        self._rebuild()

    def set_preview_data(self, session: Any, metadata: list[DriverMetadata]) -> None:
        self.preview_mode = True
        self.session = session
        self.enrichment.set_test_metadata(metadata)
        self._rebuild(force=True)

    def set_edit_mode(self, enabled: bool) -> None:
        self.edit_mode = bool(enabled)
        self.setCursor(Qt.CursorShape.SizeAllCursor if self.edit_mode else Qt.CursorShape.ArrowCursor)
        self.show()
        self.update()

    def reset_session_state(self) -> None:
        self.session = None
        self.logic.reset()
        if self._owns_online_client:
            self.online_client.reset()
        self.view = StandingsView()
        self.update()

    def closeEvent(self, event) -> None:
        self.timer.stop()
        if self._owns_enrichment:
            self.enrichment.stop()
        self.flags.stop()
        event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_scale()
        self._fit_height_to_content()
        self.update()

    def _tick(self) -> None:
        self._rebuild()

    def _rebuild(self, force: bool = False) -> None:
        now = time.monotonic()
        interval = max(0.05, float(self.config.get("render_interval_seconds", 0.20)))
        if not force and now - self._last_build < interval:
            return
        self._last_build = now
        drivers = list(getattr(self.session, "drivers", []) or [])
        driver_names = [
            str(getattr(driver, "driver_name", "") or "")
            for driver in drivers
        ]
        vehicle_names = [
            str(getattr(driver, "vehicle_name", "") or "")
            for driver in drivers
        ]
        metadata, source, _ = self.enrichment.snapshot(driver_names)
        snapshot = self.online_client.snapshot()
        metadata = self._merge_online_metadata(drivers, metadata)
        if snapshot.cloud_available:
            source = "RACECONTROL"
        self.view = self.logic.build(
            self.session,
            metadata,
            source,
            self.enrichment.vehicle_catalog(vehicle_names),
        )
        self.view.split_label = (
            snapshot.split_label
            or str(getattr(self.session, "split_label", "") or "")
        )
        if self.session is not None and snapshot.split_label:
            # Compartilha a descoberta online com Delta e demais overlays
            # que recebem o mesmo quadro de sessao.
            setattr(self.session, "split_label", snapshot.split_label)
        self._update_scale()
        self._fit_height_to_content()
        self.update()

    def _merge_online_metadata(
        self,
        drivers: list[Any],
        metadata: dict[str, DriverMetadata],
    ) -> dict[str, DriverMetadata]:
        for driver in drivers:
            name = str(getattr(driver, "driver_name", "") or "").strip()
            if not name:
                continue
            identity = self.online_client.lookup(
                name,
                steam_id=str(getattr(driver, "steam_id", "") or ""),
            )
            if identity is None:
                continue
            key = normalize_identity(name)
            current = metadata.get(key, DriverMetadata(driver_name=name))
            current.driver_name = name
            current.username = identity.username or current.username
            current.steam_id = identity.steam_id or current.steam_id
            current.team_name = identity.team_name or current.team_name
            current.car_number = identity.car_number or current.car_number
            nationality = str(identity.nationality or "").strip()
            if nationality:
                current.nationality = nationality
                if len(nationality) in (2, 3):
                    current.country_code = nationality.upper()
            current.badge = identity.badge or current.badge
            current.driver_rank = identity.driver_rank or current.driver_rank
            if identity.driver_rank_progress is not None:
                progress = float(identity.driver_rank_progress)
                current.driver_rank_progress = progress * 100.0 if 0.0 <= progress <= 1.0 else progress
            current.safety_rank = identity.safety_rank or current.safety_rank
            if identity.safety_rank_progress is not None:
                progress = float(identity.safety_rank_progress)
                current.safety_rank_progress = (
                    progress * 100.0 if 0.0 <= progress <= 1.0 else progress
                )
            if identity.estimated_driver_rank_gain is not None:
                current.estimated_driver_rank_gain = float(
                    identity.estimated_driver_rank_gain
                )
            current.source = identity.source or current.source
            metadata[key] = current
        for current in metadata.values():
            publish_driver_country(
                current.driver_name,
                current.nationality,
                current.country_code,
            )
        return metadata

    def _update_scale(self) -> None:
        internal = max(0.40, float(self.config.get("internal_scale", 1.0)))
        minimum = max(0.20, float(self.config.get("responsive_min_scale", 0.22)))
        maximum = max(minimum, float(self.config.get("responsive_max_scale", 2.25)))
        # A largura distribui apenas as colunas. Ela nao deve engrossar linhas,
        # cabecalhos ou fonte verticalmente; isso fica sob controle explicito
        # de row_height, alturas de cabecalho e escala interna.
        self._scale = max(minimum, min(maximum, internal))

    def _desired_content_height(self) -> int:
        margin = max(
            2.0,
            float(self.config.get("panel_margin", 8.0)) * self._scale,
        )
        height = 2.0 * margin + 2.0
        if self._header_items():
            height += self._global_header_height()
            height += max(2.0, 4.0 * self._scale)
        if not self.view.categories:
            return max(self.minimumHeight(), round(max(100.0, height)))
        if bool(self.config.get("show_column_legend", False)):
            height += self._legend_height()
        category_height = self._category_header_height()
        row_height = max(
            14.0,
            float(self.config.get("row_height", 54.0)) * self._scale,
        )
        for category in self.view.categories:
            height += category_height + len(category.rows) * row_height
            height += max(2.0, 7.0 * self._scale)
        return max(self.minimumHeight(), round(height))

    def _fit_height_to_content(self) -> None:
        if self._fitting_height or not bool(
            self.config.get("auto_fit_height", True)
        ):
            return
        desired = self._desired_content_height()
        if abs(self.height() - desired) <= 1:
            return
        self._fitting_height = True
        try:
            self.resize(self.width(), desired)
        finally:
            self._fitting_height = False

    def _fit_width_to_columns(self) -> None:
        """Aplica a menor largura que preserva as colunas numericas."""
        if self._fitting_width:
            return
        desired = self._minimum_panel_width()
        screen = self.screen()
        if screen is not None:
            desired = min(desired, screen.availableGeometry().width())
        desired = max(420, desired)
        # A largura calculada serve como ponto inicial, não como trava. Depois
        # disso o usuário pode redimensionar e todo o conteúdo escala junto.
        self.setMinimumWidth(420)
        if abs(self.width() - desired) <= 1:
            return
        self._fitting_width = True
        try:
            self.resize(desired, self.height())
        finally:
            self._fitting_width = False

    def _header_items(self) -> list[tuple[str, float, str]]:
        if not bool(self.config.get("show_global_header", True)):
            return []
        definitions = (
            ("show_header_session_type", self.view.session_type, 0.085, ""),
            ("show_header_session_time", self.view.session_time, 0.155, "cronometro.png"),
            ("show_header_server_time", self.view.server_time, 0.155, "relogio.png"),
            ("show_header_local_time", self.view.local_time, 0.145, "relogio.png"),
            ("show_header_grip", self.view.grip_text, 0.145, "pista.png"),
            ("show_header_track_limits", self.view.track_limits_text, 0.20, "⚠"),
            ("show_header_split", self._split_text(), 0.13, ""),
            ("show_header_source", self.view.source_text, 0.115, ""),
        )
        return [
            (str(text), fraction, icon)
            for key, text, fraction, icon in definitions
            if bool(self.config.get(key, True)) and str(text).strip()
        ]

    def _split_text(self) -> str:
        value = str(self.view.split_label or "").strip()
        if not value:
            return ""
        return (
            value
            if "split" in value.casefold() or value.casefold().startswith("s ")
            else f"SPLIT {value}"
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        colors = self.config.get("colors", {})
        outer = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        popup_reserve = self._penalty_popup_reserve()
        visual_outer = QRectF(outer)
        visual_outer.setRight(max(outer.left(), outer.right() - popup_reserve))
        if bool(self.config.get("background_enabled", True)):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colors.get("background", "#030711")))
            painter.drawRect(visual_outer)
        margin = max(2.0, float(self.config.get("panel_margin", 8.0)) * self._scale)
        content = visual_outer.adjusted(margin, margin, -margin, -margin)
        y = content.top()
        if self._header_items():
            header_height = self._global_header_height()
            self._draw_global_header(painter, QRectF(content.left(), y, content.width(), header_height))
            y += header_height + max(2.0, 4.0 * self._scale)
        used = self._draw_categories(painter, QRectF(content.left(), y, content.width(), content.bottom() - y))
        if used <= 0 and not self.view.connected:
            painter.setFont(self._font(0.95, True))
            painter.setPen(QColor(colors.get("muted", "#A7AFBA")))
            painter.drawText(
                QRectF(content.left(), y, content.width(), content.bottom() - y),
                Qt.AlignmentFlag.AlignCenter,
                "AGUARDANDO O LMU\nSTANDINGS SEM SIMHUB",
            )
        if self.edit_mode:
            painter.setPen(QPen(QColor(colors.get("edit_border", "#9B5CFF")), max(1.0, 2.0 * self._scale), Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(visual_outer)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawRect(self._resize_handle_rect())

    def _draw_global_header(self, painter: QPainter, rect: QRectF) -> None:
        colors = self.config.get("colors", {})
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors.get("header_background", "#000000")))
        painter.drawRect(rect)
        items = self._header_items()
        # As larguras usam pesos fixos por tipo de informacao. Medir o texto
        # atual fazia os blocos oscilarem quando um relogio ganhava digitos ou
        # os algarismos mudavam de largura. Os pesos sao normalizados para
        # continuar ocupando exatamente toda a faixa disponivel.
        preferred_widths = [max(0.01, float(fraction)) for _text, fraction, _icon in items]
        preferred_total = sum(preferred_widths) or 1.0
        x = rect.left()
        for index, (text, fraction, icon) in enumerate(items):
            width = rect.width() * preferred_widths[index] / preferred_total
            if index == len(items) - 1:
                width = rect.right() - x
            cell = QRectF(x, rect.top(), width, rect.height())
            x += width
            # Cada item ocupa proporcionalmente toda a largura restante, sem
            # linhas verticais. A fonte parte do tamanho configurado e so e
            # reduzida abaixo quando o conteudo realmente nao cabe na celula.
            self._column_content_scale = 1.0
            painter.setFont(self._section_font("global_header_font_size", 20.0, cell, 1.0 if index == 0 else 0.86))
            painter.setPen(QColor(colors.get("text", "#FFFFFF")))
            target = cell.adjusted(4 * self._scale, 0, -3 * self._scale, 0)
            icon_path = PROJECT_ROOT / "images" / "incos01" / icon
            if icon and icon_path.is_file():
                icon_size = min(target.height() * 0.70, target.width() * 0.24)
                pixmap = QPixmap(str(icon_path)).scaled(
                    max(1, int(icon_size)), max(1, int(icon_size)),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                label = text
                text_width = QFontMetrics(painter.font()).horizontalAdvance(label)
                group_width = min(
                    target.width(),
                    pixmap.width() + 4 * self._scale + text_width,
                )
                group_left = target.center().x() - group_width / 2.0
                painter.drawPixmap(
                    int(group_left),
                    int(target.center().y() - pixmap.height() / 2),
                    pixmap,
                )
                target.setLeft(group_left + pixmap.width() + 4 * self._scale)
                target.setRight(min(cell.right() - 3 * self._scale, target.left() + text_width))
            else:
                label = f"{icon}  {text}".strip()
            font = painter.font()
            font.setBold(True)
            while font.pixelSize() > 7 and QFontMetrics(font).horizontalAdvance(label) > max(1.0, target.width()):
                font.setPixelSize(font.pixelSize() - 1)
            painter.setFont(font)
            label = painter.fontMetrics().elidedText(
                label,
                Qt.TextElideMode.ElideRight,
                max(1, int(target.width())),
            )
            painter.save()
            painter.setClipRect(cell)
            alignment = Qt.AlignmentFlag.AlignVCenter | (
                Qt.AlignmentFlag.AlignLeft
                if icon and icon_path.is_file()
                else Qt.AlignmentFlag.AlignHCenter
            )
            painter.drawText(target, alignment, label)
            painter.restore()
        self._column_content_scale = 1.0
        painter.setPen(QPen(QColor(colors.get("header_line", "#175C9C")), max(1.0, 2.0 * self._scale)))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

    def _draw_categories(self, painter: QPainter, rect: QRectF) -> float:
        y = rect.top()
        row_height = max(14.0, float(self.config.get("row_height", 54.0)) * self._scale)
        category_height = self._category_header_height()
        legend_height = self._legend_height()
        for category_index, category in enumerate(self.view.categories):
            if y + category_height > rect.bottom():
                break
            self._draw_category_header(painter, QRectF(rect.left(), y, rect.width(), category_height), category)
            y += category_height
            if bool(self.config.get("show_column_legend", False)) and category_index == 0:
                if y + legend_height > rect.bottom():
                    break
                self._draw_legend(painter, QRectF(rect.left(), y, rect.width(), legend_height))
                y += legend_height
            for row in category.rows:
                if y + row_height > rect.bottom():
                    self._draw_clipped_notice(painter, QRectF(rect.left(), max(rect.top(), rect.bottom() - row_height), rect.width(), row_height))
                    return y - rect.top()
                self._draw_row(painter, QRectF(rect.left(), y, rect.width(), row_height), row, category)
                y += row_height
            y += max(2.0, 7.0 * self._scale)
        return y - rect.top()

    def _draw_category_header(self, painter: QPainter, rect: QRectF, category: CategoryBlock) -> None:
        previous_content_scale = self._column_content_scale
        self._column_content_scale = max(
            0.70,
            min(
                1.60,
                (float(self.config.get("category_header_height", 50.0)) / 50.0)
                ** 0.5,
            ),
        )
        color = QColor(category.color)
        gap = max(3.0, 6.0 * self._scale)
        # Todos os blocos visiveis recebem o mesmo peso. Com Categoria,
        # Pilotos, Voltas e SOF presentes, cada bloco ocupa 25% da linha.
        equal_width_weight = 1.0
        definitions: list[tuple[str, float, str]] = [
            ("class", equal_width_weight, category.class_name)
        ]
        if category.show_count:
            definitions.append(
                ("count", equal_width_weight, f"{category.started}/{category.total}")
            )
        lap_label = f"🏁  {category.current_lap}/{category.total_laps_text}"
        definitions.append(("lap", equal_width_weight, lap_label))
        has_sof = bool(
            category.dr_sof_rank and category.dr_sof_progress is not None
        )
        if has_sof:
            definitions.append(("sof", equal_width_weight, ""))

        available = max(
            1.0,
            rect.width() - gap * max(0, len(definitions) - 1),
        )
        weight_total = sum(weight for _key, weight, _text in definitions) or 1.0
        boxes: list[tuple[QRectF, str]] = []
        sof_box = None
        x = rect.left()
        for index, (key, weight, text) in enumerate(definitions):
            width = available * weight / weight_total
            if index == len(definitions) - 1:
                width = rect.right() - x
            box = QRectF(
                x,
                rect.top(),
                max(1.0, width),
                rect.height() - 3 * self._scale,
            )
            if key == "sof":
                sof_box = box
            else:
                boxes.append((box, text))
            x += width + gap
        base_category_font = self._section_font(
            "category_header_font_size", 18.0, rect
        )
        base_category_font.setBold(True)
        for box, text in boxes:
            painter.setFont(QFont(base_category_font))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRect(box)
            painter.setPen(QColor("#FFFFFF"))
            target = box.adjusted(8 * self._scale, 0, -8 * self._scale, 0)
            if category.show_count and text == f"{category.started}/{category.total}":
                pixmap = QPixmap(str(PROJECT_ROOT / "images" / "incos01" / "piloto.png"))
                if not pixmap.isNull():
                    size = min(target.height() * .68, target.width() * .26)
                    pixmap = pixmap.scaled(max(1, int(size)), max(1, int(size)), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    painter.drawPixmap(int(target.left()), int(target.center().y() - pixmap.height() / 2), pixmap)
                    target.setLeft(target.left() + size + 3 * self._scale)
            font = painter.font()
            font.setBold(True)
            while (
                font.pixelSize() > 7
                and QFontMetrics(font).horizontalAdvance(text)
                > max(1.0, target.width())
            ):
                font.setPixelSize(font.pixelSize() - 1)
            painter.setFont(font)
            painter.drawText(target, Qt.AlignmentFlag.AlignCenter, text)
        if sof_box is not None:
            self._draw_rank(
                painter,
                sof_box,
                category.dr_sof_rank,
                category.dr_sof_progress,
                prefix="SOF DR",
            )
        painter.setPen(QPen(color, max(1.0, 3.0 * self._scale)))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        self._column_content_scale = previous_content_scale

    def _humanize_total_calc(self, calc: str) -> str:
        if not calc:
            return ""
        c = str(calc)
        # formatos esperados:
        # - fixo=NN
        # - bad_fixed:NN
        # - lap_time_too_small:XXs
        # - ref=player/leader lap=XX.Xs rem=600s est=18.3
        # - ref=class_avg lap=XX.Xs rem=600s est=18.3
        try:
            if c.startswith("fixo="):
                return f"fixo {c.split('=',1)[1]}"
            if c.startswith("bad_fixed:"):
                return "fixo inválido"
            if c.startswith("lap_time_too_small"):
                return "volta inválida"
            if c in ("no_ref", "no_time"):
                return "—"
            if c in ("bad_estimate", "large_ratio"):
                return "estimativa inválida"
            # tenta extrair est (est=18.3)
            m = re.search(r"est=([0-9]+\.?[0-9]*)", c)
            if m:
                return f"est. {float(m.group(1)):.1f}"
            # fallback: limpar texto técnico e mostrar curto
            return re.sub(r"\s+", " ", c)
        except Exception:
            return str(calc)

    def _draw_legend(self, painter: QPainter, rect: QRectF) -> None:
        colors = self.config.get("colors", {})
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors.get("legend_background", "#11151D")))
        painter.drawRect(rect)
        labels = {
            "position": "P", "change": "+/-", "flag": "PAÍS", "badge": "BADGE",
            "dr": "DR", "sr": "SR", "gain_dr": "ΔDR",
            "driver": "PILOTO", "brand": "MAR", "number": "#", "laps": "VLT",
            "pit": "PIT", "best": "BEST", "last": "LAST", "interval": "INT", "delta": "DELTA", "gap": "GAP", "track_limits": "LIM", "penalty": "PEN",
            "tyre": "TYR",
            "energy": "VE/FUEL", "damage": "DMG",
        }
        for key, cell in self._column_rects(rect):
            base_width = dict(self.BASE_COLUMNS).get(key, cell.width())
            configured_width = float(self.config.get("column_widths", {}).get(key, base_width))
            effective_width = self._effective_column_width(key, configured_width)
            target_width = max(1.0, effective_width * self._scale)
            configured_scale = (
                configured_width / max(1.0, base_width)
                if key in {"driver", "flag", "tyre", "badge", "brand"}
                else 1.0
            )
            self._column_content_scale = max(
                0.20,
                min(3.0, configured_scale * cell.width() / target_width),
            )
            painter.save()
            painter.setClipRect(cell)
            painter.setFont(self._section_font("column_legend_font_size", 12.0, rect))
            painter.setPen(QColor(colors.get("muted", "#A7AFBA")))
            label = labels.get(key, key.upper())
            label = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, max(1, int(cell.width()-2)))
            painter.drawText(cell, Qt.AlignmentFlag.AlignCenter, label)
            painter.restore()
        self._column_content_scale = 1.0

    def _draw_row(self, painter: QPainter, rect: QRectF, row: StandingRow, category: CategoryBlock) -> None:
        colors = self.config.get("colors", {})
        cells = self._column_rects(rect)
        penalty_cell = next((cell for key, cell in cells if key == "penalty"), None)
        detached_penalty = bool(self.config.get("detach_penalty_column", True))
        penalty_gap = max(
            0.0,
            float(self.config.get("penalty_column_gap", 10.0)) * self._scale,
        ) if detached_penalty else 0.0
        main_right = (
            max(rect.left(), penalty_cell.left() - penalty_gap)
            if penalty_cell is not None and detached_penalty
            else rect.right()
        )
        main_rect = QRectF(
            rect.left(), rect.top(), main_right - rect.left(), rect.height()
        )
        if penalty_cell is not None and detached_penalty:
            # A coluna de avisos fica fora do corpo da classificação. Limpa
            # também o vão de separação, inclusive sobre o fundo geral.
            painter.save()
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear
            )
            painter.fillRect(
                QRectF(
                    main_right,
                    rect.top(),
                    rect.right() - main_right,
                    rect.height(),
                ),
                Qt.GlobalColor.transparent,
            )
            painter.restore()
        background = QColor(colors.get("row_background", "#030711"))
        if row.is_player:
            background = QColor(colors.get("player_background", "#111B2B"))
        elif row.in_pits or row.in_garage:
            background = QColor(colors.get("pit_row_background", "#17191D"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRect(main_rect)
        for key, cell in cells:
            painter.save()
            painter.setClipRect(cell)
            self._drawing_driver_row = True
            try:
                self._draw_cell(painter, key, cell, row, category)
            finally:
                self._drawing_driver_row = False
                painter.restore()
        if (
            detached_penalty
            and bool(self.config.get("show_penalty_column", True))
        ):
            popup_gap = max(
                0.0,
                float(self.config.get("penalty_column_gap", 10.0)) * self._scale,
            )
            popup_width = max(
                18.0,
                self._effective_column_width(
                    "penalty",
                    float(
                        self.config.get("column_widths", {}).get(
                            "penalty", dict(self.BASE_COLUMNS).get("penalty", 90.0)
                        )
                    ),
                ) * self._scale,
            )
            popup = QRectF(
                rect.right() + popup_gap,
                rect.top(),
                popup_width,
                rect.height(),
            )
            painter.save()
            painter.setClipRect(popup)
            self._draw_cell(painter, "penalty", popup, row, category)
            painter.restore()
        self._column_content_scale = 1.0
        row_color = self._row_class_color(row, category)
        painter.setPen(QPen(row_color, max(1.0, 1.2 * self._scale)))
        if penalty_cell is None or not detached_penalty:
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        else:
            painter.drawLine(rect.bottomLeft(), QPointF(main_right, rect.bottom()))

    def _row_class_color(self, row: StandingRow, category: CategoryBlock) -> QColor:
        """Return the car's own class color, including in the mixed-class Relative."""
        if row.class_key:
            _, _, color = canonical_class(row.class_key, self.config)
            return QColor(color)
        return QColor(category.color)

    def _draw_cell(self, painter: QPainter, key: str, rect: QRectF, row: StandingRow, category: CategoryBlock) -> None:
        colors = self.config.get("colors", {})
        row_color = self._row_class_color(row, category)
        if key == "position":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(row_color)
            painter.drawRect(rect.adjusted(0, 2 * self._scale, -2 * self._scale, -2 * self._scale))
            # Mostrar apenas a posição — a bandeira de chegada ficará na coluna 'brand'.
            self._text(painter, rect, f"{row.class_position}", 0.76, True)
        elif key == "change":
            value = row.position_change
            if value > 0:
                text, color = f"{value} ▲", colors.get("position_gain", "#00A020")
            elif value < 0:
                text, color = f"{abs(value)} ▼", colors.get("position_loss", "#E52B35")
            else:
                text, color = "0  -", colors.get("muted", "#A7AFBA")
            self._text(painter, rect, text, 0.62, True, QColor(color))
        elif key == "flag":
            target = rect.adjusted(1, 1, -1, -1)
            max_width = max(1, int(target.width()))
            max_height = max(1, int(target.height()))
            pixmap = self.flags.pixmap(
                row.nationality,
                row.country_code,
                max_width,
                max_height,
            )
            if pixmap is not None:
                fitted = QRectF(
                    target.center().x() - pixmap.width() / 2.0,
                    target.center().y() - pixmap.height() / 2.0,
                    pixmap.width(),
                    pixmap.height(),
                )
                painter.drawPixmap(fitted, pixmap, QRectF(pixmap.rect()))
            else:
                painter.setFont(self._font(0.70, False, emoji=True))
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(
                    rect,
                    Qt.AlignmentFlag.AlignCenter,
                    flag_emoji(row.nationality, row.country_code),
                )
        elif key == "badge":
            pixmap = self.badge_images.pixmap(
                row.badge,
                max(1, int(rect.width() * 0.90)),
                max(1, int(rect.height() * 0.84)),
            )
            if pixmap is not None:
                target = QRectF(
                    rect.center().x() - pixmap.width() / 2.0,
                    rect.center().y() - pixmap.height() / 2.0,
                    pixmap.width(),
                    pixmap.height(),
                )
                painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
            else:
                label = badge_text(row.badge)
                if not label:
                    return
                target = rect.adjusted(5 * self._scale, 10 * self._scale, -5 * self._scale, -10 * self._scale)
                color = QColor(badge_color(row.badge, colors))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRect(target)
                self._text(painter, target, label, 0.42, True)
        elif key == "dr":
            self._draw_rank(
                painter,
                rect,
                row.driver_rank,
                row.driver_rank_progress,
                row.estimated_driver_rank_gain,
            )
        elif key == "sr":
            self._draw_rank(
                painter,
                rect,
                row.safety_rank,
                row.safety_rank_progress,
                prefix="SR",
            )
        elif key == "gain_dr":
            if row.estimated_driver_rank_gain is not None:
                gain = float(row.estimated_driver_rank_gain)
                color = QColor(
                    colors.get(
                        "position_gain" if gain >= 0 else "position_loss",
                        "#008E16" if gain >= 0 else "#E52B35",
                    )
                )
                self._text(
                    painter,
                    rect,
                    f"{gain:+.1f}",
                    0.58,
                    True,
                    color,
                )
        elif key == "driver":
            target = rect.adjusted(8 * self._scale, 0, -6 * self._scale, 0)
            painter.setFont(self._row_font(row.is_player))
            painter.setPen(QColor(colors.get("text", "#FFFFFF")))
            display_name = format_driver_name(
                row.driver_name,
                str(self.config.get("driver_name_format", "full")),
            )
            text = painter.fontMetrics().elidedText(display_name, Qt.TextElideMode.ElideRight, max(1, int(target.width())))
            painter.drawText(target, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        elif key == "brand":
            # Se o piloto terminou (finish_status == 1), usar a bandeira de chegada
            finished = False
            try:
                finished = int(getattr(row, "finish_status", 0) or 0) == 1
            except Exception:
                finished = False
            pixmap = None
            if finished:
                candidate = PROJECT_ROOT / "images" / "Flags" / "bandeira_chegada.png"
                if candidate.is_file():
                    try:
                        pix = QPixmap(str(candidate))
                        if not pix.isNull():
                            pixmap = pix.scaled(
                                max(1, int(rect.width() - 2)),
                                max(1, int(rect.height() - 2)),
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                    except Exception:
                        pixmap = None
            if pixmap is None:
                pixmap = self.logos.pixmap(
                    row.manufacturer,
                    max(1, int(rect.width() - 2)),
                    max(1, int(rect.height() - 2)),
                )
            if pixmap is not None:
                x = rect.center().x() - pixmap.width() / 2
                y = rect.center().y() - pixmap.height() / 2
                painter.drawPixmap(int(x), int(y), pixmap)
            else:
                self._text(painter, rect, brand_short(row.manufacturer), 0.48, True, QColor(colors.get("brand_text", "#D8E1EA")))
        elif key == "number":
            horizontal_inset = max(
                0.75,
                3.0
                * self._scale
                * getattr(self, "_layout_width_scale", 1.0),
            )
            vertical_inset = max(
                0.5,
                2.0
                * self._scale
                * getattr(self, "_layout_width_scale", 1.0),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(row_color)
            painter.drawRect(
                rect.adjusted(
                    horizontal_inset,
                    vertical_inset,
                    -horizontal_inset,
                    -vertical_inset,
                )
            )
            self._row_text_fitted(
                painter,
                rect,
                row.car_number or "--",
                True,
                QColor(colors.get("text", "#FFFFFF")),
            )
        elif key == "laps":
            self._text(painter, rect, f"{row.laps:02d}", 0.70, True)
        elif key == "pit":
            if not row.pit_status_visible:
                return
            cell = rect.adjusted(
                3 * self._scale,
                5 * self._scale,
                -3 * self._scale,
                -5 * self._scale,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#D95B00"))
            painter.drawRect(cell)
            self._text(
                painter,
                cell,
                f"{row.pit_time_s:.0f} s",
                0.54,
                True,
                QColor("#FFFFFF"),
            )
        elif key == "best":
            if row.personal_best_highlight:
                color = QColor(colors.get("personal_best", "#008E16"))
            elif row.is_session_fastest:
                color = QColor(colors.get("best_lap", "#8B4DFF"))
            else:
                color = QColor(colors.get("last_lap", "#FFFFFF"))
            self._row_text_fitted(
                painter, rect, format_lap(row.best_lap_s), True, color
            )
        elif key == "last":
            if (
                row.last_lap_invalidated
                and bool(self.config.get("show_invalid_lap_status", True))
            ):
                color = QColor(
                    colors.get("invalid_lap", "#FF3B45")
                )
                text = format_lap(row.last_lap_s)
                self._row_text_fitted(painter, rect, text, True, color)
                return
            if row.last_lap_s <= 0:
                color = QColor(colors.get("muted", "#A7AFBA"))
            elif (
                row.personal_best_highlight
                and row.best_lap_s > 0
                and row.last_lap_s <= row.best_lap_s + 0.001
            ):
                color = QColor(colors.get("personal_best", "#008E16"))
            else:
                color = QColor(colors.get("last_lap", "#FFFFFF"))
            self._row_text_fitted(
                painter, rect, format_lap(row.last_lap_s), True, color
            )
        elif key == "interval":
            self._text(painter, rect, row.interval_text, 0.68, True)
        elif key == "delta":
            value = row.rolling_delta_s
            if value is None:
                self._text(
                    painter,
                    rect,
                    "--",
                    0.68,
                    True,
                    QColor(colors.get("muted", "#A7AFBA")),
                )
                return
            if value != 0.0:
                background = QColor(
                    colors.get(
                        "delta_gain" if value > 0.0 else "delta_loss",
                        "#008E16" if value > 0.0 else "#E52B35",
                    )
                )
                background.setAlphaF(
                    max(0.0, min(1.0, float(self.config.get("delta_background_opacity", 0.85))))
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(background)
                painter.drawRect(
                    rect.adjusted(
                        3 * self._scale,
                        3 * self._scale,
                        -3 * self._scale,
                        -3 * self._scale,
                    )
                )
            self._text(painter, rect, row.rolling_delta_text, 0.68, True)
        elif key == "gap":
            self._text(painter, rect, row.gap_text, 0.68, True)
        elif key == "penalty":
            # Esta coluna nao herda o fundo da linha: quando nao ha aviso ela
            # fica realmente transparente, inclusive nas linhas vizinhas.
            painter.save()
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear
            )
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.restore()
            finish = row.finish_state.casefold()
            in_garage = bool(row.in_garage)
            is_dnf = finish in {"dnf", "didnotfinish", "2"}
            is_dq = finish in {"dq", "disqualified", "3"}
            is_invalid = (
                bool(row.current_lap_invalidated)
                and bool(self.config.get("show_invalid_lap_status", True))
            )
            has_yellow = row.under_yellow or row.flag in {1, 2}
            has_penalty = row.penalty_text not in {"", "--"}

            # Prioridade solicitada para a coluna automática:
            # GAR > PIT > DNF > DQ > INV > amarela > punição.
            if in_garage:
                text, background, foreground = "GAR", QColor("#666666"), QColor("#FFFFFF")
            elif row.in_pits:
                text = "PIT"
                background = QColor(colors.get("pit", "#F97316"))
                foreground = QColor("#FFFFFF")
            elif is_dnf:
                text, background, foreground = "DNF", QColor(colors.get("invalid_lap", "#FF3B45")), QColor("#FFFFFF")
            elif is_dq:
                text, background, foreground = "DQ", QColor(colors.get("invalid_lap", "#FF3B45")), QColor("#FFFFFF")
            elif is_invalid:
                text, background, foreground = "INV", QColor(colors.get("invalid_lap", "#FF3B45")), QColor("#FFFFFF")
            elif has_yellow:
                text, background, foreground = "YEL", QColor("#FFD83D"), QColor("#101010")
            elif has_penalty:
                text = row.penalty_text
                background = QColor(colors.get("invalid_lap", "#FF3B45"))
                foreground = QColor("#FFFFFF")
            else:
                return
            cell = rect.adjusted(
                3 * self._scale,
                5 * self._scale,
                -3 * self._scale,
                -5 * self._scale,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRect(cell)
            self._text(
                painter,
                cell,
                text,
                0.62,
                True,
                foreground,
            )
        elif key == "track_limits":
            self._text(
                painter,
                rect,
                row.track_limits_text or "--",
                0.58,
                True,
                QColor(colors.get("muted", "#A7AFBA")),
            )
        elif key == "tyre":
            compounds = row.tyre_compounds or (
                (row.tyre_compound,) * 4 if row.tyre_compound else ()
            )
            self._draw_tyre(painter, rect, compounds)
        elif key == "energy":
            if row.fuel_liters is not None:
                prefix = "~" if row.fuel_is_estimated else ""
                value = max(0.0, float(row.fuel_liters))
                color_value = row.fuel_percent
                colors = self.config.get("colors", {})
                if color_value is not None and color_value < 15.0:
                    color = QColor(colors.get("energy_low", "#E5222B"))
                elif color_value is not None and color_value < 35.0:
                    color = QColor(colors.get("energy_mid", "#E49127"))
                else:
                    color = QColor(colors.get("energy_high", "#FFFFFF"))
                self._text(painter, rect, f"{prefix}{value:.1f} L", 0.62, True, color)
            else:
                self._draw_percent(painter, rect, row.energy_percent, "energy")
        elif key == "damage":
            self._draw_percent(painter, rect, row.damage_percent, "damage")

    def _draw_driver_status(self, painter: QPainter, rect: QRectF, row: StandingRow) -> None:
        status = ""
        color = ""
        if row.finish_state.casefold() in {"dnf", "didnotfinish", "2"}:
            status, color = "DNF", "#E5222B"
        elif row.finish_state.casefold() in {"dq", "disqualified", "3"}:
            status, color = "DQ", "#E5222B"
        elif (
            row.current_lap_invalidated
            and bool(self.config.get("show_invalid_lap_status", True))
        ):
            status = "INV"
            color = str(
                self.config.get("colors", {}).get(
                    "invalid_lap",
                    "#FF3B45",
                )
            )
        elif row.in_garage:
            status, color = "GAR", "#666666"
        if not status:
            return
        painter.setFont(self._font(0.48, True))
        width = painter.fontMetrics().horizontalAdvance(status) + 14 * self._scale
        box = QRectF(rect.right() - width, rect.top() + 7 * self._scale, width, rect.height() - 14 * self._scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRect(box)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, status)

    def _draw_percent(self, painter: QPainter, rect: QRectF, value: float | None, kind: str) -> None:
        colors = self.config.get("colors", {})
        if value is None:
            self._text(painter, rect, "--", 0.66, True, QColor(colors.get("muted", "#A7AFBA")))
            return
        value = max(0.0, min(100.0, float(value)))
        if kind == "energy":
            if value < 15.0:
                color = colors.get("energy_low", "#E5222B")
            elif value < 25.0:
                color = colors.get("energy_mid", "#E49127")
            else:
                color = colors.get("energy_high", "#FFFFFF")
        else:
            if value >= 40.0:
                color = colors.get("damage_high", "#E5222B")
            elif value >= 15.0:
                color = colors.get("damage_mid", "#E87531")
            else:
                color = colors.get("damage_low", "#FFFFFF")
        self._text(painter, rect, f"{value:.1f}%" if kind == "energy" else f"{value:.0f}%", 0.68, True, QColor(color))

    def _draw_rank(
        self,
        painter: QPainter,
        rect: QRectF,
        rank: str,
        progress: float | None = None,
        estimated_gain: float | None = None,
        prefix: str = "DR",
    ) -> None:
        label = self._rank_short(rank)
        if not label:
            self._text(
                painter,
                rect,
                "--",
                0.52,
                True,
                QColor(self.config.get("colors", {}).get("muted", "#A7AFBA")),
            )
            return
        colors = self.config.get("colors", {})
        rank_color = QColor(self._rank_color(rank))
        dark = QColor(colors.get("rank_cell_background", "#10141C"))
        muted = QColor(colors.get("muted", "#A7AFBA"))
        if prefix == "SOF DR":
            # No cabeçalho, o SOF deve preencher integralmente a célula.
            cell = QRectF(rect)
        else:
            padding = max(1.0, 2.0 * self._scale)
            cell = rect.adjusted(
                padding,
                1 * self._scale,
                -padding,
                -1 * self._scale,
            )

        progress_text = "--"
        if progress is not None:
            value = float(progress)
            if 0.0 <= value <= 1.0:
                value *= 100.0
            progress_text = f"{max(0.0, min(100.0, value)):.0f}%"

        gain_text = ""
        if (
            estimated_gain is not None
            and bool(
                self.config.get("show_estimated_driver_rank_gain", False)
            )
        ):
            gain_text = f"{float(estimated_gain):+.0f}%"

        # Layout compacto inspirado no TinyPedal: DR | S1 | 43% | -5%.
        # Somente o bloco do nivel recebe a cor do rank; nao ha barra inferior.
        prefix_weight = 0.42 if prefix == "SOF DR" else 0.23
        parts: list[tuple[str, float, QColor, QColor]] = [
            (prefix, prefix_weight, dark, muted),
            (label, 0.25, rank_color, QColor("#101010")),
            (progress_text, 0.29, dark, QColor("#FFFFFF")),
        ]
        if gain_text:
            gain = float(estimated_gain or 0.0)
            gain_color = QColor(
                colors.get(
                    "position_gain" if gain >= 0.0 else "position_loss",
                    "#008E16" if gain >= 0.0 else "#E52B35",
                )
            )
            parts.append((gain_text, 0.26, dark, gain_color))

        rank_font: QFont | None = None
        if prefix == "SOF DR":
            part_widths = [weight for _, weight, _, _ in parts]
        else:
            # Mede cada parte com a fonte uniforme da linha. Se a coluna
            # estiver estreita demais, reduz DR/SR como um conjunto (nunca
            # cada pedaco separadamente) para impedir texto cortado.
            rank_font = self._row_font(True)

            def measured_widths() -> list[float]:
                metrics = QFontMetrics(rank_font)
                padding = max(4.0, 6.0 * self._scale)
                return [
                    max(1.0, metrics.horizontalAdvance(text) + padding)
                    for text, _weight, _background, _foreground in parts
                ]

            part_widths = measured_widths()
            natural_width = sum(part_widths)
            if natural_width > cell.width() and rank_font.pixelSize() > 7:
                fitted_size = max(
                    7,
                    int(rank_font.pixelSize() * cell.width() / natural_width),
                )
                rank_font.setPixelSize(fitted_size)
                part_widths = measured_widths()

        total = sum(part_widths) or 1.0
        x = cell.left()
        for index, (text, _weight, background, foreground) in enumerate(parts):
            width = cell.width() * part_widths[index] / total
            if index == len(parts) - 1:
                width = cell.right() - x
            part_rect = QRectF(x, cell.top(), width, cell.height())
            painter.setPen(QPen(QColor("#313744"), max(0.5, self._scale)))
            painter.setBrush(background)
            painter.drawRect(part_rect)
            if prefix == "SOF DR":
                # O SOF pertence ao cabecalho da categoria. Usa a mesma
                # fonte e o mesmo tamanho-base de Categoria/Pilotos/Voltas,
                # reduzindo somente se uma das partes nao couber.
                font = self._section_font(
                    "category_header_font_size", 18.0, part_rect
                )
                font.setBold(True)
                target = part_rect.adjusted(
                    3 * self._scale, 0, -3 * self._scale, 0
                )
                while (
                    font.pixelSize() > 7
                    and QFontMetrics(font).horizontalAdvance(text)
                    > max(1.0, target.width())
                ):
                    font.setPixelSize(font.pixelSize() - 1)
                painter.setFont(font)
                painter.setPen(foreground)
                painter.drawText(target, Qt.AlignmentFlag.AlignCenter, text)
            else:
                target = part_rect.adjusted(
                    2 * self._scale, 0, -2 * self._scale, 0
                )
                painter.setFont(rank_font or self._row_font(True))
                painter.setPen(foreground)
                painter.drawText(target, Qt.AlignmentFlag.AlignCenter, text)
            x += width

    @staticmethod
    def _rank_short(rank: str) -> str:
        text = str(rank or "").strip()
        if not text:
            return ""
        match = re.search(
            r"(bronze|silver|gold|platinum)\s*([1-3])?",
            text,
            re.IGNORECASE,
        )
        if not match:
            return text[:4].upper()
        return match.group(1)[0].upper() + (match.group(2) or "")

    def _rank_color(self, rank: str) -> str:
        text = str(rank or "").strip().casefold()
        colors = self.config.get("colors", {})
        # SOF já chega no formato compacto (B1/S1/G1/P1), enquanto as
        # células dos pilotos normalmente recebem Bronze/Silver/Gold/etc.
        compact = re.match(r"^(?:dr\s*)?([bsgp])\s*[1-3]?\b", text)
        tier = compact.group(1) if compact else ""
        if "platinum" in text or tier == "p":
            return str(colors.get("rank_platinum", "#76D7EA"))
        if "gold" in text or tier == "g":
            return str(colors.get("rank_gold", "#F2C94C"))
        if "silver" in text or tier == "s":
            return str(colors.get("rank_silver", "#C5CED8"))
        return str(colors.get("rank_bronze", "#C47A44"))

    def _draw_tyre(
        self, painter: QPainter, rect: QRectF, compounds: tuple[str, ...]
    ) -> None:
        compound_colors = {
            "S": "#F2F2F2",
            "M": "#FFD32A",
            "H": "#E53935",
            "W": "#2196F3",
            "I": "#43A047",
        }
        tokens = [tyre_short(value).split("/", 1)[0] for value in compounds[:4]]
        tokens += [""] * (4 - len(tokens))
        available = [token for token in tokens if token]
        if not available:
            return

        # Um único desenho permanece legível mesmo na coluna compacta. A faixa
        # externa é dividida entre os eixos: primeiro arco = dianteiros;
        # segundo arco = traseiros. Se um eixo ainda não tiver dado, usa-se o
        # composto disponível no outro eixo como fallback.
        front_token = next((token for token in tokens[:2] if token), available[0])
        rear_token = next((token for token in tokens[2:4] if token), front_token)
        size = min(rect.height() * 0.72, rect.width() * 0.48)
        size = max(7.0, size)
        tyre = QRectF(
            rect.center().x() - size / 2,
            rect.center().y() - size / 2,
            size,
            size,
        )
        fallback_color = self.config.get("colors", {}).get("tyre", "#C7B87A")
        front_color = QColor(compound_colors.get(front_token, fallback_color))
        rear_color = QColor(compound_colors.get(rear_token, fallback_color))
        painter.setPen(QPen(QColor("#111317"), max(1.0, size * 0.17)))
        painter.setBrush(QColor("#25282D"))
        painter.drawEllipse(tyre.adjusted(size * .08, size * .08, -size * .08, -size * .08))

        # A roda continua completa, mas a faixa do composto aparece em dois
        # arcos opostos: um no lado esquerdo e outro no lado direito. As duas
        # partes ficam de frente uma para a outra, com separação em cima e
        # embaixo, como no desenho de referência.
        compound_ring = tyre.adjusted(
            size * .09,
            size * .09,
            -size * .09,
            -size * .09,
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        arc_pen_width = max(1.5, size * .15)
        rotation_angle = -60
        for color, start_angle in (
            (front_color, 110),
            (rear_color, 290),
        ):
            painter.setPen(
                QPen(
                    color,
                    arc_pen_width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawArc(
                compound_ring,
                (start_angle + rotation_angle) * 16,
                140 * 16,
            )

        hub = tyre.adjusted(size * .33, size * .33, -size * .33, -size * .33)
        painter.setPen(QPen(QColor("#8A9098"), max(1.0, size * .08)))
        painter.setBrush(QColor("#15171A"))
        painter.drawEllipse(hub)

    def _draw_clipped_notice(self, painter: QPainter, rect: QRectF) -> None:
        if not self.edit_mode:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 190))
        painter.drawRect(rect)
        self._text(painter, rect, "AUMENTE A ALTURA PARA MOSTRAR AS OUTRAS LINHAS", 0.48, True, QColor("#FFC42E"))

    def _column_rects(self, rect: QRectF) -> list[tuple[str, QRectF]]:
        columns = self._column_width_specs()
        penalty_gap = (
            max(0.0, float(self.config.get("penalty_column_gap", 10.0)))
            * self._scale
            if (
                bool(self.config.get("detach_penalty_column", True))
                and any(key == "penalty" for key, _width, _minimum in columns)
            )
            else 0.0
        )
        usable_width = max(1.0, rect.width() - penalty_gap)
        preferred = [width * self._scale for _key, width, _minimum in columns]
        minimums = [minimum * self._scale for _key, _width, minimum in columns]
        preferred_total = sum(preferred)
        minimum_total = sum(minimums)

        if usable_width >= preferred_total:
            actual_widths = list(preferred)
            extra = usable_width - preferred_total
            driver_index = next(
                (
                    index
                    for index, (key, _width, _minimum) in enumerate(columns)
                    if key == "driver"
                ),
                len(columns) - 1,
            )
            if actual_widths:
                # A sobra aumenta o nome do piloto, sem criar grandes vazios
                # entre todas as colunas numericas.
                actual_widths[driver_index] += extra
            self._layout_width_scale = self._scale
        elif usable_width >= minimum_total:
            shrink_needed = preferred_total - usable_width
            capacities = [
                max(0.0, width - minimum)
                for width, minimum in zip(preferred, minimums)
            ]
            capacity_total = sum(capacities)
            if capacity_total > 0.0:
                actual_widths = [
                    width - shrink_needed * capacity / capacity_total
                    for width, capacity in zip(preferred, capacities)
                ]
            else:
                actual_widths = list(minimums)
            # Os dados mantiveram sua largura natural e usam a fonte padrao.
            self._layout_width_scale = self._scale
        else:
            # Se o usuario deixar o painel extremamente compacto, todas as
            # colunas e a fonte diminuem juntas, sem recortes independentes.
            factor = usable_width / max(1.0, minimum_total)
            actual_widths = [width * factor for width in minimums]
            self._layout_width_scale = max(
                0.20,
                min(3.0, self._scale * factor),
            )

        x = rect.left()
        result: list[tuple[str, QRectF]] = []
        for index, ((key, _preferred, _minimum), actual) in enumerate(
            zip(columns, actual_widths)
        ):
            if key == "penalty":
                x += penalty_gap
            if index == len(columns) - 1:
                actual = rect.right() - x
            result.append((key, QRectF(x, rect.top(), actual, rect.height())))
            x += actual
        return result

    def _column_width_specs(self) -> list[tuple[str, float, float]]:
        """Retorna (coluna, largura preferida, largura minima)."""
        enabled = self._enabled_columns()
        show_gain_in_dr = bool(
            self.config.get("show_estimated_driver_rank_gain", False)
        ) and self._has_estimated_dr()
        configured_widths = self.config.get("column_widths", {})
        columns: list[tuple[str, float, float]] = []
        for key, default_width in self.BASE_COLUMNS:
            if not enabled.get(key, True):
                continue
            if key == "penalty" and bool(
                self.config.get("detach_penalty_column", True)
            ):
                continue
            preferred = self._effective_column_width(
                key,
                float(configured_widths.get(key, default_width)),
            )
            if key in {"dr", "sr"} and show_gain_in_dr:
                preferred *= 145.0 / 110.0
            preferred = max(24.0, preferred)
            if key in self.FLEXIBLE_COLUMNS:
                minimum = min(
                    preferred,
                    float(self.FLEXIBLE_MIN_WIDTHS.get(key, 24.0)),
                )
            else:
                minimum = preferred
            columns.append((key, preferred, minimum))
        return columns

    def _minimum_panel_width(self) -> int:
        minimum_content = sum(
            minimum for _key, _preferred, minimum in self._column_width_specs()
        ) * self._scale
        margin = max(
            2.0,
            float(self.config.get("panel_margin", 8.0)) * self._scale,
        )
        return max(
            420,
            round(
                minimum_content
                + 2.0 * margin
                + self._penalty_popup_reserve()
                + 2.0
            ),
        )

    def _penalty_popup_reserve(self) -> float:
        if not (
            bool(self.config.get("detach_penalty_column", True))
            and bool(self.config.get("show_penalty_column", True))
        ):
            return 0.0
        configured = float(
            self.config.get("column_widths", {}).get(
                "penalty", dict(self.BASE_COLUMNS).get("penalty", 90.0)
            )
        )
        width = max(
            18.0,
            self._effective_column_width("penalty", configured) * self._scale,
        )
        gap = max(
            0.0,
            float(self.config.get("penalty_column_gap", 10.0)) * self._scale,
        )
        return width + gap

    def _enabled_columns(self) -> dict[str, bool]:
        return {
            "change": bool(self.config.get("show_position_change", True)),
            "flag": bool(self.config.get("show_country_flag", True)),
            "badge": bool(self.config.get("show_badge", True)),
            "dr": bool(self.config.get("show_driver_rank", True)),
            "sr": bool(self.config.get("show_safety_rank", True)),
            # O ganho estimado agora faz parte da propria coluna DR.
            "gain_dr": False,
            "brand": bool(self.config.get("show_brand_logo", True)),
            "number": bool(self.config.get("show_car_number", True)),
            "laps": bool(self.config.get("show_laps", True)),
            "pit": bool(self.config.get("show_pit_status", True)),
            "best": bool(self.config.get("show_best_lap", True)),
            "last": bool(self.config.get("show_last_lap", True)),
            "interval": (
                bool(self.config.get("show_interval", True))
                and not bool(self.config.get("relative_mode", False))
                and self.view.session_type == "Race"
            ),
            "delta": (
                bool(self.config.get("show_delta", False))
                and not bool(self.config.get("relative_mode", False))
                and self.view.session_type == "Race"
            ),
            "gap": bool(self.config.get("show_gap", True)),
            "penalty": bool(self.config.get("show_penalty_column", True)),
            "track_limits": bool(
                self.config.get("show_track_limits_column", True)
            ),
            "tyre": bool(self.config.get("show_tyre", True)),
            "energy": bool(self.config.get("show_energy", True)),
            "damage": bool(self.config.get("show_damage", True)),
        }

    def _has_penalties(self) -> bool:
        return any(
            row.penalties > 0
            for category in self.view.categories
            for row in category.rows
        )

    def _has_estimated_dr(self) -> bool:
        return any(
            row.estimated_driver_rank_gain is not None
            for category in self.view.categories
            for row in category.rows
        )

    def _text(
        self,
        painter: QPainter,
        rect: QRectF,
        text: str,
        multiplier: float,
        bold: bool,
        color: QColor | None = None,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter,
    ) -> None:
        painter.setFont(
            self._row_font(bold)
            if self._drawing_driver_row
            else self._font(multiplier, bold)
        )
        painter.setPen(color or QColor(self.config.get("colors", {}).get("text", "#FFFFFF")))
        painter.drawText(rect, alignment, str(text))

    def _row_text_fitted(
        self,
        painter: QPainter,
        rect: QRectF,
        text: str,
        bold: bool,
        color: QColor,
    ) -> None:
        """Desenha dados com a mesma fonte uniforme de toda a linha."""
        font = self._row_font(bold)
        padding = max(
            0.75,
            3.0
            * getattr(self, "_layout_width_scale", 1.0),
        )
        target = rect.adjusted(padding, 0, -padding, 0)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(target, Qt.AlignmentFlag.AlignCenter, str(text))

    def _row_font(self, bold: bool) -> QFont:
        """Fonte uniforme usada exclusivamente nas linhas dos pilotos."""
        font = QFont(str(self.config.get("font_name", "Bahnschrift Condensed")))
        font.setBold(bold)
        row_scale = max(
            0.70,
            min(
                1.55,
                (float(self.config.get("row_height", 54.0)) / 54.0) ** 0.5,
            ),
        )
        base_row_height = max(
            14.0,
            float(self.config.get("row_height", 54.0)),
        )
        base_size = min(
            float(self.config.get("font_size", 26)) * row_scale,
            base_row_height * 0.68,
        )
        font.setPixelSize(
            max(
                3,
                round(
                    base_size
                    * getattr(self, "_layout_width_scale", 1.0)
                ),
            )
        )
        return font

    def _font(self, multiplier: float, bold: bool, emoji: bool = False) -> QFont:
        family = "Segoe UI Emoji" if emoji else str(self.config.get("font_name", "Bahnschrift Condensed"))
        font = QFont(family)
        font.setBold(bold)
        row_scale = max(
            0.70,
            min(1.55, (float(self.config.get("row_height", 54.0)) / 54.0) ** 0.5),
        )
        # Em layouts compactos, o piso antigo de 6 px fazia várias
        # alterações de largura parecerem não afetar o texto. Um piso menor
        # preserva a escala linear; o recorte da célula evita sobreposição.
        requested = (
            float(self.config.get("font_size", 26))
            * multiplier * self._scale * row_scale
            * getattr(self, "_column_content_scale", 1.0)
        )
        row_height = max(
            14.0,
            float(self.config.get("row_height", 54.0)) * self._scale,
        )
        font.setPixelSize(max(3, round(min(requested, row_height * .68))))
        return font

    def _section_font(self, config_key: str, default_size: float, rect: QRectF, multiplier: float = 1.0) -> QFont:
        """Fonte independente para cada faixa do cabeçalho."""
        font = QFont(str(self.config.get("font_name", "Bahnschrift Condensed")))
        font.setBold(True)
        requested = (
            float(self.config.get(config_key, default_size))
            * multiplier
            * self._scale
            * getattr(self, "_column_content_scale", 1.0)
        )
        font.setPixelSize(max(3, round(min(requested, max(3.0, rect.height() * .78)))))
        return font

    def _global_header_height(self) -> float:
        return max(
            18.0,
            float(self.config.get("global_header_height", 58.0)) * self._scale,
            float(self.config.get("global_header_font_size", 20.0)) * self._scale * 1.35,
        )

    def _category_header_height(self) -> float:
        return max(
            14.0,
            float(self.config.get("category_header_height", 50.0)) * self._scale,
            float(self.config.get("category_header_font_size", 18.0)) * self._scale * 1.35,
        )

    def _legend_height(self) -> float:
        return max(
            12.0,
            30.0 * self._scale,
            float(self.config.get("column_legend_font_size", 12.0)) * self._scale * 1.45,
        )

    def _resize_handle_rect(self) -> QRectF:
        size = max(10.0, 15.0 * self._scale)
        return QRectF(self.width() - size - 4, self.height() - size - 4, size, size)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.edit_mode or event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self.selected.emit(self.widget_id)
        if self._resize_handle_rect().contains(event.position()):
            self._resizing = True
            self._resize_origin = event.globalPosition().toPoint()
            self._resize_width = self.width()
            self._resize_height = self.height()
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.edit_mode:
            event.ignore()
            return
        if self._resizing:
            delta = event.globalPosition().toPoint() - self._resize_origin
            width = max(self.minimumWidth(), self._resize_width + delta.x())
            if bool(self.config.get("auto_fit_height", True)):
                self.resize(width, self.height())
            else:
                self.resize(
                    width,
                    max(
                        self.minimumHeight(),
                        self._resize_height + delta.y(),
                    ),
                )
            event.accept()
            return
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if self._resize_handle_rect().contains(event.position()) else Qt.CursorShape.SizeAllCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        changed = self._dragging or self._resizing
        self._dragging = False
        self._resizing = False
        self.setCursor(Qt.CursorShape.SizeAllCursor if self.edit_mode else Qt.CursorShape.ArrowCursor)
        if changed:
            self._emit_geometry()
            event.accept()
        else:
            event.ignore()

    def _emit_geometry(self) -> None:
        screen = self.screen()
        if screen is None:
            return
        geometry = screen.geometry()
        self.geometry_changed.emit(
            self.widget_id,
            (self.x() - geometry.left()) / geometry.width(),
            (self.y() - geometry.top()) / geometry.height(),
            self.width() / geometry.width(),
            self.height() / geometry.height(),
        )


def format_lap(seconds: float) -> str:
    if seconds <= 0:
        return "--:--:---"
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes}:{remainder:06.3f}"


def tyre_short(value: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    aliases = (("SOFT", "S"), ("MEDIUM", "M"), ("HARD", "H"), ("WET", "W"), ("INTER", "I"))
    if "/" in text:
        tokens = []
        for part in text.split("/"):
            tokens.append(next((short for word, short in aliases if word in part), part[:1]))
        return "/".join(tokens)
    for word, short in aliases:
        if word in text:
            return short
    return text[:3]
