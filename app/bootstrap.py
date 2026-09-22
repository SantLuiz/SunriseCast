from app.config.logging_config import setup_logging
from app.config.settings import AppConfig
from app.integrations.spotify_auth import build_spotify_client
from app.integrations.spotify_client import SpotifyGateway
from app.integrations.tray_icon import SunriseCastTray
from app.repositories.podcasts_repository import PodcastsRepository
from app.repositories.settings_repository import SettingsRepository
from app.repositories.state_repository import StateRepository
from app.services.episode_service import EpisodeService
from app.services.playlist_service import PlaylistService
from app.services.scheduler_service import SchedulerService
from app.services.sync_service import SyncService
from app.services.operation_controller import OperationController
from app.ui.main_window import MainWindow
from app.utils.paths import resource_path

class Application:
    def __init__(
        self,
        config: AppConfig,
        window: MainWindow,
        scheduler: SchedulerService,
        tray: SunriseCastTray,
    ) -> None:
        self.config = config
        self.window = window
        self.scheduler = scheduler
        self.tray = tray

    def run(self) -> None:
        self.scheduler.start()
        self.tray.show()
        self.window.show()
        self.window.exec_app()


def build_application() -> Application:
    config = AppConfig.load()

    raw_spotify_client = build_spotify_client(config)
    spotify_gateway = SpotifyGateway(raw_spotify_client)

    podcasts_repository = PodcastsRepository(config.podcasts_file)
    state_repository = StateRepository(config.state_file, playlist_id=config.playlist_id)
    settings_repository = SettingsRepository(config.settings_file)

    episode_service = EpisodeService(spotify_gateway)
    playlist_service = PlaylistService(spotify_gateway)

    sync_service = SyncService(
        playlist_id=config.playlist_id,
        podcasts_repository=podcasts_repository,
        settings_repository=settings_repository,
        state_repository=state_repository,
        episode_service=episode_service,
        playlist_service=playlist_service,
    )

    controller = OperationController(sync_service)
    scheduler = SchedulerService(
        controller=controller,
        settings_repository=settings_repository,
    )

    window = MainWindow(
        sync_service=sync_service,
        settings_repository=settings_repository,
        scheduler_service=scheduler,
        controller=controller,
    )

    tray = SunriseCastTray(
        window=window,
        scheduler_service=scheduler,
        icon_path=str(resource_path("assets", "icon.ico")),
    )

    controller.completed.connect(tray.notify_outcome)
    controller.available_changed.connect(tray.sync_action.setEnabled)

    window.set_tray_controller(tray)

    return Application(
        config=config,
        window=window,
        scheduler=scheduler,
        tray=tray,
    )
