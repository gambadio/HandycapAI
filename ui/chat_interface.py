"""
Light-weight chat area:

• ChatBubble – draws user / assistant bubbles
• ChatArea   – scroll-area that stores bubbles and lets us update the last
               bubble while streaming (update_last_bubble)
• ChatInputBar – line-edit + Send and Mic buttons
• ChatInterface – wraps ChatArea + ChatInputBar and re-emits signals:
        • text_entered(str)
        • voice_requested()
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
class ChatBubble(QWidget):
    """Single rounded speech bubble."""

    def __init__(self, text: str, is_user: bool):
        super().__init__()
        self.text = text
        self.is_user = is_user

        self.font = QFont("Arial", 11)
        self.fm = QFontMetrics(self.font)

        # Constants
        self.pad = 12
        self.radius = 12
        self.margin = 20

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._recalc_size()

    # --------------------------------------------
    def _recalc_size(self):
        """Pre-compute height to avoid heavy work inside paintEvent."""
        max_w = 400
        text_rect = self.fm.boundingRect(
            0, 0, max_w, 0, Qt.TextWordWrap | Qt.TextWrapAnywhere, self.text
        )
        self.setMinimumHeight(text_rect.height() + self.pad * 2 + 20)

    def update_text(self, new_text: str):
        """Replace bubble content (used while streaming)"""
        self.text = new_text
        self._recalc_size()
        self.update()

    # --------------------------------------------
    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        bubble_w = min(rect.width() - self.margin * 2, 400)

        # Where to place the bubble?
        if self.is_user:
            bubble_rect = rect.adjusted(
                rect.width() - bubble_w - self.margin,
                self.pad // 2,
                -self.margin,
                -self.pad // 2,
            )
            fill = QColor("#DCF8C6")
        else:
            bubble_rect = rect.adjusted(
                self.margin,
                self.pad // 2,
                -(rect.width() - bubble_w - self.margin),
                -self.pad // 2,
            )
            fill = QColor("#E5E5EA")

        # Draw background
        p.setBrush(fill)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(bubble_rect, self.radius, self.radius)

        # Draw text
        p.setPen(Qt.black)
        p.setFont(self.font)
        txt_rect = bubble_rect.adjusted(10, 6, -10, -6)
        p.drawText(txt_rect, Qt.TextWordWrap | Qt.TextWrapAnywhere, self.text)

# ────────────────────────────────────────────────
class ChatArea(QScrollArea):
    """Scrollable container for chat bubbles."""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.container = QWidget(self)
        self.v_layout = QVBoxLayout(self.container)
        self.v_layout.setAlignment(Qt.AlignTop)
        self.v_layout.setSpacing(10)
        self.setWidget(self.container)

    # --------------------------------------------
    def add_bubble(self, text: str, is_user: bool) -> ChatBubble:
        bubble = ChatBubble(text, is_user)
        self.v_layout.addWidget(bubble)

        # Auto-scroll to bottom
        QTimer.singleShot(
            50,
            lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()),
        )
        return bubble

    def update_last_bubble(self, new_text: str):
        """Replace text of the most recently added bubble."""
        if self.v_layout.count() == 0:
            return
        item = self.v_layout.itemAt(self.v_layout.count() - 1)
        bubble: ChatBubble = item.widget()  # type: ignore[assignment]
        bubble.update_text(new_text)

    def clear(self):
        while self.v_layout.count():
            child = self.v_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

# ────────────────────────────────────────────────
class ChatInputBar(QWidget):
    """Line-edit + buttons."""

    send_text = Signal(str)
    send_voice = Signal()

    def __init__(self):
        super().__init__()
        h = QHBoxLayout(self)
        h.setSpacing(10)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type your message…")
        self.input.returnPressed.connect(self._emit)
        h.addWidget(self.input, 1)

        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._emit)
        h.addWidget(send_btn)

        mic_btn = QPushButton("🎤")
        mic_btn.setFixedSize(40, 32)
        mic_btn.clicked.connect(lambda: self.send_voice.emit())
        h.addWidget(mic_btn)

    # --------------------------------------------
    def _emit(self):
        txt = self.input.text().strip()
        if txt:
            self.send_text.emit(txt)
            self.input.clear()

# ────────────────────────────────────────────────
class ChatInterface(QWidget):
    """
    Combines ChatArea and ChatInputBar.
    Exposes:
        • text_entered(str)
        • voice_requested()
    """

    text_entered = Signal(str)
    voice_requested = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)

        self.chat_area = ChatArea()
        self.input_bar = ChatInputBar()

        v.addWidget(self.chat_area, 1)
        v.addWidget(self.input_bar, 0)

        # Re-emit signals
        self.input_bar.send_text.connect(self.text_entered.emit)
        self.input_bar.send_voice.connect(self.voice_requested.emit)

    # --------------------------------------------
    def clear(self):
        self.chat_area.clear()