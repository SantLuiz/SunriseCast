import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests
import spotipy
from spotipy.cache_handler import CacheFileHandler
from requests.adapters import HTTPAdapter
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError

from app.config.settings import AppConfig
from app.integrations.errors import AuthenticationRequired, OperationCancelled, SpotifyRateLimited

SCOPES = ["playlist-modify-private", "playlist-modify-public", "playlist-read-private",
          "user-library-read", "user-read-playback-position"]
HTTP_TIMEOUT = (5, 20)


def rate_limit_hook(response, *args, **kwargs):
    if response.status_code == 429:
        try:
            body = response.json()
            error = body.get("error", {})
            reason = error.get("reason") if isinstance(error, dict) else None
            reason = reason or body.get("reason")
        except (ValueError, AttributeError):
            reason = None
        raise SpotifyRateLimited(response.headers.get("Retry-After"), reason)
    return response


def http_session():
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=0))
    session.mount("http://", HTTPAdapter(max_retries=0))
    session.hooks["response"].append(rate_limit_hook)
    return session


class BoundedSpotifyOAuth(SpotifyOAuth):
    interactive = False
    cancelled = staticmethod(lambda: False)
    login_timeout = 120

    def get_access_token(self, code=None, as_dict=True, check_cache=True):
        try:
            return super().get_access_token(code=code, as_dict=as_dict, check_cache=check_cache)
        except SpotifyOauthError as exc:
            if exc.error not in ("invalid_grant", "invalid_client"):
                raise
            if self.interactive and exc.error == "invalid_grant":
                return super().get_access_token(as_dict=as_dict, check_cache=False)
            raise AuthenticationRequired("Autorização necessária. Use Sincronizar agora para entrar no Spotify.") from exc

    def get_auth_response(self, open_browser=None):
        if not self.interactive:
            raise AuthenticationRequired("Autorização necessária. Use Sincronizar agora para entrar no Spotify.")
        redirect = urlparse(self.redirect_uri)
        if redirect.scheme != "http" or redirect.hostname not in ("127.0.0.1", "localhost") or not redirect.port:
            raise AuthenticationRequired("Configure SPOTIPY_REDIRECT_URI com http://127.0.0.1:PORTA/callback para autorizar.")
        self.state = secrets.token_urlsafe(32)
        result = {}
        expected_state = self.state
        expected_path = redirect.path or "/"

        class Callback(BaseHTTPRequestHandler):
            def do_GET(handler):
                parsed = urlparse(handler.path)
                query = parse_qs(parsed.query)
                if parsed.path != expected_path or query.get("state", [None])[0] != expected_state:
                    handler.send_error(400)
                    return
                result["code"] = query.get("code", [None])[0]
                result["error"] = query.get("error", [None])[0]
                handler.send_response(200)
                handler.end_headers()
                handler.wfile.write(b"SunriseCast: pode fechar esta janela.")

            def log_message(self, *args):
                pass

            def setup(self):
                super().setup()
                self.connection.settimeout(1)

        with HTTPServer((redirect.hostname, redirect.port), Callback) as server:
            server.timeout = 0.5
            webbrowser.open(self.get_authorize_url())
            deadline = time.monotonic() + self.login_timeout
            while not result and time.monotonic() < deadline:
                if self.cancelled():
                    raise OperationCancelled("Autorização cancelada.")
                server.handle_request()
        if not result.get("code"):
            raise AuthenticationRequired("Autorização não concluída em até 120 segundos. Tente novamente.")
        return result["code"]


def build_spotify_client(config: AppConfig) -> spotipy.Spotify:
    session = http_session()
    auth_manager = BoundedSpotifyOAuth(
        client_id=config.client_id, client_secret=config.client_secret,
        redirect_uri=config.redirect_uri, scope=" ".join(SCOPES), open_browser=False,
        cache_handler=CacheFileHandler(cache_path=".spotify_cache"), show_dialog=True,
        requests_session=session, requests_timeout=HTTP_TIMEOUT,
    )
    return spotipy.Spotify(auth_manager=auth_manager, requests_session=session,
                          requests_timeout=HTTP_TIMEOUT, retries=0, status_retries=0, backoff_factor=0)
