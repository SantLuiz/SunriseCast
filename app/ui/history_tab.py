from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from app.domain.progress import parse_time

REASONS = {"finished": "Finalizado", "stalled": "Encalhado"}
STATUSES = {"removed": "Removido", "restored": "Restaurado", "restore_failed": "Falha na restauração",
            "removal_failed": "Remoção não confirmada", "removal_pending": "Remoção a conferir",
            "restore_pending": "Restauração a conferir"}


class HistoryTab(QWidget):
    def __init__(self, repository, controller):
        super().__init__()
        self.repository = repository
        self.controller = controller
        self.available = True
        self.rows = []
        self.search = QLineEdit()
        self.search.setPlaceholderText("Pesquisar episódio ou podcast")
        self.reason = QComboBox()
        self.reason.addItem("Todos os motivos", "")
        for key, text in REASONS.items():
            self.reason.addItem(text, key)
        self.status = QComboBox()
        self.status.addItem("Todas as situações", "")
        for key, text in STATUSES.items():
            self.status.addItem(text, key)
        filters = QHBoxLayout()
        for widget in (self.search, self.reason, self.status):
            filters.addWidget(widget)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Episódio", "Podcast", "Remoção", "Motivo", "Situação"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setMinimumSectionSize(100)
        self.table.setWordWrap(False)
        self.restore = QPushButton("Restaurar selecionados (0)")
        self.restore.clicked.connect(self.restore_selected)
        self.summary = QLabel("Selecione episódios removidos para restaurar. Use Ctrl ou Shift para selecionar vários.")
        self.summary.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self.table)
        layout.addWidget(self.summary)
        layout.addWidget(self.restore)
        self.search.textChanged.connect(self.render)
        self.reason.currentIndexChanged.connect(self.render)
        self.status.currentIndexChanged.connect(self.render)
        self.table.itemSelectionChanged.connect(self.update_selection)
        self.controller.history_changed.connect(self.reload)
        self.controller.available_changed.connect(self.set_available)
        self.controller.completed.connect(self.show_result)
        self.reload()

    def reload(self):
        try:
            self.rows = [h for h in self.repository.load()["history"]
                         if h["playlist_id"] == self.controller.service.playlist_id]
            self.rows.sort(key=lambda h: h.get("removed_at") or h.get("requested_at", ""), reverse=True)
            self.render()
        except Exception as exc:
            self.summary.setText(str(exc))

    def render(self):
        term = self.search.text().strip().casefold()
        rows = [h for h in self.rows if term in (h["episode"]["name"] + " " + h["episode"]["show_name"]).casefold()
                and (not self.reason.currentData() or h["reason"] == self.reason.currentData())
                and (not self.status.currentData() or h["status"] == self.status.currentData())]
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            removed = parse_time(row.get("removed_at"))
            values = [row["episode"]["name"], row["episode"]["show_name"],
                      removed.astimezone().strftime("%d/%m/%Y %H:%M") if removed else "A conferir",
                      REASONS[row["reason"]], STATUSES[row["status"]]]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, row["id"])
                item.setToolTip(row.get("error") or value)
                self.table.setItem(index, col, item)
        self.update_selection()

    def selected_ids(self):
        selected = {self.table.item(index.row(), 0).data(Qt.UserRole)
                    for index in self.table.selectionModel().selectedRows() if self.table.item(index.row(), 0)}
        return [h["id"] for h in self.rows if h["id"] in selected and h.get("removed_at")
                and h["status"] in ("removed", "restore_failed", "restore_pending")]

    def update_selection(self):
        count = len(self.selected_ids())
        self.restore.setText(f"Restaurar selecionados ({count})")
        self.restore.setEnabled(self.available and count > 0)

    def set_available(self, available):
        self.available = available
        self.update_selection()

    def restore_selected(self):
        self.controller.request_restore(self.selected_ids())

    def show_result(self, outcome):
        result = outcome.get("result", {})
        if result.get("kind") == "restore":
            self.summary.setText(f"{result['restored']} restaurações confirmadas; {result['failed']} falhas. "
                                 "Detalhes individuais na coluna Situação (passe o mouse para ver o erro).")
        elif outcome["status"] != "success":
            self.summary.setText("Operação interrompida. Resultados confirmados estão na tabela; itens a conferir serão reconciliados na próxima tentativa.")
