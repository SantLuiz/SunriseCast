from typing import Any
import spotipy
from spotipy.exceptions import SpotifyException

from app.config.constants import EPISODE_FETCH_LIMIT, SPOTIFY_MARKET
from app.integrations.errors import AuthenticationRequired, OperationCancelled, SpotifyRateLimited


class SpotifyGateway:
    def __init__(self, client: spotipy.Spotify):
        self.client = client
        self.cancelled = lambda: False
        self.cache = {}

    def begin_operation(self, interactive=False, cancelled=None):
        self.cache = {}
        self.cancelled = cancelled or (lambda: False)
        auth = self.client.auth_manager
        if auth is not None:
            auth.interactive = interactive
            auth.cancelled = self.cancelled

    def check_cancelled(self):
        if self.cancelled():
            raise OperationCancelled("Operação interrompida. Alterações pendentes serão conferidas na próxima execução.")

    def _call(self, method, *args, **kwargs):
        self.check_cancelled()
        try:
            return method(*args, **kwargs)
        except SpotifyException as exc:
            if exc.http_status == 429:
                headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
                raise SpotifyRateLimited(headers.get("retry-after"), exc.reason) from exc
            if exc.http_status == 401:
                auth = self.client.auth_manager
                if auth is not None:
                    # Invalidate a revoked but not yet expired token. The next manual run
                    # can refresh/authorize; automatic runs still cannot open a browser.
                    cached = auth.cache_handler.get_cached_token()
                    if cached:
                        cached["expires_at"] = 0
                        auth.cache_handler.save_token_to_cache(cached)
                raise AuthenticationRequired("Autorização do Spotify expirada. Sincronize manualmente para entrar novamente.") from exc
            raise

    def get_show_episodes(self, show_id, limit=EPISODE_FETCH_LIMIT, offset=0):
        response = self._call(self.client.show_episodes, show_id, limit=limit,
                              offset=offset, market=SPOTIFY_MARKET)
        return self._items(response)

    def get_playlist_items(self, playlist_id, limit=50, offset=0):
        response = self._call(self.client.playlist_items, playlist_id, limit=limit,
                              offset=offset, market=SPOTIFY_MARKET, additional_types=("episode",))
        return self._items(response)

    @staticmethod
    def _items(response):
        if not isinstance(response, dict) or not isinstance(response.get("items"), list):
            raise RuntimeError("Resposta inválida do Spotify; operação interrompida para preservar a playlist.")
        return response["items"]

    def get_episode(self, episode_id):
        if episode_id not in self.cache:
            try:
                self.cache[episode_id] = self._call(self.client.episode, episode_id, market=SPOTIFY_MARKET)
            except SpotifyException as exc:
                if exc.http_status not in (403, 404):
                    raise
                self.cache[episode_id] = None
        return self.cache[episode_id]

    # Exactly one remote mutation per method. The service journals and confirms each batch.
    def add_items_to_playlist(self, playlist_id, uris):
        return self._call(self.client.playlist_add_items, playlist_id, uris)

    def remove_all_occurrences_from_playlist(self, playlist_id, uris):
        return self._call(self.client.playlist_remove_all_occurrences_of_items, playlist_id, uris)

    def reorder_items(self, playlist_id, range_start, insert_before, range_length=1):
        return self._call(self.client.playlist_reorder_items, playlist_id,
                          range_start, insert_before, range_length=range_length)
