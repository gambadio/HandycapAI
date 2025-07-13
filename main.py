#!/usr/bin/env python3
"""
HandycapAI — application entry-point.

• Binds Qt’s event-loop to asyncio via qasync.
• Selects the correct transports (Chat-Completions, Realtime-basic,
  Realtime-advanced) via TransportFactory according to settings.
• Registers the VoiceManager, TTS, system-tray and quick settings bar.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from qasync import QEventLoop

from llm.transport_factory import TransportFactory
from settings_ui import SettingsManager
from ui.tray import TrayManager
from voice.state import VoiceManager
from voice.tts import TTSManager

# ──────────────────────────────  logging  ──────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s | %(message)s",
)
logger = logging.getLogger("main")

# Allow ⌃C
signal.signal(signal.SIGINT, signal.SIG_DFL)

def start_app() -> None:
    """Qt + asyncio bootstrap."""
    # High-DPI / Retina
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # Bind the asyncio loop
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    async def bootstrap() -> None:
        try:
            settings = SettingsManager()

            # Transports (factory auto-selects correct realtime impl.)
            chat_transport = TransportFactory.create_chat_transport(settings)
            realtime_transport = TransportFactory.create_realtime_transport(settings)

            # Voice (wake-word + STT) and TTS
            voice_mgr = VoiceManager(settings)
            tts_mgr = TTSManager(settings)

            # System-tray root
            TrayManager(
                app,
                settings,
                voice_mgr,
                tts_mgr,
                chat_transport,
                realtime_transport,
            )

            logger.info("HandycapAI started successfully")

        except Exception as exc:  # noqa: BLE001
            logger.exception("Startup failed")
            QMessageBox.critical(None, "Startup Error", f"Failed to start HandycapAI:\n{exc}")
            app.quit()

    loop.create_task(bootstrap())

    with loop:
        loop.run_forever()

if __name__ == "__main__":
    start_app()