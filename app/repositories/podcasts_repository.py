from __future__ import annotations

import json
from pathlib import Path
from typing import List

from app.domain.models import Podcast
from app.repositories.atomic import atomic_json


class PodcastsRepository:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        if self.file_path.exists():
            return

        payload = {
            "shows": [
                {"name": "Example Podcast", "show_id": "spotify_show_id_here", "priority": 1}
            ]
        }
        atomic_json(self.file_path, payload)

    def load(self) -> List[Podcast]:
        data = json.loads(self.file_path.read_text(encoding="utf-8"))
        shows = data.get("shows", [])

        podcasts: List[Podcast] = []
        for index, show in enumerate(shows, start=1):
            if not isinstance(show, dict):
                continue

            name = str(show.get("name", "")).strip()
            show_id = str(show.get("show_id", "")).strip()
            priority = int(show.get("priority", index))

            if not name or not show_id:
                continue

            podcasts.append(Podcast(name=name, show_id=show_id, priority=priority))

        return sorted(podcasts, key=lambda podcast: podcast.priority)

    def save(self, podcasts: List[Podcast]) -> None:
        payload = {
            "shows": [
                {"name": podcast.name, "show_id": podcast.show_id, "priority": podcast.priority}
                for podcast in sorted(podcasts, key=lambda item: item.priority)
            ]
        }
        atomic_json(self.file_path, payload)
