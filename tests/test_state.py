import json
import pytest
from app.repositories.state_repository import InvalidStateError, StateRepository


def test_migration_preserves_ids_stats_and_creates_exact_backup(tmp_path):
    path = tmp_path / "state.json"
    original = {"processed_episode_ids": ["a"], "last_sync_at": "2026-09-18", "last_removed_count": 5,
                "last_playlist_size": 321, "custom": "preserve"}
    path.write_text(json.dumps(original), encoding="utf-8")
    repo = StateRepository(path)
    state = repo.load()
    assert state["version"] == 2 and state["history"] == []
    assert all(state[key] == value for key, value in original.items())
    backups = list(tmp_path.glob("*.bak"))
    assert len(backups) == 1 and json.loads(backups[0].read_text()) == original
    assert repo.load() == state
    assert len(list(tmp_path.glob("*.bak"))) == 1


@pytest.mark.parametrize("content", ['{broken', '[]', '{"processed_episode_ids": 1}', '{"version": 99}'])
def test_invalid_state_not_erased(tmp_path, content):
    path = tmp_path / "state.json"
    path.write_text(content)
    with pytest.raises(InvalidStateError):
        StateRepository(path).load()
    assert path.read_text() == content


def test_atomic_write_failure_preserves_old_state(tmp_path, monkeypatch):
    repo = StateRepository(tmp_path / "state.json")
    before = repo.file_path.read_bytes()
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr("app.repositories.atomic.os.replace", fail)
    state = repo.load()
    state["last_playlist_size"] = 321
    with pytest.raises(OSError):
        repo.save(state)
    assert repo.file_path.read_bytes() == before


def test_legacy_rate_limit_imported_once_during_migration(tmp_path):
    from datetime import timedelta
    from app.domain.progress import utc_now
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"processed_episode_ids": ["old"], "last_sync_at": None}))
    wait = {"until": (utc_now() + timedelta(hours=23)).isoformat(), "reason": "RATE_LIMITED", "seconds": 86000}
    (tmp_path / "legacy_spotify_wait.json").write_text(json.dumps(wait), encoding="utf-8-sig")
    repo = StateRepository(path, playlist_id="playlist")
    state = repo.load()
    assert state["spotify_wait"] == wait
    assert state["pending_operation"]["auto_retry"]
    state["spotify_wait"] = None
    repo.save(state)
    assert repo.load()["spotify_wait"] is None


@pytest.mark.parametrize("field,value", [("spotify_wait", {}), ("pending_operation", {}),
                                        ("pending_mutation", {}), ("rate_limit_streak", -1)])
def test_structurally_invalid_v2_state_is_preserved(tmp_path, field, value):
    path = tmp_path / "state.json"
    state = StateRepository.empty()
    state[field] = value
    content = json.dumps(state)
    path.write_text(content)
    with pytest.raises(InvalidStateError):
        StateRepository(path).load()
    assert path.read_text() == content
