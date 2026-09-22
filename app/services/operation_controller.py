import logging

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from app.domain.progress import parse_time, utc_now
from app.integrations.errors import AuthenticationRequired, OperationCancelled, SpotifyRateLimited

logger = logging.getLogger(__name__)


class OperationWorker(QObject):
    progress = Signal(str)
    done = Signal(dict)

    def __init__(self, service, operation, interactive):
        super().__init__()
        self.service = service
        self.operation = operation
        self.interactive = interactive

    @Slot()
    def run(self):
        repo = self.service.state_repository
        try:
            state = repo.load()
            state["pending_operation"] = {**self.operation, "auto_retry": False}
            repo.save(state)
            self.service.gateway.begin_operation(
                self.interactive, QThread.currentThread().isInterruptionRequested)
            self.service.report = self.progress.emit
            result = (self.service.run_restore(self.operation["history_ids"])
                      if self.operation["kind"] == "restore" else self.service.run_sync())
            state = repo.load()
            state.update(spotify_wait=None, pending_operation=None, rate_limit_streak=0)
            repo.save(state)
            outcome = {"status": "success", "result": result}
        except SpotifyRateLimited as exc:
            try:
                state = repo.load()
                wait = exc.waiting_state(state.get("rate_limit_streak", 0))
                state.update(spotify_wait=wait, rate_limit_streak=state.get("rate_limit_streak", 0) + 1,
                             pending_operation={**self.operation, "auto_retry": True})
                repo.save(state)
                outcome = {"status": "waiting", "wait": wait}
            except Exception as persist_error:
                outcome = {"status": "error", "message": f"Não foi possível salvar a espera: {persist_error}"}
        except AuthenticationRequired as exc:
            outcome = {"status": "auth", "message": str(exc)}
        except OperationCancelled as exc:
            outcome = {"status": "cancelled", "message": str(exc)}
        except Exception as exc:
            logger.exception("Operation failed")
            outcome = {"status": "error", "message": str(exc)}
        finally:
            self.service.report = lambda message: None
            self.service.playlist_service.report = lambda message: None
        self.done.emit(outcome)


class OperationController(QObject):
    busy_changed = Signal(bool)
    available_changed = Signal(bool)
    status_changed = Signal(str)
    completed = Signal(dict)
    history_changed = Signal()
    ready_to_quit = Signal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.busy = False
        self.closing = False
        self.thread = None
        self.worker = None
        self.outcome = None
        self.now = utc_now
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.check_pending)
        self.last_status = ""

    def start(self):
        self.timer.start()
        self.check_pending()

    def _waiting(self, state):
        wait = state.get("spotify_wait")
        until = parse_time(wait.get("until")) if wait else None
        return wait if until and until > self.now() else None

    def _wait_message(self, wait):
        time = parse_time(wait["until"]).astimezone().strftime("%d/%m %H:%M:%S")
        reason = "Quota do Spotify excedida" if wait["reason"] == "QUOTA_EXCEEDED" else "Limite do Spotify atingido"
        auto = self.service.settings_repository.load().auto_sync_enabled
        suffix = "Retomada automática habilitada." if auto else "Automático desativado. Tente após esse horário."
        return f"{reason}. Aguardando até {time}. {suffix}"

    def _status(self, message):
        if message != self.last_status:
            self.last_status = message
            self.status_changed.emit(message)

    def request_sync(self, automatic=False):
        return self.request({"kind": "sync", "playlist_id": self.service.playlist_id}, automatic)

    def request_restore(self, history_ids):
        if not history_ids:
            return False
        return self.request({"kind": "restore", "history_ids": list(history_ids),
                             "playlist_id": self.service.playlist_id}, False)

    def request(self, operation, automatic=False):
        if self.busy or self.closing:
            return False
        try:
            state = self.service.state_repository.load()
            wait = self._waiting(state)
            if wait:
                self._status(self._wait_message(wait))
                return False
            pending = state.get("pending_operation")
            if pending and pending.get("playlist_id") != self.service.playlist_id:
                raise RuntimeError("Há uma operação pendente em outra playlist. Confira a configuração antes de continuar.")
            # Finish an interrupted restoration before accepting different work.
            if pending and pending.get("kind") == "restore":
                operation = pending
        except Exception as exc:
            self._status(str(exc))
            return False
        self.busy = True
        self.outcome = None
        self.busy_changed.emit(True)
        self.available_changed.emit(False)
        self._status("Iniciando operação…")
        self.thread = QThread(self)
        self.worker = OperationWorker(self.service, operation, not automatic)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._status)
        self.worker.done.connect(self._receive)
        self.worker.done.connect(self.thread.quit)
        self.worker.done.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        return True

    @Slot(dict)
    def _receive(self, outcome):
        self.outcome = outcome

    @Slot()
    def _finished(self):
        self.busy = False
        self.thread = None
        self.worker = None
        self.busy_changed.emit(False)
        outcome = self.outcome or {"status": "error", "message": "Worker terminou sem resultado."}
        if outcome["status"] == "waiting":
            self._status(self._wait_message(outcome["wait"]))
        elif outcome["status"] == "success":
            result = outcome["result"]
            if result["kind"] == "restore":
                self._status(f"Restauração: {result['restored']} confirmados; {result['failed']} falhas.")
            else:
                self._status(f"Concluído. Novos: {result['new_found']} | Finalizados: {result['removed_finished']} | "
                             f"Encalhados: {result['removed_stalled']} | Playlist: {result['final_total']}")
        else:
            self._status(outcome["message"])
        self.history_changed.emit()
        self.completed.emit(outcome)
        self.available_changed.emit(not self.closing and outcome["status"] != "waiting")
        if self.closing:
            self.ready_to_quit.emit()

    @Slot()
    def check_pending(self):
        if self.busy or self.closing:
            return
        try:
            state = self.service.state_repository.load()
            wait = self._waiting(state)
            self.available_changed.emit(not bool(wait))
            if wait:
                self._status(self._wait_message(wait))
                return
            pending = state.get("pending_operation")
            if pending and pending.get("auto_retry") and self.service.settings_repository.load().auto_sync_enabled:
                self.request(pending, automatic=True)
        except Exception as exc:
            self.available_changed.emit(False)
            self._status(str(exc))

    def shutdown(self):
        self.closing = True
        self.timer.stop()
        self.available_changed.emit(False)
        if self.thread is not None:
            self._status("Encerrando após a chamada em andamento…")
            self.thread.requestInterruption()
        else:
            self.ready_to_quit.emit()
