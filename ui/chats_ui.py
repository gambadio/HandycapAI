import asyncio
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QPushButton, QLabel, QMessageBox
)
from PySide6.QtCore import Qt
from ui.chat_interface import ChatInterface
from storage import ChatStorage
from llm.tools import FunctionExecutor

logger = logging.getLogger(__name__)


class ChatsWindow(QWidget):
    """Main chat history window + live conversation pane."""

    def __init__(self, settings, voice, chat_transport, realtime_transport):
        super().__init__()
        self.setWindowTitle("HandycapAI Chats")
        self.setMinimumSize(800, 600)

        self.settings = settings
        self.voice = voice
        self.chat_transport = chat_transport
        self.realtime_transport = realtime_transport

        self.storage = ChatStorage()
        self.current_chat: int | None = None
        self.function_exec = FunctionExecutor(settings)

        # UI layout
        v = QVBoxLayout(self)

        self.hist_list = QListWidget()
        self.hist_list.itemClicked.connect(self._select_chat)
        v.addWidget(self.hist_list)

        new_btn = QPushButton("New chat")
        new_btn.clicked.connect(self._new_chat)
        v.addWidget(new_btn)

        self.chat_ui = ChatInterface()
        v.addWidget(self.chat_ui)

        self.status_lbl = QLabel("Idle")
        v.addWidget(self.status_lbl)

        # Wire signals
        self.chat_ui.text_entered.connect(self._on_user_text)
        self.chat_ui.voice_requested.connect(voice.start_listening)
        voice.text_recognized.connect(self._on_user_text)
        voice.state_changed.connect(self.status_lbl.setText)
        voice.error_occurred.connect(lambda e: QMessageBox.warning(self, "Voice error", e))

        self._load_history()

    # ─────────────────────
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
        logger.info("Started new chat %s", self.current_chat)

    def _load_chat(self, cid: int):
        self.current_chat = cid
        msgs = self.storage.get_messages(cid, limit=int(self.settings.get("max_context_length", 10)))
        self.chat_ui.clear()
        for m in msgs:
            self.chat_ui.chat_area.add_bubble(m["content"], m["role"] == "user")

    # ─────────────────────
    def _on_user_text(self, text: str):
        if not text.strip():
            return
        if not self.current_chat:
            self._new_chat()

        # Persistence + UI
        self.storage.add_message(self.current_chat, "user", text)
        self.chat_ui.chat_area.add_bubble(text, True)

        asyncio.create_task(self._ask_llm(text))

    async def _ask_llm(self, text: str):
        try:
            self.status_lbl.setText("Processing…")

            # Build context
            history = self.storage.get_messages(
                self.current_chat,
                limit=int(self.settings.get("max_context_length", 10)),
            )
            msgs = [{"role": m["role"], "content": m["content"]} for m in history]

            # Transport
            mode = self.settings.get("api_mode", "stream")
            reply = await (
                self.realtime_transport.chat(msgs)
                if mode == "realtime"
                else self.chat_transport.chat(msgs)
            )

            # Function call?
            if isinstance(reply, dict) and "function_call" in reply:
                reply = await self.function_exec.execute(reply["function_call"])

            # Display
            self.storage.add_message(self.current_chat, "assistant", reply)
            self.chat_ui.chat_area.add_bubble(reply, False)

            # Auto title
            if len(history) <= 2:
                title = text[:50] + ("…" if len(text) > 50 else "")
                self.storage.update_chat_title(self.current_chat, title)
                self._load_history()

        except Exception as exc:
            logger.exception("LLM failure")
            QMessageBox.warning(self, "LLM error", str(exc))
        finally:
            self.status_lbl.setText("Idle")