"""
Voice state-machine with extended listening mode.
"""

import asyncio
import logging
import os
from typing import Optional

from PySide6.QtCore import QObject, Signal, QSoundEffect, QUrl

from .wake import PorcupineWake
from .stt import STTManager

logger = logging.getLogger(__name__)

class VoiceManager(QObject):
    text_recognized = Signal(str)
    state_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.state = "idle"
        self._extended_task: Optional[asyncio.Task] = None

        # Components
        self.wake = PorcupineWake(settings)
        self.stt = STTManager(settings)

        # Sounds
        self._snd_on = self._load("sounds/start.wav")
        self._snd_off = self._load("sounds/stop.wav")

        # Signals
        self.wake.keyword_triggered.connect(self.start_listening)
        self.wake.error_occurred.connect(self.error_occurred.emit)
        self.stt.error_occurred.connect(self.error_occurred.emit)

    # ─────────────────────
    def _load(self, path):
        if not os.path.exists(path):
            return None
        s = QSoundEffect()
        s.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
        return s

    def _set_state(self, new: str):
        if self.state != new:
            prev = self.state
            self.state = new
            self.state_changed.emit(new)
            if prev == "idle" and new == "listening":
                self._snd_on.play() if self._snd_on else None
            if prev != "idle" and new == "idle":
                self._snd_off.play() if self._snd_off else None
            logger.info("Voice state %s → %s", prev, new)

    # ─────────────────────
    def start_listening(self):
        if self.state != "idle":
            return
        self._set_state("listening")
        asyncio.create_task(self._single_round())

    async def _single_round(self):
        try:
            self._set_state("processing")
            audio, audio_np = await self.stt.record()
            text = await self.stt.transcribe(audio, audio_np)
            if text:
                self.text_recognized.emit(text)
                # Extend?
                if "keep listening" in text.lower():
                    self._set_state("extended")
                    self._extended_task = asyncio.create_task(self._extended_loop())
                else:
                    self._set_state("idle")
            else:
                self._set_state("idle")
        except Exception as exc:
            logger.exception("Voice error")
            self.error_occurred.emit(str(exc))
            self._set_state("idle")

    async def _extended_loop(self):
        """Continuous speech until 'stop listening' command."""
        try:
            while self.state == "extended":
                try:
                    audio, audio_np = await self.stt.record(timeout=6)
                    text = await self.stt.transcribe(audio, audio_np)
                    if not text:
                        continue
                    if "stop listening" in text.lower():
                        self._set_state("idle")
                        break
                    self.text_recognized.emit(text)
                except Exception as exc:
                    logger.debug("Extended listen timeout/error: %s", exc)
                    continue
        finally:
            self._set_state("idle")

    # ─────────────────────
    def stop(self):
        if self._extended_task:
            self._extended_task.cancel()
        self._set_state("idle")
        self.wake.stop()