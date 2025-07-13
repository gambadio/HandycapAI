"""
Speech-to-text manager (local Whisper or cloud).
"""
import asyncio
import io
import logging

import numpy as np
import speech_recognition as sr
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class STTManager(QObject):
    error_occurred = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.recognizer = sr.Recognizer()
        self.local_model = None

        if settings.get("stt_source", "local") == "local":
            self._init_local()

    # ─────────────────────
    def _init_local(self):
        try:
            from faster_whisper import WhisperModel

            self.local_model = WhisperModel("medium", device="auto", compute_type="float16")
            logger.info("Local Whisper ready")
        except Exception as exc:
            logger.warning("Local Whisper init failed – fallback to cloud: %s", exc)
            self.settings.set("stt_source", "cloud")

    # ─────────────────────
    async def record(self, timeout: int = 10):
        try:
            with sr.Microphone() as src:
                logger.info("Listening…")
                self.recognizer.adjust_for_ambient_noise(src, duration=0.5)
                audio = self.recognizer.listen(src, timeout=timeout, phrase_time_limit=10)

            audio_np = np.frombuffer(audio.get_raw_data(), np.int16).astype(np.float32) / 32768.0
            return audio, audio_np
        except sr.WaitTimeoutError:
            raise Exception("No speech detected")
        except Exception as exc:
            raise Exception(f"Audio capture error: {exc}") from exc

    async def transcribe(self, audio, audio_np):
        src = self.settings.get("stt_source", "local")
        try:
            if src == "local" and self.local_model:
                return await self._transcribe_local(audio_np)
            return await self._transcribe_cloud(audio)
        except Exception as exc:
            if src == "local":
                logger.info("Local STT failed, switching to cloud")
                self.settings.set("stt_source", "cloud")
                return await self._transcribe_cloud(audio)
            raise

    # ─────────────────────
    async def _transcribe_local(self, audio_np):
        segments, _ = self.local_model.transcribe(audio_np, beam_size=5)
        return " ".join(s.text for s in segments).strip()

    async def _transcribe_cloud(self, audio):
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.settings.get("openai_api_key", ""))
        audio_file = io.BytesIO(audio.get_wav_data())
        audio_file.name = "audio.wav"

        rsp = await client.audio.transcriptions.create(model="whisper-1", file=audio_file)
        return rsp.text.strip()