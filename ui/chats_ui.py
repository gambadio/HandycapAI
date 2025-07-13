"""
Main chat-window: history list + live conversation pane +
handles both streaming and realtime transports.
"""
from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from llm.tools import SecureFunctionExecutor
from storage import ChatStorage
from ui.chat_interface import ChatInterface
from ui.quick_settings import QuickSettingsBar
from voice.tts import TTSManager

logger = logging.getLogger(__name__)

class ChatsWindow(QWidget):
    """Main window for all chats."""

    def __init__(self, settings, voice_mgr, tts_mgr: TTSManager, chat_tx, realtime_tx):
        super().__init__()
        self.setWindowTitle("HandycapAI Chats")
        self.setMinimumSize(900, 640)

        self.settings = settings
        self.voice_mgr = voice_mgr
        self.tts_mgr = tts_mgr
        self.chat_tx = chat_tx
        self.rt_basic = realtime_tx  # always exists
        self.rt_adv = None  # lazy

        self.storage = ChatStorage()
        self.func_exec = SecureFunctionExecutor(settings)
        self.current_chat: int | None = None

        # ───── UI ─────
        v = QVBoxLayout(self)
        self.quick = QuickSettingsBar(settings)
        v.addWidget(self.quick)

        self.hist_list = QListWidget()
        self.hist_list.itemClicked.connect(self._select_chat)
        v.addWidget(self.hist_list, 1)

        new_btn = QPushButton("New chat")
        new_btn.clicked.connect(self._new_chat)
        v.addWidget(new_btn)

        self.chat_ui = ChatInterface()
        v.addWidget(self.chat_ui, 3)

        self.status_lbl = QLabel("Idle")
        v.addWidget(self.status_lbl)

        # Signals
        self.chat_ui.text_entered.connect(self._incoming_user_text)
        self.chat_ui.voice_requested.connect(voice_mgr.start_listening)
        voice_mgr.text_recognized.connect(self._incoming_user_text)
        voice_mgr.state_changed.connect(self.status_lbl.setText)

        self.quick.settings_changed.connect(self._refresh_realtime_mode)

        self._load_history()
        self._refresh_realtime_mode()

    # ───────────────────────────────────────────
    def _load_history(self):
        self.hist_list.clear()
        for c in self.storage.get_all_chats():
            self.hist_list.addItem(f"{c['id']}: {c['title']}")

    def _select_chat(self, item):
        cid = int(item.text().split(":")[0])
        self._load_chat(cid)

    def _new_chat(self):
        self.current_chat = self.storage.create_chat()
        self.chat_ui.clear()
        self.storage.update_chat_title(self.current_chat, "")
        logger.info("Started chat %s", self.current_chat)

    def _load_chat(self, cid: int):
        self.current_chat = cid
        msgs = self.storage.get_messages(cid, limit=int(self.settings.get("max_context_length", 10)))
        self.chat_ui.clear()
        for m in msgs:
            self.chat_ui.chat_area.add_bubble(m["content"], m["role"] == "user")

    # ───────────────────────────────────────────
    def _current_rt(self):
        if self.settings.get("realtime_basic_mode", True):
            return self.rt_basic
        if not self.rt_adv:
            from llm.realtime_manager import RealtimeManager

            self.rt_adv = RealtimeManager(self.settings)
            self.rt_adv.text_received.connect(lambda t: self._finish_assistant_reply(t, False))
            self.rt_adv.transcript_received.connect(
                lambda t: self._finish_assistant_reply(t, False)
            )
        return self.rt_adv

    def _refresh_realtime_mode(self):
        # Disconnect adv if user flipped to basic
        if self.rt_adv and self.settings.get("realtime_basic_mode", True):
            asyncio.create_task(self.rt_adv.disconnect())

    # ───────────────────────────────────────────
    @Slot(str)
    def _incoming_user_text(self, text: str):
        if not text.strip():
            return
        if not self.current_chat:
            self._new_chat()

        self.storage.add_message(self.current_chat, "user", text)
        self.chat_ui.chat_area.add_bubble(text, True)
        asyncio.create_task(self._ask_assistant(text))

    # ───────────────────────────────────────────
    async def _ask_assistant(self, user_text: str):
        try:
            self.status_lbl.setText("Processing…")

            history = self.storage.get_messages(
                self.current_chat, limit=int(self.settings.get("max_context_length", 10))
            )
            msgs = [{"role": m["role"], "content": m["content"]} for m in history]

            mode = self.settings.get("api_mode", "stream")
            if mode == "stream":
                reply = await self.chat_tx.chat(msgs)
                await self._finish_assistant_reply(reply)
            else:
                # realtime
                if self.settings.get("realtime_basic_mode", True):
                    reply = await self.rt_basic.chat(msgs)
                    await self._finish_assistant_reply(reply)
                else:
                    rt = self._current_rt()
                    await rt.connect()
                    await rt.send_text(user_text)
                    # reply handled via signal
        except Exception as exc:  # noqa: BLE001
            logger.exception("Assistant failure")
            QMessageBox.warning(self, "LLM error", str(exc))
        finally:
            self.status_lbl.setText("Idle")

    async def _finish_assistant_reply(self, reply: str, do_tts: bool = True):
        if isinstance(reply, dict) and "function_call" in reply:
            reply = await self.func_exec.execute(reply["function_call"])

        self.storage.add_message(self.current_chat, "assistant", reply)
        self.chat_ui.chat_area.add_bubble(reply, False)

        if self.settings.get("tts_enabled", False) and do_tts:
            asyncio.create_task(self.tts_mgr.speak(reply))

    # ───────────────────────────────────────────
    def closeEvent(self, ev):
        # Ensure advanced realtime WS closed
        if self.rt_adv:
            asyncio.create_task(self.rt_adv.disconnect())
        super().closeEvent(ev)