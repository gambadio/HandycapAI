import logging
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import QObject

from ui.chats_ui import ChatsWindow
from settings_ui import SettingsWindow

logger = logging.getLogger(__name__)


class TrayManager(QObject):
    """System-tray & global windows registry."""

    def __init__(self, app, settings, voice, chat_transport, realtime_transport):
        super().__init__()
        self.app = app
        self.settings = settings
        self.voice = voice

        self.chat_transport = chat_transport
        self.realtime_transport = realtime_transport

        # Tray icon
        self.tray = QSystemTrayIcon(QIcon("icons/mic_grey.png"))
        menu = QMenu()

        chat_act = QAction("Open chats", self)
        chat_act.triggered.connect(self._open_chats)
        menu.addAction(chat_act)

        settings_act = QAction("Settings", self)
        settings_act.triggered.connect(self._open_settings)
        menu.addAction(settings_act)

        menu.addSeparator()
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self._quit)
        menu.addAction(quit_act)

        self.tray.setContextMenu(menu)
        self.tray.show()

        # Windows refs
        self._chat_win = None
        self._settings_win = None

        # Voice state → icon
        voice.state_changed.connect(self._update_icon)

        logger.info("System tray ready")

    # ─────────────────────
    def _update_icon(self, state: str):
        icon = {
            "listening": "icons/mic_cyan.png",
            "processing": "icons/mic_cyan_pulse.png",
        }.get(state, "icons/mic_grey.png")
        self.tray.setIcon(QIcon(icon))

    def _open_chats(self):
        if self._chat_win is None:
            self._chat_win = ChatsWindow(self.settings, self.voice,
                                         self.chat_transport, self.realtime_transport)
        self._chat_win.show()
        self._chat_win.raise_()

    def _open_settings(self):
        if self._settings_win is None:
            self._settings_win = SettingsWindow(self.settings)
        self._settings_win.show()
        self._settings_win.raise_()

    def _quit(self):
        logger.info("Exiting application")
        self.voice.stop()
        self.app.quit()