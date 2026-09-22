from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton, QTabWidget, QVBoxLayout, QWidget

from app.ui.history_tab import HistoryTab
from app.ui.podcasts_tab import PodcastsTab
from app.ui.settings_tab import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self, sync_service, settings_repository, scheduler_service, controller):
        super().__init__()
        self.sync_service = sync_service
        self.controller = controller
        self.tray_controller = None
        self._allow_close = False
        self.setWindowTitle("SunriseCast")
        self.resize(1000, 650)
        self.setMinimumSize(800, 500)
        central = QWidget()
        layout = QVBoxLayout(central)
        self.status_label = QLabel("Pronto.")
        self.status_label.setWordWrap(True)
        self.sync_button = QPushButton("Sincronizar agora")
        self.sync_button.clicked.connect(self.run_sync)
        self.tabs = QTabWidget()
        self.settings_tab = SettingsTab(settings_repository, scheduler_service.refresh)
        self.podcasts_tab = PodcastsTab(sync_service.podcasts_repository)
        self.history_tab = HistoryTab(sync_service.state_repository, controller)
        self.tabs.addTab(self.podcasts_tab, "Podcasts")
        self.tabs.addTab(self.history_tab, "Histórico")
        self.tabs.addTab(self.settings_tab, "Preferências")
        layout.addWidget(self.status_label)
        layout.addWidget(self.sync_button)
        layout.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.controller.status_changed.connect(self.status_label.setText)
        self.controller.available_changed.connect(self.sync_button.setEnabled)
        self.controller.busy_changed.connect(self.set_busy)

    def set_busy(self, busy):
        # Tabs and local navigation remain usable. Only configuration writes are locked.
        self.settings_tab.save_button.setEnabled(not busy)
        self.podcasts_tab.set_busy(busy)

    def set_tray_controller(self, tray_controller):
        self.tray_controller = tray_controller

    def allow_close(self):
        self._allow_close = True

    def run_sync(self):
        self.controller.request_sync()

    def closeEvent(self, event: QCloseEvent):
        if self._allow_close:
            event.accept()
        elif self.tray_controller is not None:
            self.tray_controller.handle_close_event(event)
        elif self.controller.busy:
            event.ignore()
            self.controller.ready_to_quit.connect(QApplication.instance().quit)
            self.controller.shutdown()
        else:
            event.accept()

    def exec_app(self):
        QApplication.instance().exec()
