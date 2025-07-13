#!/usr/bin/env python3
"""
HandycapAI – Application entry-point.
Uses qasync to bind Qt’s event loop to asyncio so that
all `asyncio.create_task` calls (voice, LLM, …) run correctly.
"""

import sys
import signal
import asyncio
import logging

from PySide6.QtWidgets import QApplication, QMessageBox
from qasync import QEventLoop

from ui.tray import TrayManager
from settings_ui import SettingsManager
from voice.state import VoiceManager
from llm.chat import ChatCompletionsTransport
from llm.realtime import RealtimeTransport

# ──────────────────────────
# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s | %(message)s",
)
logger = logging.getLogger("main")

# Handle ⌃C gracefully
signal.signal(signal.SIGINT, signal.SIG_DFL)

def start_app() -> None:
    """Initialise Qt -> asyncio bridge and launch the UI."""
    # Qt application
    app = QApplication(sys.argv)

    # Bind asyncio to the Qt event loop
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    async def bootstrap() -> None:
        try:
            settings = SettingsManager()

            # Check OpenAI key – warn only
            if not settings.get("openai_api_key", ""):
                QMessageBox.warning(
                    None,
                    "API Key Required",
                    "Please set your OpenAI API key in Settings before using the application.",
                )

            # Transports
            chat_transport = ChatCompletionsTransport(settings)
            realtime_transport = RealtimeTransport(settings)

            # Voice & Tray
            voice = VoiceManager(settings)
            TrayManager(app, settings, voice, chat_transport, realtime_transport)

            logger.info("HandycapAI started successfully")

        except Exception as exc:
            logger.exception("Startup failed")
            QMessageBox.critical(None, "Startup Error", f"Failed to start HandycapAI:\n{exc}")
            app.quit()

    # Run bootstrap as soon as event loop starts
    loop.create_task(bootstrap())

    # Start Qt + asyncio loop
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    start_app()