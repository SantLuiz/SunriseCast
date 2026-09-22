import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyOAuth

from app.integrations.errors import AuthenticationRequired, OperationCancelled, SpotifyRateLimited
from app.integrations.spotify_auth import BoundedSpotifyOAuth, HTTP_TIMEOUT, build_spotify_client, http_session, rate_limit_hook


def auth():
    return BoundedSpotifyOAuth(client_id="fake", client_secret="fake", redirect_uri="http://127.0.0.1:8888/callback",
                               scope="user-read-playback-position", cache_handler=MemoryCacheHandler(),
                               requests_timeout=HTTP_TIMEOUT, requests_session=http_session())


def test_http_api_and_oauth_have_no_retries_and_explicit_timeouts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = build_spotify_client(SimpleNamespace(client_id="fake", client_secret="fake",
                                                 redirect_uri="http://127.0.0.1:8888/callback"))
    assert client.requests_timeout == client.auth_manager.requests_timeout == (5, 20)
    assert client._session is client.auth_manager._session
    assert client._session.get_adapter("https://").max_retries.total == 0
    assert client.retries == client.status_retries == 0


def test_429_hook_preserves_header_and_structured_reason():
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "86000"
    response._content = json.dumps({"error": {"reason": "QUOTA_EXCEEDED"}}).encode()
    with pytest.raises(SpotifyRateLimited) as caught:
        rate_limit_hook(response)
    assert caught.value.retry_after == "86000"
    assert caught.value.reason == "QUOTA_EXCEEDED"


def test_automatic_auth_never_opens_browser(monkeypatch):
    manager = auth()
    browser = Mock()
    monkeypatch.setattr("app.integrations.spotify_auth.webbrowser.open", browser)
    with pytest.raises(AuthenticationRequired):
        manager.get_access_token(as_dict=False)
    browser.assert_not_called()


def test_expired_token_refreshes_with_timeout_without_interactive_login(monkeypatch):
    manager = auth()
    manager.cache_handler.save_token_to_cache({"access_token": "expired", "refresh_token": "refresh",
                                               "scope": manager.scope, "expires_at": 1})
    response = Mock()
    response.json.return_value = {"access_token": "renewed", "expires_in": 3600}
    post = Mock(return_value=response)
    monkeypatch.setattr(manager._session, "post", post)
    assert manager.get_access_token(as_dict=False) == "renewed"
    assert post.call_args.kwargs["timeout"] == (5, 20)


def test_manual_login_bounded_and_cancellable(monkeypatch):
    manager = auth()
    manager.interactive = True
    manager.login_timeout = 0
    server = Mock()
    server.__enter__ = Mock(return_value=server)
    server.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("app.integrations.spotify_auth.HTTPServer", Mock(return_value=server))
    browser = Mock()
    monkeypatch.setattr("app.integrations.spotify_auth.webbrowser.open", browser)
    with pytest.raises(AuthenticationRequired):
        manager.get_auth_response()
    browser.assert_called_once()
    server.handle_request.assert_not_called()
    manager.login_timeout = 120
    manager.cancelled = lambda: True
    with pytest.raises(OperationCancelled):
        manager.get_auth_response()
