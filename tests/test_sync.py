from datetime import timedelta
import pytest
from requests.exceptions import ReadTimeout

from app.domain.models import Podcast
from app.integrations.errors import SpotifyRateLimited
from conftest import NOW, add_history, episode, raw_episode


def test_321_episodes_no_individual_progress_calls(make_service):
    service, client = make_service([episode(i) for i in range(321)])
    result = service.run_sync()
    assert result["final_total"] == 321
    assert client.lookups == []
    assert {limit for limit, _ in client.reads} == {50}
    assert service.state_repository.load()["last_playlist_size"] == 321


def test_fallback_only_missing_fields_and_per_execution_cache(make_service):
    service, client = make_service([episode(1), episode(2, position=None), episode(3, finished=None)])
    client.details["2"] = raw_episode(episode(2, position=40))
    client.details["3"] = raw_episode(episode(3))
    service.playlist_service.snapshot("playlist", True)
    service.playlist_service.snapshot("playlist", True)
    service.playlist_service.snapshot("playlist", False)
    assert client.lookups == ["2", "3"]
    service.gateway.begin_operation()
    service.playlist_service.snapshot("playlist", True)
    assert client.lookups == ["2", "3", "2", "3"]


def test_cleanup_preserves_processed_and_records_reasons(make_service):
    service, client = make_service([episode(1, finished=True), episode(2, added="2020-01-01T00:00:00Z"),
                                    episode(3, position=100, added="2020-01-01T00:00:00Z")])
    result = service.run_sync()
    assert (result["removed_finished"], result["removed_stalled"], result["final_total"]) == (1, 1, 1)
    state = service.state_repository.load()
    assert set(state["processed_episode_ids"]) == {"1", "2", "3"}
    assert {h["reason"] for h in state["history"]} == {"finished", "stalled"}
    assert all(h["status"] == "removed" for h in state["history"])


def test_new_episodes_priority_processed_and_completed_rules(make_service):
    service, client = make_service([episode(9, show="b")])
    service.podcasts_repository.save([Podcast("A", "a", 1), Podcast("B", "b", 2)])
    for e in [episode(1, show="a"), episode(2, show="a", finished=True), episode(3, show="a")]:
        client.catalog[e.uri] = raw_episode(e)
    client.shows["a"] = list(client.catalog.values())[1:]
    state = service.state_repository.load()
    state["processed_episode_ids"] = ["3"]
    service.state_repository.save(state)
    result = service.run_sync()
    assert result["new_found"] == 1
    assert client.uris == ["spotify:episode:1", "spotify:episode:9"]


def test_unknown_tracks_and_duplicates_survive_ordering(make_service):
    service, client = make_service([episode(1), episode(2)])
    client.catalog["spotify:track:music"] = {"type": "track", "uri": "spotify:track:music"}
    client.uris = ["spotify:track:music", "spotify:episode:1", "spotify:episode:2", "spotify:episode:1"]
    service.run_sync()
    assert sorted(client.uris) == sorted(["spotify:track:music", "spotify:episode:1", "spotify:episode:2", "spotify:episode:1"])


@pytest.mark.parametrize("action", ["remove", "restore", "add", "move"])
def test_crash_after_remote_before_local_reconciles_without_duplicate(make_service, action):
    e = episode(1, finished=action == "remove")
    service, client = make_service([e, episode(2)])
    ids = []
    if action == "restore":
        client.uris.remove(e.uri)
        ids = add_history(service, [e])
    elif action == "add":
        client.uris.remove(e.uri)
        service.podcasts_repository.save([Podcast("Podcast", "show", 1)])
        client.shows["show"] = [raw_episode(e)]
    def crash():
        raise ReadTimeout("ambiguous response")
    client.after_write = crash
    with pytest.raises(ReadTimeout):
        service.run_restore(ids) if action == "restore" else service.run_sync()
    assert service.state_repository.load()["pending_mutation"]
    service.gateway.begin_operation()
    service.run_restore(ids) if action == "restore" else service.run_sync()
    state = service.state_repository.load()
    assert state["pending_mutation"] is None
    assert len(client.uris) == len(set(client.uris))
    if action == "remove":
        assert len([h for h in state["history"] if h["status"] == "removed"]) == 1
    if action == "restore":
        assert state["history"][0]["status"] == "restored"
        assert len([w for w in client.writes if w[0] == "add"]) == 1


def test_batch_restoration_partial_failures_already_present_and_retry(make_service):
    episodes = [episode(i, finished=True) for i in range(3)]
    service, client = make_service(episodes)
    ids = add_history(service, episodes)
    client.uris = [episodes[0].uri]
    client.fail_add = {episodes[2].uri}
    result = service.run_restore(ids)
    assert (result["restored"], result["failed"]) == (2, 1)
    assert len([w for w in client.writes if w[0] == "add"]) == 1
    state = service.state_repository.load()
    assert state["history"][2]["status"] == "restore_failed"
    client.fail_add.clear()
    result = service.run_restore(ids)
    assert result["restored"] == 3
    assert len(client.uris) == 3
    result = service.run_sync()
    assert result["removed_finished"] == 0
    service.now = lambda: NOW + timedelta(days=15)
    result = service.run_sync()
    assert result["removed_stalled"] == 3
    assert len(service.state_repository.load()["history"]) == 6


def test_429_during_mutation_preserves_intent_and_no_false_success(make_service):
    service, client = make_service([episode(finished=True)])
    def limited(*args):
        raise SpotifyRateLimited("86000", "QUOTA_EXCEEDED")
    client.playlist_remove_all_occurrences_of_items = limited
    with pytest.raises(SpotifyRateLimited):
        service.run_sync()
    row = service.state_repository.load()["history"][0]
    assert row["status"] == "removal_pending"
    assert row["removed_at"] is None


def test_successful_bulk_restoration_uses_batches_and_no_progress_fallback(make_service):
    episodes = [episode(i, position=None, finished=None) for i in range(105)]
    service, client = make_service(episodes)
    ids = add_history(service, episodes)
    client.uris.clear()
    result = service.run_restore(ids)
    assert result["restored"] == 105
    assert [len(w[1]) for w in client.writes if w[0] == "add"] == [100, 5]
    assert client.lookups == []


def test_unconfirmed_removal_does_not_advance_last_success(make_service):
    service, client = make_service([episode(finished=True)])
    client.playlist_remove_all_occurrences_of_items = lambda *args: {"snapshot_id": "not-applied"}
    with pytest.raises(RuntimeError, match="remoções"):
        service.run_sync()
    assert service.state_repository.load()["last_sync_at"] is None
