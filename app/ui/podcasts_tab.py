from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import Podcast
from app.repositories.podcasts_repository import PodcastsRepository


class PodcastsTab(QWidget):
    def __init__(self, podcasts_repository: PodcastsRepository) -> None:
        super().__init__()
        self.podcasts_repository = podcasts_repository
        self.editing_index: int | None = None
        self.busy = False

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._load_selected_into_form)

        self.name_input = QLineEdit()
        self.show_id_input = QLineEdit()
        self.priority_input = QSpinBox()
        self.priority_input.setRange(1, 999)
        self.priority_input.setValue(1)

        self.add_button = QPushButton("Add podcast")
        self.edit_button = QPushButton("Edit selected")
        self.save_edit_button = QPushButton("Save changes")
        self.remove_button = QPushButton("Remove selected")
        self.move_up_button = QPushButton("Move up")
        self.move_down_button = QPushButton("Move down")
        self.cancel_edit_button = QPushButton("Cancel edit")

        self.add_button.clicked.connect(self.add_podcast)
        self.edit_button.clicked.connect(self.start_edit_selected)
        self.save_edit_button.clicked.connect(self.save_edit)
        self.remove_button.clicked.connect(self.remove_selected)
        self.move_up_button.clicked.connect(self.move_up)
        self.move_down_button.clicked.connect(self.move_down)
        self.cancel_edit_button.clicked.connect(self.cancel_edit)

        form = QFormLayout()
        form.addRow("Name", self.name_input)
        form.addRow("Spotify show ID", self.show_id_input)
        form.addRow("Priority", self.priority_input)

        primary_buttons = QHBoxLayout()
        primary_buttons.addWidget(self.add_button)
        primary_buttons.addWidget(self.edit_button)
        primary_buttons.addWidget(self.save_edit_button)
        primary_buttons.addWidget(self.cancel_edit_button)

        reorder_buttons = QHBoxLayout()
        reorder_buttons.addWidget(self.move_up_button)
        reorder_buttons.addWidget(self.move_down_button)
        reorder_buttons.addWidget(self.remove_button)

        layout = QVBoxLayout()
        layout.addWidget(self.list_widget)
        layout.addLayout(form)
        layout.addLayout(primary_buttons)
        layout.addLayout(reorder_buttons)
        self.setLayout(layout)

        self.refresh_list()
        self._update_edit_mode(False)

    def refresh_list(self) -> None:
        self.list_widget.clear()
        podcasts = self._load_podcasts()

        for podcast in podcasts:
            self.list_widget.addItem(
                f"{podcast.priority}. {podcast.name} ({podcast.show_id})"
            )

        next_priority = len(podcasts) + 1
        self.priority_input.setMaximum(max(999, next_priority))
        if self.editing_index is None:
            self.priority_input.setValue(next_priority)

    def add_podcast(self) -> None:
        name = self.name_input.text().strip()
        show_id = self.show_id_input.text().strip()
        desired_priority = self.priority_input.value()

        if not name:
            QMessageBox.warning(self, "SunriseCast", "Please enter the podcast name.")
            return

        if not show_id:
            QMessageBox.warning(self, "SunriseCast", "Please enter the Spotify show ID.")
            return

        podcasts = self._load_podcasts()

        if any(podcast.show_id == show_id for podcast in podcasts):
            QMessageBox.warning(self, "SunriseCast", "This podcast is already in the list.")
            return

        insert_index = max(0, min(desired_priority - 1, len(podcasts)))
        podcasts.insert(
            insert_index,
            Podcast(name=name, show_id=show_id, priority=desired_priority),
        )

        podcasts = self._reassign_priorities(podcasts)
        self.podcasts_repository.save(podcasts)

        self.refresh_list()
        self._clear_form()
        self.list_widget.setCurrentRow(insert_index)
        QMessageBox.information(self, "SunriseCast", "Podcast added.")

    def start_edit_selected(self) -> None:
        current_row = self.list_widget.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "SunriseCast", "Select a podcast to edit.")
            return

        self.editing_index = current_row
        self._load_selected_into_form(current_row)
        self._update_edit_mode(True)

    def save_edit(self) -> None:
        if self.editing_index is None:
            QMessageBox.information(self, "SunriseCast", "No podcast is being edited.")
            return

        name = self.name_input.text().strip()
        show_id = self.show_id_input.text().strip()
        desired_priority = self.priority_input.value()

        if not name:
            QMessageBox.warning(self, "SunriseCast", "Please enter the podcast name.")
            return

        if not show_id:
            QMessageBox.warning(self, "SunriseCast", "Please enter the Spotify show ID.")
            return

        podcasts = self._load_podcasts()
        if self.editing_index < 0 or self.editing_index >= len(podcasts):
            QMessageBox.warning(self, "SunriseCast", "The selected podcast is no longer valid.")
            self.cancel_edit()
            return

        for index, podcast in enumerate(podcasts):
            if index != self.editing_index and podcast.show_id == show_id:
                QMessageBox.warning(self, "SunriseCast", "Another podcast already uses this show ID.")
                return

        podcasts.pop(self.editing_index)

        new_index = max(0, min(desired_priority - 1, len(podcasts)))
        podcasts.insert(
            new_index,
            Podcast(name=name, show_id=show_id, priority=desired_priority),
        )

        podcasts = self._reassign_priorities(podcasts)
        self.podcasts_repository.save(podcasts)

        self.editing_index = None
        self.refresh_list()
        self._clear_form()
        self._update_edit_mode(False)
        self.list_widget.setCurrentRow(new_index)
        QMessageBox.information(self, "SunriseCast", "Podcast updated.")

    def cancel_edit(self) -> None:
        self.editing_index = None
        self._clear_form()
        self._update_edit_mode(False)

    def remove_selected(self) -> None:
        current_row = self.list_widget.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "SunriseCast", "Select a podcast to remove.")
            return

        podcasts = self._load_podcasts()
        podcasts.pop(current_row)
        podcasts = self._reassign_priorities(podcasts)
        self.podcasts_repository.save(podcasts)

        self.editing_index = None
        self.refresh_list()
        self._clear_form()
        self._update_edit_mode(False)

        if podcasts:
            self.list_widget.setCurrentRow(min(current_row, len(podcasts) - 1))

    def move_up(self) -> None:
        current_row = self.list_widget.currentRow()
        if current_row <= 0:
            return

        podcasts = self._load_podcasts()
        podcasts[current_row - 1], podcasts[current_row] = podcasts[current_row], podcasts[current_row - 1]
        podcasts = self._reassign_priorities(podcasts)
        self.podcasts_repository.save(podcasts)

        self.editing_index = None
        self.refresh_list()
        self.list_widget.setCurrentRow(current_row - 1)
        self._update_edit_mode(False)

    def move_down(self) -> None:
        podcasts = self._load_podcasts()
        current_row = self.list_widget.currentRow()

        if current_row < 0 or current_row >= len(podcasts) - 1:
            return

        podcasts[current_row], podcasts[current_row + 1] = podcasts[current_row + 1], podcasts[current_row]
        podcasts = self._reassign_priorities(podcasts)
        self.podcasts_repository.save(podcasts)

        self.editing_index = None
        self.refresh_list()
        self.list_widget.setCurrentRow(current_row + 1)
        self._update_edit_mode(False)

    def _load_selected_into_form(self, current_row: int) -> None:
        if self.editing_index is not None and current_row != self.editing_index:
            self.editing_index = None
            self._update_edit_mode(False)
        podcasts = self._load_podcasts()

        if current_row < 0 or current_row >= len(podcasts):
            if self.editing_index is None:
                self._clear_form()
            return

        selected = podcasts[current_row]
        self.name_input.setText(selected.name)
        self.show_id_input.setText(selected.show_id)
        self.priority_input.setValue(selected.priority)

    def _load_podcasts(self) -> list[Podcast]:
        return self.podcasts_repository.load()

    def _clear_form(self) -> None:
        self.name_input.clear()
        self.show_id_input.clear()
        self.priority_input.setValue(len(self._load_podcasts()) + 1)

    def _update_edit_mode(self, editing: bool) -> None:
        self.add_button.setEnabled(not editing and not self.busy)
        self.edit_button.setEnabled(not editing and not self.busy)
        self.save_edit_button.setEnabled(editing and not self.busy)
        self.cancel_edit_button.setEnabled(editing)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        for button in (self.remove_button, self.move_up_button, self.move_down_button):
            button.setEnabled(not busy)
        self._update_edit_mode(self.editing_index is not None)

    def _reassign_priorities(self, podcasts: list[Podcast]) -> list[Podcast]:
        normalized: list[Podcast] = []

        for index, podcast in enumerate(podcasts, start=1):
            normalized.append(
                Podcast(
                    name=podcast.name,
                    show_id=podcast.show_id,
                    priority=index,
                )
            )

        return normalized
