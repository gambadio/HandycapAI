"""
Porcupine wake-word wrapper.
"""
import logging
import threading
import struct

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class PorcupineWake(QObject):
    keyword_triggered = Signal()
    error_occurred = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.ppn = None
        self.pa = None
        self.stream = None
        self._running = False

        if settings.get("wake_word_enabled", False):
            self._init()

    # ─────────────────────
    def _init(self):
        try:
            import pvporcupine
            import pyaudio

            access_key = self.settings.get("porcupine_api_key", "")
            if not access_key:
                self.error_occurred.emit("Picovoice API key missing")
                return

            # Use built-in keyword "porcupine" if custom not supplied
            self.ppn = pvporcupine.create(access_key=access_key, keywords=["porcupine"])

            self.pa = pyaudio.PyAudio()
            self.stream = self.pa.open(
                rate=self.ppn.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.ppn.frame_length,
            )

            self._running = True
            threading.Thread(target=self._loop, daemon=True).start()
            logger.info("Porcupine wake-word active")

        except ImportError:
            logger.warning("Porcupine deps not installed")
        except Exception as exc:
            logger.exception("Wake-word init failed")
            self.error_occurred.emit(str(exc))

    # ─────────────────────
    def _loop(self):
        try:
            while self._running:
                pcm = self.stream.read(self.ppn.frame_length, exception_on_overflow=False)
                pcm = struct.unpack_from("h" * self.ppn.frame_length, pcm)
                if self.ppn.process(pcm) >= 0:
                    logger.info("Wake-word detected")
                    self.keyword_triggered.emit()
        except Exception as exc:
            logger.exception("Wake-word loop error")
            self.error_occurred.emit(str(exc))

    def stop(self):
        self._running = False
        try:
            if self.stream:
                self.stream.close()
            if self.pa:
                self.pa.terminate()
            if self.ppn:
                self.ppn.delete()
        finally:
            logger.info("Wake-word stopped")