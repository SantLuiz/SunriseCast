import threading
import time
from datetime import timedelta

from PySide6.QtCore import QTimer
from spotipy.exceptions import SpotifyException

from app.domain.models import SyncSettings
from app.domain.progress import parse_time
from app.integrations.errors import AuthenticationRequired, SpotifyRateLimited
from app.services.operation_controller import OperationController
from app.services.scheduler_service import SchedulerService
from app.ui.main_window import MainWindow
from conftest import NOW, add_history, episode


def wait_finished(qtbot, controller):
    qtbot.waitUntil(lambda: not controller.busy, timeout=5000)


def test_responsive_single_operation_and_cooperative_shutdown(qtbot, make_service):
    service, client = make_service([episode()])
    entered, release = threading.Event(), threading.Event()
    original = client.playlist_items
    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)
    client.playlist_items = slow
    controller = OperationController(service)
    scheduler = SchedulerService(controller, service.settings_repository)
    window = MainWindow(service, service.settings_repository, scheduler, controller)
    qtbot.addWidget(window)
    window.show()
    ticks = []
    pulse = QTimer()
    pulse.timeout.connect(lambda: ticks.append(1))
    pulse.start(5)
    try:
        assert controller.request_sync()
        qtbot.waitUntil(entered.is_set)
        assert not controller.request_sync()
        assert not controller.request_restore(["x"])
        assert not window.settings_tab.save_button.isEnabled()
        assert not window.podcasts_tab.add_button.isEnabled()
        window.tabs.setCurrentIndex(1)
        assert window.history_tab.isVisible()
        qtbot.waitUntil(lambda: len(ticks) >= 3)
        ready = []
        controller.ready_to_quit.connect(lambda: ready.append(1))
        start = time.monotonic()
        controller.shutdown()
        assert time.monotonic() - start < .2
        assert ready == []
    finally:
        release.set()
        wait_finished(qtbot, controller)
        pulse.stop()
    assert ready == [1]
    assert controller.thread is None


def test_86000_second_quota_persists_restart_and_auto_resume(qtbot, make_service):
    service, client = make_service([episode()])
    client.read_error = SpotifyException(429, -1, "limited", headers={"Retry-After": "86000"}, reason="QUOTA_EXCEEDED")
    service.settings_repository.save(SyncSettings(auto_sync_enabled=True))
    controller = OperationController(service)
    assert controller.request_sync()
    wait_finished(qtbot, controller)
    assert controller.outcome["status"] == "waiting"
    state = service.state_repository.load()
    assert state["spotify_wait"]["seconds"] == 86000
    assert state["spotify_wait"]["reason"] == "QUOTA_EXCEEDED"
    restarted = OperationController(service)
    assert not restarted.request_sync()
    assert not restarted.busy
    # At expiry, a new worker starts from a fresh playlist read and authentication context.
    client.read_error = None
    restarted.now = lambda: parse_time(state["spotify_wait"]["until"]) + timedelta(seconds=1)
    restarted.check_pending()
    assert restarted.busy
    wait_finished(qtbot, restarted)
    assert restarted.outcome["status"] == "success"
    assert service.state_repository.load()["spotify_wait"] is None


def test_no_auto_resume_when_disabled_and_no_hidden_login(qtbot, make_service):
    service, client = make_service()
    state = service.state_repository.load()
    state["spotify_wait"] = {"until": (NOW - timedelta(seconds=1)).isoformat(), "reason": "RATE_LIMITED", "seconds": 60}
    state["pending_operation"] = {"kind": "sync", "playlist_id": "playlist", "auto_retry": True}
    service.state_repository.save(state)
    controller = OperationController(service)
    controller.now = lambda: NOW
    controller.check_pending()
    assert not controller.busy
    service.settings_repository.save(SyncSettings(auto_sync_enabled=True))
    client.read_error = AuthenticationRequired("Faça login manualmente")
    controller.check_pending()
    wait_finished(qtbot, controller)
    assert controller.outcome["status"] == "auth"
    controller.check_pending()
    assert not controller.busy
    assert service.state_repository.load()["pending_operation"]["auto_retry"] is False


def test_backoff_and_manual_restore_resume(qtbot, make_service):
    assert [SpotifyRateLimited().waiting_state(i, NOW)["seconds"] for i in range(9)] == [60, 120, 240, 480, 960, 1920, 3600, 3600, 3600]
    service, client = make_service([episode()])
    ids = add_history(service, [episode()])
    client.uris.clear()
    state = service.state_repository.load()
    state["pending_operation"] = {"kind": "restore", "playlist_id": "playlist", "history_ids": ids}
    service.state_repository.save(state)
    controller = OperationController(service)
    controller.request_sync()
    wait_finished(qtbot, controller)
    assert controller.outcome["result"]["kind"] == "restore"


def test_history_filters_multiselect_and_persists_after_restart(qtbot, make_service):
    service, client = make_service([episode(1), episode(2, finished=True)])
    ids = add_history(service, [episode(1), episode(2, finished=True)])
    controller = OperationController(service)
    scheduler = SchedulerService(controller, service.settings_repository)
    window = MainWindow(service, service.settings_repository, scheduler, controller)
    qtbot.addWidget(window)
    tab = window.history_tab
    tab.table.selectAll()
    assert set(tab.selected_ids()) == set(ids)
    assert tab.restore.text() == "Restaurar selecionados (2)"
    tab.reason.setCurrentIndex(tab.reason.findData("finished"))
    assert tab.table.rowCount() == 1
    tab.search.setText("not-found")
    assert tab.table.rowCount() == 0
    tab.search.clear()
    tab.reason.setCurrentIndex(0)
    tab.table.selectAll()
    tab.restore_selected()
    wait_finished(qtbot, controller)
    assert all(h["status"] == "restored" for h in service.state_repository.load()["history"])
    assert len(tab.rows) == 2
    assert "2 restaurações confirmadas" in tab.summary.text()
