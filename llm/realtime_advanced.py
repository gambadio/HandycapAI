"""
Advanced Realtime API session:
• text + audio
• function-calling
• interrupt / cancel
• voice selection and VAD parameters
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from openai import AsyncOpenAI  # type: ignore[reportMissingTypeStubs]

logger = logging.getLogger(__name__)

class AdvancedRealtimeSession:
    """Full-featured Realtime session living for the entire chat window."""

    # Callbacks assigned by RealtimeManager
    on_text_delta: Optional[Callable[[str, bool], None]] = None
    on_audio_delta: Optional[Callable[[bytes, bool], None]] = None
    on_transcript: Optional[Callable[[str, bool], None]] = None
    on_function_call: Optional[Callable[[Dict[str, Any]], None]] = None
    on_error: Optional[Callable[[str], None]] = None
    on_state: Optional[Callable[[str], None]] = None

    def __init__(self, settings):
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.get("openai_api_key", ""))
        self.conn = None
        self.modalities: list[str] = settings.get("realtime_modalities", ["text", "audio"])
        self.voice: str = settings.get("realtime_voice", "alloy")
        self.instructions: str = settings.get("realtime_instructions", "")
        self.temperature: float = float(settings.get("realtime_temperature", 0.8))

    # ───────────────────────────────────────────
    async def connect(self):
        self._emit_state("connecting")
        self.conn = await self.client.beta.realtime.connect(model="gpt-4o-realtime-preview")
        await self.conn.session.update(
            session={
                "modalities": self.modalities,
                "voice": self.voice,
                "instructions": self.instructions,
                "temperature": self.temperature,
            }
        )
        asyncio.create_task(self._event_loop())
        self._emit_state("connected")
        logger.info("Advanced Realtime WS connected")

    # ───────────────────────────────────────────
    async def _event_loop(self):
        try:
            async for ev in self.conn:
                t = ev.type

                if t == "response.text.delta":
                    self._emit_text(ev.delta, False)

                elif t == "response.text.done":
                    self._emit_text(ev.text, True)

                elif t == "response.audio.delta":
                    self._emit_audio(base64.b64decode(ev.delta), False)

                elif t == "response.audio.done":
                    self._emit_audio(b"", True)

                elif t == "response.audio.transcript.delta":
                    self._emit_transcript(ev.delta, False)

                elif t == "response.audio.transcript.done":
                    self._emit_transcript(ev.transcript, True)

                elif t == "response.function_call.arguments.done":
                    if self.on_function_call:
                        self.on_function_call({"name": ev.name, "arguments": ev.arguments})

                elif t == "response.done":
                    self._emit_state("idle")

                elif t == "error":
                    raise RuntimeError(ev.error.message)
        except Exception as exc:  # noqa: BLE001
            self._emit_error(str(exc))

    # ───────────────────────────────────────────
    async def send_text(self, text: str):
        if not self.conn:
            raise RuntimeError("Realtime not connected")
        self._emit_state("processing")
        await self.conn.conversation.item.create(
            item={
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            }
        )
        await self.conn.response.create()

    async def send_audio_chunk(self, chunk: bytes):
        if not self.conn:
            return
        await self.conn.input_audio_buffer.append(audio=base64.b64encode(chunk).decode())
        await self.conn.input_audio_buffer.commit()

    async def interrupt(self):
        if self.conn:
            await self.conn.response.cancel()

    async def disconnect(self):
        if self.conn and not self.conn.closed:
            await self.conn.close()
        self._emit_state("disconnected")

    # ───────────────────────────────────────────
    # tiny helpers
    def _emit_text(self, txt: str, done: bool):
        if self.on_text_delta:
            asyncio.get_event_loop().call_soon_threadsafe(self.on_text_delta, txt, done)

    def _emit_audio(self, data: bytes, done: bool):
        if self.on_audio_delta:
            asyncio.get_event_loop().call_soon_threadsafe(self.on_audio_delta, data, done)

    def _emit_transcript(self, txt: str, done: bool):
        if self.on_transcript:
            asyncio.get_event_loop().call_soon_threadsafe(self.on_transcript, txt, done)

    def _emit_error(self, msg: str):
        if self.on_error:
            asyncio.get_event_loop().call_soon_threadsafe(self.on_error, msg)
        self._emit_state("error")

    def _emit_state(self, st: str):
        if self.on_state:
            asyncio.get_event_loop().call_soon_threadsafe(self.on_state, st)