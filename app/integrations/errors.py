from datetime import timedelta
from email.utils import parsedate_to_datetime

from app.domain.progress import utc_now


class OperationCancelled(RuntimeError):
    pass


class AuthenticationRequired(RuntimeError):
    pass


class SpotifyRateLimited(RuntimeError):
    def __init__(self, retry_after=None, reason=None):
        self.retry_after = retry_after
        self.reason = reason or "RATE_LIMITED"
        super().__init__("Quota do Spotify excedida" if self.reason == "QUOTA_EXCEEDED"
                         else "Limite de requisições do Spotify atingido")

    def waiting_state(self, streak, now=None):
        now = now or utc_now()
        seconds = None
        if self.retry_after is not None:
            try:
                seconds = max(1, int(self.retry_after))
            except (TypeError, ValueError):
                try:
                    seconds = max(1, int((parsedate_to_datetime(self.retry_after) - now).total_seconds()))
                except (TypeError, ValueError, OverflowError):
                    pass
        if seconds is None:
            seconds = min(3600, 60 * 2 ** min(streak, 6))
        return {"until": (now + timedelta(seconds=seconds)).isoformat(),
                "retry_after": self.retry_after, "reason": self.reason, "seconds": seconds}
