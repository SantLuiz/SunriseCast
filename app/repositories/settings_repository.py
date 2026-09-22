from __future__ import annotations

import json
from pathlib import Path

from app.config.constants import DEFAULT_INTERVAL_DAYS, DEFAULT_SYNC_ENABLED, DEFAULT_SYNC_TIMES
from app.domain.models import SyncSettings
from app.repositories.atomic import atomic_json


class SettingsRepository:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        if self.file_path.exists():
            return
        self.save(SyncSettings())

    def load(self) -> SyncSettings:
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return SyncSettings(
                auto_sync_enabled=DEFAULT_SYNC_ENABLED,
                interval_days=DEFAULT_INTERVAL_DAYS,
                sync_times=list(DEFAULT_SYNC_TIMES),
            )

        return SyncSettings(
            auto_sync_enabled=bool(data.get("auto_sync_enabled", DEFAULT_SYNC_ENABLED)),
            interval_days=int(data.get("interval_days", DEFAULT_INTERVAL_DAYS)),
            sync_times=list(data.get("sync_times", DEFAULT_SYNC_TIMES)),
        )

    def save(self, settings: SyncSettings) -> None:
        payload = {
            "auto_sync_enabled": settings.auto_sync_enabled,
            "interval_days": settings.interval_days,
            "sync_times": settings.sync_times,
        }
        atomic_json(self.file_path, payload)
