"""
Lightweight chat bubbles + input bar.
"""
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QLabel
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics

logger = logging.getLogger(__name__)


class ChatBubble(QWidget):
    def __init__(self, text: str, is_user: bool):
        super().__init__()
        self.text = text
        self.is_user = is_user
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.font = QFont("Arial", 11)
        self.pad = 12
        self.radius = 12
        self.margin = 20

        fm = QFontMetrics(self.font)
        txt_w = min(fm.horizontalAdvance(text), 400)
        txt_h = fm.boundingRect(0, 0, txt_w, 0, Qt.TextWordWrap, text).height()
        self.setMinimumHeight(txt_h + self.pad * 2 + 20)

    # ─────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        bubble_w = min(rect.width() - self.margin * 2, 400)
        bubble_h = rect.height() - self.pad

        if self.is_user:
            bubble_rect = rect.adjusted(
                rect.width() - bubble_w - self.margin,
                self.pad // 2,
                -self.margin,
                -self.pad // 2,
            )
            color = QColor("#DCF8C6")
        else:
            bubble_rect = rect.adjusted(
                self.margin,
                self.pad // 2,
                -(rect.width() - bubble_w - self.margin),
                -self.pad // 2,
            )
            color = QColor("#E5E5EA")

        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(bubble_rect, self.radius, self.radius)

        p.setPen(Qt.black)
        p.setFont(self.font)
        txt_rect = bubble_rect.adjusted(10, 6, -10, -6)
        p.drawText(txt_rect, Qt.TextWordWrap | Qt.TextWrapAnywhere, self.text)


class ChatArea(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.v_layout = QVBoxLayout(self.container)
        self.v_layout.setAlignment(Qt.AlignTop)
        self.v_layout.setSpacing(10)
        self.setWidget(self.container)

    def add_bubble(self, text: str, is_user: bool):
        bubble = ChatBubble(text, is_user)
        self.v_layout.addWidget(bubble)
        QTimer.singleShot(50, lambda: self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()
        ))

    def clear(self):
        while self.v_layout.count():
            child = self.v_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()


class ChatInputBar(QWidget):
    send_text = Signal(str)
    send_voice = Signal()

    def __init__(self):
        super().__init__()
        h = QHBoxLayout(self)
        h.setSpacing(10)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type your message…")
        self.input.returnPressed.connect(self._emit)

        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._emit)

        mic_btn = QPushButton("🎤")
        mic_btn.setFixedSize(40, 32)
        mic_btn.clicked.connect(lambda: self.send_voice.emit())

        h.addWidget(self.input, 1)
        h.addWidget(send_btn)
        h.addWidget(mic_btn)

    def _emit(self):
        txt = self.input.text().strip()
        if txt:
            self.send_text.emit(txt)
            self.input.clear()


class ChatInterface(QWidget):
    text_entered = Signal(str)
    voice_requested = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        self.chat_area = ChatArea()
        self.input_bar = ChatInputBar()
        v.addWidget(self.chat_area, 1)
        v.addWidget(self.input_bar, 0)

        # Wire
        self.input_bar.send_text.connect(self.text_entered.emit)
        self.input_bar.send_voice.connect(self.voice_requested.emit)

    def clear(self):
        self.chat_area.clear()