"""
Low-latency microphone capture + speaker playback for AdvancedRealtimeSession.
Uses PyAudio + WebRTC VAD for speech detection.
"""
from __future__ import annotations

import asyncio
import logging
import struct
import wave
from collections import deque
from typing import Optional

import numpy as np
import pyaudio  # type: ignore
import webrtcvad  # type: ignore
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

class RealtimeAudioIO(QObject):
    """Bi-directional 24 kHz mono 16-bit audio."""

    level_changed = Signal(float)

    SAMPLE_RATE = 24_000
    CHUNK = 480  # 20 ms
    FORMAT = pyaudio.paInt16
    CHANNELS = 1

    def __init__(self, parent):
        super().__init__(parent)
        self.parent_mgr = parent
        self.p = pyaudio.PyAudio()
        self.vad = webrtcvad.Vad(2)
        self.input_stream = None
        self.output_stream = None
        self.tx_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.play_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._worker: Optional[asyncio.Task] = None

    # ───────────────────────────────────────────
    async def start(self):
        self.input_stream = self.p.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.SAMPLE_RATE,
            input=True,
            frames_per_buffer=self.CHUNK,
            stream_callback=self._record_cb,
        )
        self.output_stream = self.p.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.SAMPLE_RATE,
            output=True,
            frames_per_buffer=self.CHUNK,
            stream_callback=self._play_cb,
        )
        self._worker = asyncio.create_task(self._tx_loop())

    async def stop(self):
        if self._worker:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
        self.p.terminate()

    # ───────────────────────────────────────────
    async def play_output(self, data: bytes):
        await self.play_queue.put(data)

    # ───────────────────────────────────────────
    # stream callbacks  (run in audio thread)
    def _record_cb(self, in_data, frame_count, *_):
        try:
            if self.vad.is_speech(in_data, self.SAMPLE_RATE):
                # Enqueue for network send
                asyncio.get_event_loop().call_soon_threadsafe(
                    self.tx_queue.put_nowait, in_data
                )
            # level meter
            audio_np = np.frombuffer(in_data, np.int16)
            level = float(np.abs(audio_np).mean()) / 32768.0
            self.level_changed.emit(level)
        except Exception:
            pass
        return (None, pyaudio.paContinue)

    def _play_cb(self, *_):
        try:
            data = self.play_queue.get_nowait()
        except asyncio.QueueEmpty:
            data = b"\x00" * self.CHUNK * 2
        return (data, pyaudio.paContinue)

    # ───────────────────────────────────────────
    async def _tx_loop(self):
        """Forward mic chunks to session."""
        while True:
            chunk = await self.tx_queue.get()
            await self.parent_mgr.session.send_audio_chunk(chunk)