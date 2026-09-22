import copy
import os
from dataclasses import asdict
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from spotipy.exceptions import SpotifyException

from app.domain.models import Episode
from app.integrations.spotify_client import SpotifyGateway
from app.repositories.podcasts_repository import PodcastsRepository
from app.repositories.settings_repository import SettingsRepository
from app.repositories.state_repository import StateRepository
from app.services.episode_service import EpisodeService
from app.services.playlist_service import PlaylistService
from app.services.sync_service import SyncService

NOW = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)


def episode(number="1", position=0, finished=False, added="2026-09-20T12:00:00Z", show="show"):
    return Episode(str(number), f"spotify:episode:{number}", f"Episódio {number}", show,
                   f"Podcast {show}", "2026-09-21", finished, position, added)


def raw_episode(e):
    raw = {"id": e.id, "uri": e.uri, "name": e.name, "type": "episode",
           "release_date": e.release_date, "show": {"id": e.show_id, "name": e.show_name}}
    point = {}
    if e.is_finished is not None:
        point["fully_played"] = e.is_finished
    if e.resume_position_ms is not None:
        point["resume_position_ms"] = e.resume_position_ms
    if point:
        raw["resume_point"] = point
    return raw


class FakeSpotify:
    auth_manager = None

    def __init__(self, episodes):
        self.catalog = {e.uri: raw_episode(e) for e in episodes}
        self.added = {e.uri: e.added_at for e in episodes}
        self.uris = [e.uri for e in episodes]
        self.reads = []
        self.lookups = []
        self.writes = []
        self.details = {}
        self.shows = {}
        self.fail_add = set()
        self.after_write = None
        self.read_error = None

    def playlist_items(self, playlist_id, limit, offset, **kwargs):
        if self.read_error:
            raise self.read_error
        self.reads.append((limit, offset))
        return {"items": [{("track" if i % 2 else "item"): copy.deepcopy(self.catalog[u]),
                            "added_at": self.added.get(u)}
                           for i, u in enumerate(self.uris[offset:offset + limit])]}

    def episode(self, episode_id, **kwargs):
        self.lookups.append(episode_id)
        return copy.deepcopy(self.details.get(episode_id, self.catalog.get(f"spotify:episode:{episode_id}")))

    def show_episodes(self, show_id, offset, limit, **kwargs):
        return {"items": copy.deepcopy(self.shows.get(show_id, [])[offset:offset + limit])}

    def _written(self):
        if self.after_write:
            callback, self.after_write = self.after_write, None
            callback()
        return {"snapshot_id": "confirmed"}

    def playlist_add_items(self, playlist_id, uris):
        if set(uris) & self.fail_add:
            raise SpotifyException(403, -1, "unavailable")
        self.writes.append(("add", list(uris)))
        self.uris.extend(uris)
        return self._written()

    def playlist_remove_all_occurrences_of_items(self, playlist_id, uris):
        self.writes.append(("remove", list(uris)))
        self.uris = [u for u in self.uris if u not in uris]
        return self._written()

    def playlist_reorder_items(self, playlist_id, start, before, range_length):
        self.writes.append(("move", start, before, range_length))
        block = self.uris[start:start + range_length]
        del self.uris[start:start + range_length]
        self.uris[before:before] = block
        return self._written()


@pytest.fixture
def make_service(tmp_path):
    def make(episodes=()):
        client = FakeSpotify(episodes)
        gateway = SpotifyGateway(client)
        gateway.begin_operation()
        podcasts = PodcastsRepository(tmp_path / "podcasts.json")
        podcasts.save([])
        service = SyncService("playlist", podcasts, SettingsRepository(tmp_path / "settings.json"),
                              StateRepository(tmp_path / "state.json"), EpisodeService(gateway), PlaylistService(gateway))
        service.now = lambda: NOW
        return service, client
    return make


def add_history(service, episodes, status="removed"):
    state = service.state_repository.load()
    rows = [{"id": f"history-{e.id}", "playlist_id": "playlist", "episode": asdict(e),
             "reason": "finished" if e.is_finished else "stalled", "status": status,
             "removed_at": "2026-09-20T12:00:00+00:00", "requested_at": "2026-09-20T12:00:00+00:00",
             "restored_at": None, "error": None} for e in episodes]
    state["history"].extend(rows)
    state["processed_episode_ids"].extend(e.id for e in episodes)
    service.state_repository.save(state)
    return [h["id"] for h in rows]
