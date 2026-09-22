"""Offline packaged smoke test. Only fictional data; never loads .env or OAuth."""
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase

from app.domain.models import Episode, Podcast
from app.repositories.podcasts_repository import PodcastsRepository
from app.repositories.settings_repository import SettingsRepository
from app.repositories.state_repository import StateRepository
from app.services.operation_controller import OperationController
from app.services.scheduler_service import SchedulerService
from app.ui.main_window import MainWindow
from app.integrations.spotify_auth import build_spotify_client
from app.integrations.spotify_client import SpotifyGateway


def smoke_test(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    # The offscreen Windows plugin does not discover native fonts on its own.
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))
        app.setFont(QFont("Segoe UI", 10))
    with tempfile.TemporaryDirectory(prefix="sunrisecast-demo-") as folder:
        root = Path(folder)
        # Validate the packaged network/auth imports without requesting a token or using a cache.
        client = build_spotify_client(SimpleNamespace(client_id="demo", client_secret="demo",
                                                      redirect_uri="http://127.0.0.1:8888/callback"))
        gateway = SpotifyGateway(client)
        assert gateway.client.requests_timeout == (5, 20)
        client._session.close()
        podcasts = PodcastsRepository(root / "podcasts.json")
        podcasts.save([Podcast("Ciência pela manhã", "demo-ciencia", 1),
                       Podcast("Histórias do cotidiano", "demo-historias", 2)])
        settings = SettingsRepository(root / "settings.json")
        state_repo = StateRepository(root / "state.json")
        state = state_repo.load()
        names = ["Como observamos o universo", "Uma cidade contada por seus moradores",
                 "O tempo e os relógios", "Conversas no caminho de casa"]
        for index, name in enumerate(names):
            podcast = podcasts.load()[index % 2]
            episode = Episode(f"demo-{index}", f"spotify:episode:demo{index}", name,
                              podcast.show_id, podcast.name, "2026-09-01", False, 0)
            state["history"].append({"id": f"history-{index}", "playlist_id": "demo-playlist",
                "episode": asdict(episode), "reason": "stalled" if index % 2 else "finished",
                "status": ["removed", "restored", "restore_failed", "removed"][index],
                "removed_at": f"2026-09-{20-index:02d}T12:30:00+00:00",
                "error": "Episódio temporariamente indisponível." if index == 2 else None})
        state_repo.save(state)
        service = SimpleNamespace(playlist_id="demo-playlist", podcasts_repository=podcasts,
                                  settings_repository=settings, state_repository=state_repo)
        controller = OperationController(service)
        scheduler = SchedulerService(controller, settings)
        window = MainWindow(service, settings, scheduler, controller)
        window.show()
        for index, name in enumerate(("podcasts", "historico", "preferencias")):
            window.tabs.setCurrentIndex(index)
            if name == "historico":
                window.history_tab.table.selectRow(0)
            app.processEvents()
            window.grab().save(str(destination / f"{name}.png"))
        window.tabs.setCurrentIndex(1)
        window.resize(800, 500)
        app.processEvents()
        window.grab().save(str(destination / "historico-minimo.png"))
        controller._status("Quota do Spotify excedida. Aguardando até 22/09 07:30:00. Retomada automática habilitada.")
        controller.available_changed.emit(False)
        app.processEvents()
        window.grab().save(str(destination / "espera.png"))
        window.allow_close()
        window.close()
        (destination / "smoke-result.json").write_text(json.dumps({
            "ok": True, "network_used": False, "personal_data_loaded": False,
            "history_rows": len(state["history"]), "screenshots": 5,
        }, indent=2), encoding="utf-8")
