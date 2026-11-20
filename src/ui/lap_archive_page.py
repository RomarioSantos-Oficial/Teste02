from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.i18n import tr
from src.laps.archive import LapArchiveStore, local_owner_key, set_active_owner_key


class LapArchivePage(QWidget):
    """Local-only view of the driver's saved personal-best laps."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.store = LapArchiveStore()
        self.store.copy_profiles_to_local()
        set_active_owner_key("offline")
        self._owner_key = local_owner_key()
        self._build_ui()
        self.refresh_local_records()

    @property
    def owner_key(self) -> str:
        return self._owner_key

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.archive_status = QLabel(
            tr("As melhores voltas v\u00e1lidas s\u00e3o salvas localmente automaticamente.")
        )
        self.archive_status.setWordWrap(True)
        root.addWidget(self.archive_status)

        headers = (
            "Escopo", "Pista", "Categoria", "Carro", "Nome", "Volta",
            "S1", "S2", "S3", "N\u00ba carro",
        )
        self.local_table = QTableWidget(0, len(headers))
        self.local_table.setHorizontalHeaderLabels([tr(value) for value in headers])
        self.local_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.local_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.local_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.local_table.verticalHeader().setVisible(False)
        self.local_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.local_table.horizontalHeader().setStretchLastSection(True)
        self.local_table.setAlternatingRowColors(True)
        root.addWidget(self.local_table, 1)

    @staticmethod
    def _format_time(seconds: float) -> str:
        if seconds <= 0.0:
            return "?"
        minutes, remainder = divmod(float(seconds), 60.0)
        return f"{int(minutes)}:{remainder:06.3f}" if minutes >= 1 else f"{remainder:.3f}"

    def refresh_local_records(self) -> None:
        records = self.store.all_personal_bests(self._owner_key)
        self.local_table.setRowCount(len(records))
        for row, record in enumerate(records):
            car = record.car_model or record.car_filename
            values = (
                tr("Categoria") if record.scope == "category" else tr("Modelo"),
                record.track,
                record.category,
                car,
                record.driver_name,
                self._format_time(record.lap_seconds),
                self._format_time(record.sector1),
                self._format_time(record.sector2),
                self._format_time(record.sector3),
                record.car_number,
            )
            for column, value in enumerate(values):
                self.local_table.setItem(row, column, QTableWidgetItem(str(value)))

        if not records:
            self.archive_status.setText(
                tr("Ainda n\u00e3o h\u00e1 uma volta v\u00e1lida completa salva neste perfil local.")
            )
        else:
            self.archive_status.setText(
                tr("{count} melhores voltas v\u00e1lidas salvas neste perfil.").format(
                    count=len(records)
                )
            )

    def retranslate(self) -> None:
        headers = (
            "Escopo", "Pista", "Categoria", "Carro", "Nome", "Volta",
            "S1", "S2", "S3", "N\u00ba carro",
        )
        self.local_table.setHorizontalHeaderLabels([tr(value) for value in headers])
        self.refresh_local_records()
