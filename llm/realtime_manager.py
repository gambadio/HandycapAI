"""
High-level manager that wraps AdvancedRealtimeSession and connects it
to audio capture / playback (voice.realtime_audio) plus SecureFunctionExecutor.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from PySide6.QtCore import QObject, Signal

from llm.realtime_advanced import AdvancedRealtimeSession
from llm.tools import SecureFunctionExecutor
from voice.realtime_audio import RealtimeAudioIO

logger = logging.getLogger(__name__)

class RealtimeManager(QObject):
    """Exposes a Qt-friendly API identical to the basic transport."""

    text_received = Signal(str)
    transcript_received = Signal(str)
    audio_received = Signal(bytes)
    state_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.session = AdvancedRealtimeSession(settings)
        self.audio_io = RealtimeAudioIO(self)
        self.func_exec = SecureFunctionExecutor(settings)

        # Wire session callbacks
        self.session.on_text_delta = self._on_text
        self.session.on_transcript = self._on_transcript
        self.session.on_audio_delta = self._on_audio
        self.session.on_state = self.state_changed.emit
        self.session.on_error = self.error_occurred.emit
        self.session.on_function_call = lambda call: asyncio.create_task(
            self._handle_function(call)
        )

        self._connect_lock = asyncio.Lock()

    # ───────────────────────────────────────────
    async def connect(self):
        async with self._connect_lock:
            await self.session.connect()
            await self.audio_io.start()

    async def disconnect(self):
        async with self._connect_lock:
            await self.audio_io.stop()
            await self.session.disconnect()

    # ───────────────────────────────────────────
    async def send_text(self, text: str):
        await self.session.send_text(text)

    async def interrupt(self):
        await self.session.interrupt()

    # ───────────────────────────────────────────
    # callbacks
    def _on_text(self, delta: str, done: bool):
        if done:
            self.text_received.emit(delta)

    def _on_transcript(self, tr: str, done: bool):
        if done:
            self.transcript_received.emit(tr)

    def _on_audio(self, data: bytes, done: bool):
        if data:
            self.audio_received.emit(data)
            asyncio.create_task(self.audio_io.play_output(data))

    async def _handle_function(self, call: Dict):
        result = await self.func_exec.execute(call)
        await self.session.send_text(result)