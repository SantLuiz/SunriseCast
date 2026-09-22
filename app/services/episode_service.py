from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List

from app.domain.models import Episode, Podcast
from app.integrations.spotify_client import SpotifyGateway
from app.services.playlist_service import playback

logger = logging.getLogger(__name__)


class EpisodeService:
    def __init__(self, spotify_gateway: SpotifyGateway) -> None:
        self.spotify_gateway = spotify_gateway

    def get_recent_unfinished_episodes(
        self,
        podcast: Podcast,
        interval_days: int,
    ) -> List[Episode]:
        logger.debug(
            "Fetching episodes for podcast | name=%s show_id=%s interval_days=%s",
            podcast.name,
            podcast.show_id,
            interval_days,
        )

        cutoff_date = datetime.now() - timedelta(days=interval_days)

        episodes: List[Episode] = []
        offset = 0
        limit = 50

        while True:
            raw_items = self.spotify_gateway.get_show_episodes(
                show_id=podcast.show_id,
                limit=limit,
                offset=offset,
            )

            if not raw_items:
                break

            for raw in raw_items:
                episode = self._map_to_episode(raw, podcast)

                if episode is None:
                    continue

                episode_date = self._parse_date(episode.release_date)
                if episode_date is None:
                    logger.debug(
                        "Skipping episode: invalid date | episode_id=%s name=%s",
                        episode.id,
                        episode.name,
                    )
                    continue

                if episode_date < cutoff_date:
                    # como a API retorna ordenado por mais recente,
                    # podemos parar cedo
                    return episodes

                if not episode.is_finished:
                    episodes.append(episode)

            if len(raw_items) < limit:
                break

            offset += limit

        logger.debug(
            "Episodes fetched | podcast=%s count=%s",
            podcast.name,
            len(episodes),
        )

        return episodes

    def _map_to_episode(self, raw: dict, podcast: Podcast) -> Episode | None:
        if not isinstance(raw, dict):
            return None

        episode_id = raw.get("id")
        episode_uri = raw.get("uri")
        episode_name = raw.get("name")
        release_date = raw.get("release_date")

        if not episode_id or not episode_uri or not episode_name or not release_date:
            return None

        resume_point = raw.get("resume_point", {})
        if not isinstance(resume_point, dict):
            resume_point = {}

        is_finished, position = playback(raw)

        return Episode(
            id=episode_id,
            uri=episode_uri,
            name=episode_name,
            show_id=podcast.show_id,
            show_name=podcast.name,
            release_date=release_date,
            is_finished=is_finished,
            resume_position_ms=position,
        )

    def _parse_date(self, value: str) -> datetime | None:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except Exception:
            logger.warning("Failed to parse episode date | value=%s", value)
            return None
