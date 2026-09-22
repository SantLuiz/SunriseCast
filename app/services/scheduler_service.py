from datetime import datetime
from PySide6.QtCore import QTimer


class SchedulerService:
    def __init__(self, controller, settings_repository):
        self.controller = controller
        self.settings_repository = settings_repository
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.executed = set()

    def start(self):
        self.controller.start()
        self.timer.start(30_000)
        self._tick()

    def stop(self):
        self.timer.stop()

    def refresh(self):
        self.controller.check_pending()
        self._tick()

    def _tick(self):
        settings = self.settings_repository.load()
        if not settings.auto_sync_enabled:
            return
        now = datetime.now()
        self.executed = {key for key in self.executed if key.startswith(now.strftime("%Y-%m-%d"))}
        times = set()
        for value in settings.sync_times:
            try:
                times.add(datetime.strptime(value.strip(), "%H:%M").strftime("%H:%M"))
            except (ValueError, AttributeError):
                continue
        key = now.strftime("%Y-%m-%d %H:%M")
        if now.strftime("%H:%M") in times and key not in self.executed:
            # Record dispatch, including auth/error, to avoid repeating a failed login in the same slot.
            self.executed.add(key)
            self.controller.request_sync(automatic=True)
