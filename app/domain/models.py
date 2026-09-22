from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(slots=True)
class Podcast:
    name: str
    show_id: str
    priority: int


@dataclass(slots=True)
class Episode:
    id: str
    uri: str
    name: str
    show_id: str
    show_name: str
    release_date: str
    is_finished: bool | None = None
    resume_position_ms: int | None = None
    added_at: str | None = None


@dataclass(slots=True)
class SyncSettings:
    auto_sync_enabled: bool = False
    interval_days: int = 14
    sync_times: List[str] = field(default_factory=lambda: ["06:30"])
