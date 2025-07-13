"""
Voice state-machine with extended listening mode.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtMultimedia import QSoundEffect

from .wake import PorcupineWake
from .stt import STTManager

logger = logging.getLogger(__name__)

class VoiceManager(QObject):
    text_recognized = Signal(str)   # emitted with the final transcript
    state_changed   = Signal(str)   # "idle" | "listening" | "processing" | "extended"
    error_occurred  = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.state: str = "idle"
        self._extended_task: Optional[asyncio.Task] = None

        # Components
        self.wake = PorcupineWake(settings)
        self.stt  = STTManager(settings)

        # Load start/stop chimes  (.wav preferred, fall back to .mp3)
        self._snd_on  = self._load_sound("sounds/start")
        self._snd_off = self._load_sound("sounds/stop")

        # Signals
        self.wake.keyword_triggered.connect(self.start_listening)
        self.wake.error_occurred.connect(self.error_occurred.emit)
        self.stt.error_occurred.connect(self.error_occurred.emit)

    # ────────────────────────────────────────────────────────
    def _load_sound(self, stem: str) -> Optional[QSoundEffect]:
        """
        Try to load <stem>.wav, else <stem>.mp3; return QSoundEffect or None.
        """
        for ext in (".wav", ".mp3"):
            fn = f"{stem}{ext}"
            if os.path.exists(fn):
                s = QSoundEffect()
                s.setSource(QUrl.fromLocalFile(os.path.abspath(fn)))
                return s
        logger.warning("Sound file not found for %s.[wav|mp3]", stem)
        return None

    def _set_state(self, new: str):
        if self.state == new:
            return
        prev = self.state
        self.state = new
        self.state_changed.emit(new)

        if prev == "idle" and new == "listening" and self._snd_on:
            self._snd_on.play()
        if prev != "idle" and new == "idle" and self._snd_off:
            self._snd_off.play()

        logger.info("Voice state %s → %s", prev, new)

    # ────────────────────────────────────────────────────────
    # State transitions
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
        """
        Continuous speech until user says 'stop listening' (or hot-key).
        """
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

    # ────────────────────────────────────────────────────────
    def stop(self):
        """Called on app quit or manual cancel key."""
        if self._extended_task:
            self._extended_task.cancel()
        self._set_state("idle")
        self.wake.stop()