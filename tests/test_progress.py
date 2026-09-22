from datetime import timedelta
import pytest

from app.domain.progress import observe, reset_after_restore
from conftest import NOW, episode


@pytest.mark.parametrize("age,expected", [(14, None), (14.00001, "stalled"), (15, "stalled")])
def test_initial_unstarted_strict_age(age, expected):
    e = episode(added=(NOW - timedelta(days=age)).isoformat())
    assert observe(e, {}, NOW) == expected


def test_partial_starts_observation_and_publication_irrelevant():
    e = episode(position=100, added="2020-01-01T00:00:00Z")
    e.release_date = "1999-01-01"
    state = {}
    assert observe(e, state, NOW) is None
    assert observe(e, state, NOW + timedelta(days=14)) is None
    assert observe(e, state, NOW + timedelta(days=15)) == "stalled"


def test_rewind_and_then_advance():
    e = episode(position=200)
    state = {}
    observe(e, state, NOW)
    e.resume_position_ms = 100
    observe(e, state, NOW + timedelta(days=10))
    assert state[e.id]["last_advance_at"] == NOW.isoformat()
    e.resume_position_ms = 110
    observe(e, state, NOW + timedelta(days=11))
    assert observe(e, state, NOW + timedelta(days=20)) is None


def test_unknown_data_never_backdates_when_data_appears():
    e = episode(position=None, finished=None, added="2000-01-01T00:00:00Z")
    state = {}
    assert observe(e, state, NOW) is None
    e.resume_position_ms, e.is_finished = 0, False
    assert observe(e, state, NOW + timedelta(days=40)) is None
    e.resume_position_ms = None
    assert observe(e, state, NOW + timedelta(days=100)) is None


def test_missing_or_invalid_added_at_starts_now():
    for value in (None, "bad-date"):
        assert observe(episode(added=value), {}, NOW) is None


def test_finished_takes_precedence():
    assert observe(episode(finished=True, added="2000-01-01T00:00:00Z"), {}, NOW) == "finished"


def test_restored_finished_requires_incomplete_then_complete():
    e = episode(finished=True)
    state = {}
    reset_after_restore(e, state, NOW)
    assert observe(e, state, NOW + timedelta(days=1)) is None
    e.is_finished = False
    assert observe(e, state, NOW + timedelta(days=2)) is None
    e.is_finished = True
    assert observe(e, state, NOW + timedelta(days=3)) == "finished"


def test_restored_finished_without_progress_becomes_stalled():
    e = episode(finished=True)
    state = {}
    reset_after_restore(e, state, NOW)
    assert observe(e, state, NOW + timedelta(days=15)) == "stalled"


def test_restore_with_unknown_position_waits_for_observable_baseline():
    e = episode(position=None, finished=None, added="2000-01-01T00:00:00Z")
    state = {}
    reset_after_restore(e, state, NOW)
    assert observe(e, state, NOW + timedelta(days=30)) is None
    e.resume_position_ms, e.is_finished = 100, False
    assert observe(e, state, NOW + timedelta(days=31)) is None
