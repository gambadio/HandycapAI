"""
OpenAI Realtime-API transport (beta).
"""
import logging
from typing import List

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class RealtimeTransport:
    def __init__(self, settings):
        self.settings = settings
        key = settings.get("openai_api_key", "")
        self.client = AsyncOpenAI(api_key=key) if key else None

    async def chat(self, messages: List[dict]) -> str:
        if not self.client:
            raise RuntimeError("OpenAI key missing")

        async with self.client.beta.realtime.connect(model="gpt-4o-realtime-preview") as conn:
            # Configure text-only
            await conn.session.update(session={"modalities": ["text"]})

            # Last user message only
            await conn.conversation.item.create(
                item={
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": messages[-1]["content"]}],
                }
            )
            await conn.response.create()

            ret = ""
            async for ev in conn:
                if ev.type == "response.text.delta":
                    ret += ev.delta
                elif ev.type == "response.text.done":
                    break
                elif ev.type == "error":
                    raise RuntimeError(ev.error.message)
            return ret.strip()