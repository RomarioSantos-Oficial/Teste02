#  SectorFlow is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 SectorFlow developers
#  Based on TinyPedal - Copyright (C) 2022-2026 TinyPedal developers
#
#  This file is part of SectorFlow.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap


class WeatherIconManager:
    FILES = {
        "Pista": (
            "Pista.png",
            "pista.png",
            "track.png",
        ),
        "Sol": (
            "Sol.png",
            "sol.png",
            "sun.png",
        ),
        "noite": (
            "noite.png",
            "Noite.png",
            "moon.png",
        ),
        "nublado": (
            "nublado.png",
            "Nublado.png",
            "cloud.png",
        ),
        "noite_nublada": (
            "noite_nublada.png",
            "Noite_Nublada.png",
            "cloud_moon.png",
        ),
        "Chuva": (
            "Chuva.png",
            "chuva.png",
            "rain.png",
        ),
    }

    FALLBACK_TEXT = {
        "Pista": "TRK",
        "Sol": "SUN",
        "noite": "NIGHT",
        "nublado": "CLOUD",
        "noite_nublada": "CLOUD",
        "Chuva": "RAIN",
    }

    def __init__(
        self,
        project_root: Path,
        directory: str = "images/tempo",
    ) -> None:
        self.project_root = Path(
            project_root
        )
        configured = Path(directory)

        self.directory = (
            configured
            if configured.is_absolute()
            else self.project_root / configured
        )
        self._originals: dict[
            str,
            QPixmap,
        ] = {}
        self.refresh()

    def set_directory(
        self,
        directory: str,
    ) -> None:
        configured = Path(directory)
        resolved = (
            configured
            if configured.is_absolute()
            else self.project_root / configured
        )

        if resolved != self.directory:
            self.directory = resolved

        self.refresh()

    def refresh(self) -> None:
        self._originals.clear()

        if not self.directory.exists():
            return

        indexed = {
            path.name.lower(): path
            for path in self.directory.iterdir()
            if path.is_file()
        }

        for state, candidates in self.FILES.items():
            selected = None

            for filename in candidates:
                selected = indexed.get(
                    filename.lower()
                )

                if selected is not None:
                    break

            if selected is None:
                continue

            pixmap = QPixmap(
                str(selected)
            )

            if not pixmap.isNull():
                self._originals[state] = pixmap

    def pixmap(
        self,
        state: str,
        size: int,
    ) -> QPixmap | None:
        pixmap = self._originals.get(
            state
        )

        if pixmap is None:
            return None

        target = max(8, int(size))

        return pixmap.scaled(
            QSize(target, target),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def fallback_text(
        self,
        state: str,
    ) -> str:
        return self.FALLBACK_TEXT.get(
            state,
            "?",
        )
