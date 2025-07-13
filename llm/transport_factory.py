"""
Factory helpers that decide which transport implementation to
instantiate based on current Settings.
"""
from __future__ import annotations

import logging

from llm.chat import ChatCompletionsTransport
from llm.realtime_basic import RealtimeTransport
from llm.realtime_manager import RealtimeManager

logger = logging.getLogger(__name__)

class TransportFactory:
    """Static helpers."""

    @staticmethod
    def create_chat_transport(settings) -> ChatCompletionsTransport:
        return ChatCompletionsTransport(settings)

    @staticmethod
    def create_realtime_transport(settings):
        use_basic = settings.get("realtime_basic_mode", True)
        if use_basic:
            logger.info("Realtime: basic implementation selected")
            return RealtimeTransport(settings)
        logger.info("Realtime: advanced implementation selected")
        return RealtimeManager(settings)