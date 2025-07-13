"""
OpenAI Chat-Completions (streaming) transport
with robust error handling.
"""

from __future__ import annotations

import json
import logging
from typing import List

from openai import AsyncOpenAI, OpenAIError

logger = logging.getLogger(__name__)

class ChatCompletionsTransport:
    def __init__(self, settings):
        self.settings = settings
        self._client: AsyncOpenAI | None = None

    # ─────────────────────
    def _client(self) -> AsyncOpenAI:
        if self._client is None:
            key = self.settings.get("openai_api_key", "")
            if not key:
                raise RuntimeError("OpenAI API key is missing.")
            self._client = AsyncOpenAI(api_key=key)
        return self._client

    def _build_tools(self):
        try:
            funcs = json.loads(self.settings.get("functions_json", "[]"))
            return [
                {
                    "type": "function",
                    "function": {
                        "name": f["name"],
                        "description": f.get("description", ""),
                        "parameters": f.get(
                            "parameters", {"type": "object", "properties": {}, "required": []}
                        ),
                    },
                }
                for f in funcs
            ]
        except Exception as exc:
            logger.warning("Failed to build tool schema: %s", exc)
            return []

    # ─────────────────────
    async def chat(self, messages: List[dict]):
        client = self._client()
        tools = self._build_tools()

        try:
            async with client.chat.completions.stream(
                model=self.settings.get("model", "gpt-4o"),
                messages=messages,
                temperature=0.7,
                tools=tools or None,
                tool_choice="auto" if tools else None,
            ) as stream:
                content = ""
                func_calls = []

                async for ev in stream:
                    delta = ev.choices[0].delta
                    if delta.content:
                        content += delta.content
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            if tc.function:
                                func_calls.append(
                                    {"name": tc.function.name, "arguments": tc.function.arguments}
                                )

            return {"function_call": func_calls[0]} if func_calls else content.strip()

        except (OpenAIError, Exception) as exc:
            logger.error("LLM stream failed: %s", exc)
            raise RuntimeError("LLM stream failed, please retry.") from exc