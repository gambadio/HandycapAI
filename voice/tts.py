"""
Asynchronous wrapper around OpenAI /v1/audio/speech
to generate voice output and play via QSoundEffect.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QSoundEffect
from openai import AsyncOpenAI  # type: ignore[reportMissingTypeStubs]

logger = logging.getLogger(__name__)

class TTSManager(QObject):
    """Generate WAV via OpenAI TTS and play it."""

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        key = settings.get("openai_api_key", "")
        self.client = AsyncOpenAI(api_key=key) if key else None
        self._current: Optional[QSoundEffect] = None

    # ───────────────────────────────────────────
    async def speak(self, text: str):
        if not self.client or not self.settings.get("tts_enabled", False):
            return
        voice = self.settings.get("tts_voice", "alloy")
        try:
            rsp = await self.client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
                format="wav",
                stream=False,
            )
            data = await rsp.read()
            fd, path = tempfile.mkstemp(suffix=".wav", prefix="hcai_tts_")
            os.write(fd, data)
            os.close(fd)
            self._play(path)
            Path(path).unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            logger.error("TTS failure: %s", exc)

    # ───────────────────────────────────────────
    def _play(self, wav_path: str):
        if self._current and self._current.isPlaying():
            self._current.stop()
        fx = QSoundEffect()
        fx.setSource(QUrl.fromLocalFile(wav_path))
        fx.setVolume(float(self.settings.get("tts_volume", 1.0)))
        fx.setLoopCount(1)
        fx.play()
        self._current = fx