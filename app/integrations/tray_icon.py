from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QAction, QCloseEvent, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from app.services.scheduler_service import SchedulerService
from app.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


class SunriseCastTray:
    def __init__(
        self,
        window: MainWindow,
        scheduler_service: SchedulerService,
        icon_path: str | None = None,
    ) -> None:
        self.window = window
        self.scheduler_service = scheduler_service
        self._force_quit = False

        self.tray_icon = QSystemTrayIcon(self.window)
        self.tray_icon.setToolTip("SunriseCast")

        icon = self._load_icon(icon_path)
        self.tray_icon.setIcon(icon)
        self.window.setWindowIcon(icon)

        menu = QMenu()

        self.open_action = QAction("Abrir SunriseCast", self.window)
        self.open_action.triggered.connect(self.show_window)

        self.sync_action = QAction("Sincronizar agora", self.window)
        self.sync_action.triggered.connect(self.run_sync)

        self.hide_action = QAction("Ocultar janela", self.window)
        self.hide_action.triggered.connect(self.hide_window)

        self.quit_action = QAction("Sair", self.window)
        self.quit_action.triggered.connect(self.quit_application)

        menu.addAction(self.open_action)
        menu.addAction(self.sync_action)
        menu.addAction(self.hide_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_activated)

    def show(self) -> None:
        self.tray_icon.show()
        logger.info("System tray icon initialized")

    def show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        logger.info("Main window shown from tray")

    def hide_window(self) -> None:
        self.window.hide()
        logger.info("Main window hidden to tray")

    def run_sync(self) -> None:
        logger.info("Manual synchronization triggered from tray")
        self.show_window()
        self.window.run_sync()

    def notify_sync_success(
        self,
        *,
        new_found: int,
        removed_finished: int,
        final_total: int,
        automatic: bool,
    ) -> None:
        mode = "Automatic sync" if automatic else "Synchronization completed"
        message = (
            f"New: {new_found} | "
            f"Removed finished: {removed_finished} | "
            f"Playlist total: {final_total}"
        )
        self.tray_icon.showMessage(
            "SunriseCast",
            f"{mode}\n{message}",
            QSystemTrayIcon.Information,
            5000,
        )

    def notify_sync_error(self, error_message: str, *, automatic: bool) -> None:
        mode = "Automatic sync failed" if automatic else "Synchronization failed"
        self.tray_icon.showMessage(
            "SunriseCast",
            f"{mode}\n{error_message}",
            QSystemTrayIcon.Critical,
            7000,
        )

    def quit_application(self) -> None:
        logger.info("Application exit requested from tray")
        self._force_quit = True
        self.scheduler_service.stop()
        self.quit_action.setEnabled(False)
        self.window.controller.ready_to_quit.connect(self._finish_quit)
        self.window.controller.shutdown()

    def _finish_quit(self) -> None:
        self.tray_icon.hide()
        self.window.allow_close()
        self.window.close()
        QApplication.instance().quit()

    def notify_outcome(self, outcome) -> None:
        level = QSystemTrayIcon.Information if outcome["status"] in ("success", "waiting") else QSystemTrayIcon.Warning
        self.tray_icon.showMessage("SunriseCast", self.window.controller.last_status, level, 7000)

    def handle_close_event(self, event: QCloseEvent) -> None:
        if self._force_quit:
            event.accept()
            return

        self.window.hide()
        self.tray_icon.showMessage(
            "SunriseCast",
            "O SunriseCast continua em execução na bandeja.",
            QSystemTrayIcon.Information,
            3000,
        )
        logger.info("Close intercepted; application minimized to tray")
        event.ignore()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
        ):
            if self.window.isVisible():
                self.hide_window()
            else:
                self.show_window()

    def _load_icon(self, icon_path: str | None) -> QIcon:
        if icon_path:
            path = Path(icon_path).resolve()
            logger.info("Trying tray icon path: %s", path)

            if not path.exists():
                logger.warning("Tray icon file does not exist: %s", path)
            else:
                logger.info("Tray icon file exists: %s", path)

                icon = QIcon(str(path))
                if not icon.isNull():
                    logger.info("Tray icon loaded successfully: %s", path)
                    return icon

                logger.warning("Tray icon file exists but Qt could not load it: %s", path)

        fallback = self.window.style().standardIcon(QStyle.SP_ComputerIcon)
        logger.warning("Using fallback system icon")
        return fallback
