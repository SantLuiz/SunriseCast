from datetime import datetime, timedelta, timezone

from app.domain.models import Episode


def utc_now():
    return datetime.now(timezone.utc)


def parse_time(value):
    if not value or not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except ValueError:
        return None


def observe(episode: Episode, observations: dict, now: datetime) -> str | None:
    """Unknown playback never establishes inactivity. Rewinds change the baseline only."""
    entry = observations.setdefault(episode.id, {})
    position = episode.resume_position_ms
    previous = entry.get("position_ms")
    if position is not None:
        if not entry.get("last_advance_at"):
            initial = now
            if not entry.get("seen") and position == 0 and episode.is_finished is False:
                initial = parse_time(episode.added_at) or now
            entry["last_advance_at"] = min(initial, now).isoformat()
        elif previous is not None and position > previous:
            entry["last_advance_at"] = now.isoformat()
        entry["position_ms"] = position
    entry["seen"] = True
    if entry.get("suppress_finished") and episode.is_finished is False:
        entry["suppress_finished"] = False
    if episode.is_finished is True and not entry.get("suppress_finished"):
        return "finished"
    since = parse_time(entry.get("last_advance_at"))
    if position is not None and since and now - since > timedelta(days=14):
        return "stalled"
    return None


def reset_after_restore(episode: Episode, observations: dict, now: datetime):
    observations[episode.id] = {
        "seen": True, "position_ms": episode.resume_position_ms,
        "last_advance_at": now.isoformat() if episode.resume_position_ms is not None else None,
        "restored_at": now.isoformat(),
        "suppress_finished": episode.is_finished is not False,
    }
