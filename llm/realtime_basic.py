"""
Basic text-only Realtime API transport.

This keeps the original lightweight behaviour for users that
don’t need advanced audio / function-calling support.
"""
from __future__ import annotations

import logging
from typing import List

from openai import AsyncOpenAI  # type: ignore[reportMissingTypeStubs]

logger = logging.getLogger(__name__)

class RealtimeTransport:
    """Minimal wrapper around /beta/realtime — text only."""

    def __init__(self, settings):
        self.settings = settings
        key = settings.get("openai_api_key", "")
        self.client: AsyncOpenAI | None = AsyncOpenAI(api_key=key) if key else None

    # ───────────────────────────────────────────
    async def chat(self, messages: List[dict]) -> str:
        if not self.client:
            raise RuntimeError("OpenAI key missing")

        async with self.client.beta.realtime.connect(
            model="gpt-4o-realtime-preview"
        ) as conn:
            await conn.session.update(session={"modalities": ["text"]})

            # Push last five messages for context
            for msg in messages[-5:]:
                await conn.conversation.item.create(
                    item={
                        "type": "message",
                        "role": msg["role"],
                        "content": [{"type": "input_text", "text": msg["content"]}],
                    }
                )

            await conn.response.create()

            ret = ""
            async for ev in conn:
                if ev.type == "response.text.delta":
                    ret += ev.delta
                elif ev.type in ("response.text.done", "response.done"):
                    break
                elif ev.type == "error":
                    raise RuntimeError(ev.error.message)
            return ret.strip()