from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
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
        self.local_table.itemSelectionChanged.connect(self._update_delete_button)
        root.addWidget(self.local_table, 1)

        self.delete_lap_button = QPushButton(tr("Excluir volta selecionada"))
        self.delete_lap_button.setEnabled(False)
        self.delete_lap_button.clicked.connect(self._delete_selected_lap)
        root.addWidget(self.delete_lap_button)

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
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, record.record_id)
                self.local_table.setItem(row, column, item)

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

    def _update_delete_button(self) -> None:
        self.delete_lap_button.setEnabled(self.local_table.currentRow() >= 0)

    def _delete_selected_lap(self) -> None:
        row = self.local_table.currentRow()
        if row < 0:
            return
        item = self.local_table.item(row, 0)
        record_id = str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""
        if not record_id:
            return
        answer = QMessageBox.question(
            self,
            tr("Excluir volta de referência"),
            tr("Esta ação remove somente a volta rápida selecionada do arquivo local. O jogo não será alterado. Deseja continuar?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self.store.delete_personal_best(record_id, self._owner_key):
            self.refresh_local_records()
            self.archive_status.setText(
                tr("Referência removida. A próxima volta válida poderá criar uma nova referência do Delta.")
            )

    def retranslate(self) -> None:
        headers = (
            "Escopo", "Pista", "Categoria", "Carro", "Nome", "Volta",
            "S1", "S2", "S3", "N\u00ba carro",
        )
        self.local_table.setHorizontalHeaderLabels([tr(value) for value in headers])
        self.delete_lap_button.setText(tr("Excluir volta selecionada"))
        self.refresh_local_records()
