"""
OpenAI Chat-Completions (streaming) transport with robust error handling.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from openai import (  # type: ignore[reportMissingTypeStubs]
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    OpenAIError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

class ChatCompletionsTransport:
    """Wrapper around /v1/chat/completions streaming endpoint."""

    def __init__(self, settings):
        self.settings = settings
        self.__client: AsyncOpenAI | None = None

    # ───────────────────────────────────────────
    def _get_client(self) -> AsyncOpenAI:
        if self.__client is None:
            key = self.settings.get("openai_api_key", "")
            if not key:
                raise RuntimeError("OpenAI API key is missing.")
            self.__client = AsyncOpenAI(api_key=key)
        return self.__client

    # ───────────────────────────────────────────
    def _build_tools(self) -> List[Dict[str, Any]]:
        try:
            funcs = json.loads(self.settings.get("functions_json", "[]"))
            out = []
            for f in funcs:
                out.append(
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
                )
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tool schema build failed: %s", exc)
            return []

    # ───────────────────────────────────────────
    async def chat(self, messages: List[Dict[str, Any]]) -> str | Dict[str, Any]:
        """
        Stream the assistant response and return either the final
        string or the first tool-call object.
        """
        client = self._get_client()
        tools = self._build_tools()

        try:
            stream = await client.with_options(max_retries=2).chat.completions.create(
                model=self.settings.get("model", "gpt-4o"),
                messages=messages,
                temperature=float(self.settings.get("temperature", 0.7)),
                tools=tools or None,
                tool_choice="auto" if tools else None,
                stream=True,
            )

            text_parts: list[str] = []
            tool_calls: list[Dict[str, Any]] = []

            async for ev in stream:
                delta = ev.choices[0].delta
                if delta.content:
                    text_parts.append(delta.content)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.function:
                            tool_calls.append(
                                {"name": tc.function.name, "arguments": tc.function.arguments}
                            )

            return {"function_call": tool_calls[0]} if tool_calls else "".join(text_parts).strip()

        except (APIConnectionError, RateLimitError) as exc:
            logger.warning("Transient OpenAI error: %s", exc)
            raise RuntimeError("Temporary network / rate-limit issue. Please retry.") from exc
        except APIStatusError as exc:
            logger.error("OpenAI returned %s", exc.status_code)
            raise RuntimeError(f"OpenAI error {exc.status_code}: {exc.message}") from exc
        except (OpenAIError, Exception) as exc:  # noqa: BLE001
            logger.exception("LLM stream failed")
            raise RuntimeError("LLM stream failed. Please retry.") from exc