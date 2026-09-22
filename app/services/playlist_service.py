from app.domain.models import Episode, Podcast


def playback(raw):
    point = raw.get("resume_point") or {}
    if not isinstance(point, dict):
        point = {}
    finished = point.get("fully_played")
    position = point.get("resume_position_ms")
    return (finished if isinstance(finished, bool) else None,
            position if type(position) is int and position >= 0 else None)


class PlaylistService:
    def __init__(self, spotify_gateway):
        self.spotify_gateway = spotify_gateway
        self.report = lambda message: None

    def snapshot(self, playlist_id, progress=False):
        episodes, uris = [], []
        offset = 0
        while True:
            items = self.spotify_gateway.get_playlist_items(playlist_id, limit=50, offset=offset)
            for item in items:
                raw = (item.get("track") or item.get("item")) if isinstance(item, dict) else None
                if not isinstance(raw, dict) or not raw.get("uri"):
                    raise RuntimeError("A playlist contém um item indisponível sem URI. Não foi possível conferir a ordem com segurança.")
                uris.append(raw["uri"])
                episode = self._map_playlist_item_to_episode(item)
                if episode is not None:
                    if progress and (episode.is_finished is None or episode.resume_position_ms is None):
                        detail = self.spotify_gateway.get_episode(episode.id)
                        if detail:
                            finished, position = playback(detail)
                            if episode.is_finished is None:
                                episode.is_finished = finished
                            if episode.resume_position_ms is None:
                                episode.resume_position_ms = position
                    episodes.append(episode)
            self.report(f"Lendo playlist: {len(uris)} itens recebidos")
            if len(items) < 50:
                return episodes, uris
            offset += 50

    def get_playlist_episodes(self, playlist_id, progress=True):
        return self.snapshot(playlist_id, progress)[0]

    def _map_playlist_item_to_episode(self, item):
        raw = item.get("track") or item.get("item")
        if not isinstance(raw, dict) or raw.get("type") != "episode":
            return None
        show = raw.get("show") or {}
        if not isinstance(show, dict):
            show = {}
        if not all(raw.get(k) for k in ("id", "uri", "name")):
            return None
        finished, position = playback(raw)
        return Episode(id=raw["id"], uri=raw["uri"], name=raw["name"],
                       show_id=show.get("id", ""), show_name=show.get("name", "Podcast desconhecido"),
                       release_date=raw.get("release_date", ""), is_finished=finished,
                       resume_position_ms=position, added_at=item.get("added_at"))

    def build_desired_order(self, existing_unfinished: list[Episode], new_episodes: list[Episode],
                            podcasts: list[Podcast]):
        merged = {episode.id: episode for episode in reversed(existing_unfinished + new_episodes)}
        grouped = {}
        for episode in merged.values():
            grouped.setdefault(episode.show_id, []).append(episode)
        known = [p.show_id for p in sorted(podcasts, key=lambda p: p.priority)]
        show_order = known + sorted(set(grouped) - set(known))
        return [episode for show_id in show_order for episode in
                sorted(grouped.get(show_id, []), key=lambda e: (e.release_date, e.name.lower()), reverse=True)]

    @staticmethod
    def extract_episode_ids(episodes):
        return {episode.id for episode in episodes}
