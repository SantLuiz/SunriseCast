from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import SyncSettings
from app.repositories.settings_repository import SettingsRepository


class SettingsTab(QWidget):
    def __init__(self, settings_repository: SettingsRepository, on_settings_changed) -> None:
        super().__init__()
        self.settings_repository = settings_repository
        self.on_settings_changed = on_settings_changed

        self.auto_sync_checkbox = QCheckBox("Enable automatic synchronization")
        self.interval_days_input = QSpinBox()
        self.interval_days_input.setRange(1, 60)

        self.sync_times_input = QLineEdit()
        self.sync_times_input.setPlaceholderText("06:30, 12:00, 18:30")

        self.save_button = QPushButton("Save settings")
        self.save_button.clicked.connect(self.save_settings)

        layout = QVBoxLayout()
        form = QFormLayout()
        form.addRow("Automatic sync", self.auto_sync_checkbox)
        form.addRow("Interval in days", self.interval_days_input)
        form.addRow("Times (HH:MM, comma separated)", self.sync_times_input)
        layout.addLayout(form)
        layout.addWidget(self.save_button)
        self.setLayout(layout)

        self.load_settings()

    def load_settings(self) -> None:
        settings = self.settings_repository.load()
        self.auto_sync_checkbox.setChecked(settings.auto_sync_enabled)
        self.interval_days_input.setValue(settings.interval_days)
        self.sync_times_input.setText(", ".join(settings.sync_times))

    def save_settings(self) -> None:
        times = [item.strip() for item in self.sync_times_input.text().split(",") if item.strip()]
        normalized_times = self._normalize_times(times)

        if not normalized_times:
            QMessageBox.warning(
                self,
                "SunriseCast",
                "Please enter at least one valid time in HH:MM format.",
            )
            return

        settings = SyncSettings(
            auto_sync_enabled=self.auto_sync_checkbox.isChecked(),
            interval_days=self.interval_days_input.value(),
            sync_times=normalized_times,
        )
        self.settings_repository.save(settings)
        self.on_settings_changed()
        QMessageBox.information(self, "SunriseCast", "Settings saved successfully.")

    def _normalize_times(self, times: list[str]) -> list[str]:
        valid_times: list[str] = []
        seen: set[str] = set()

        for value in times:
            candidate = value.strip()
            if not self._is_valid_time(candidate):
                continue
            candidate = datetime.strptime(candidate, "%H:%M").strftime("%H:%M")

            if candidate in seen:
                continue

            seen.add(candidate)
            valid_times.append(candidate)

        valid_times.sort()
        return valid_times

    def _is_valid_time(self, value: str) -> bool:
        try:
            datetime.strptime(value, "%H:%M")
            return True
        except ValueError:
            return False
