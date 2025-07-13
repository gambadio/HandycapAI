"""
Qt widget showing live audio-level, transcript and controls
for AdvancedRealtimeSession.
"""
from __future__ import annotations

import asyncio

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from llm.realtime_manager import RealtimeManager
from voice.realtime_audio import RealtimeAudioIO

class _Level(QWidget):
    def __init__(self):
        super().__init__()
        self.level = 0.0
        self.setFixedHeight(12)

    def set_level(self, v: float):
        self.level = v
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        bar = self.rect().adjusted(0, 0, int(self.width() * self.level) - self.width(), 0)
        color = QColor(0, 200, 0) if self.level < 0.7 else QColor(200, 50, 0)
        p.fillRect(bar, color)

class RealtimeWidget(QWidget):
    """Visible only in advanced mode."""

    def __init__(self, mgr: RealtimeManager):
        super().__init__()
        self.mgr = mgr
        v = QVBoxLayout(self)

        # Status line
        h = QHBoxLayout()
        self.state_lbl = QLabel("…")
        h.addWidget(self.state_lbl)
        h.addStretch()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_conn)
        self.cancel_btn = QPushButton("Interrupt")
        self.cancel_btn.clicked.connect(lambda: asyncio.create_task(self.mgr.interrupt()))
        self.cancel_btn.setEnabled(False)
        h.addWidget(self.connect_btn)
        h.addWidget(self.cancel_btn)
        v.addLayout(h)

        # Level meter
        self.level = _Level()
        v.addWidget(self.level)

        # Transcript
        self.tr = QTextEdit()
        self.tr.setReadOnly(True)
        v.addWidget(self.tr, 1)

        # Wire signals
        self.mgr.state_changed.connect(self._on_state)
        self.mgr.transcript_received.connect(self._append_tr)
        self.mgr.text_received.connect(self._append_tr)
        self.mgr.error_occurred.connect(self._append_tr)
        self.mgr.audio_io.level_changed.connect(self.level.set_level)

    # ───────────────────────────────────────────
    @Slot()
    def _toggle_conn(self):
        if self.connect_btn.text() == "Connect":
            asyncio.create_task(self.mgr.connect())
        else:
            asyncio.create_task(self.mgr.disconnect())

    @Slot(str)
    def _on_state(self, st: str):
        self.state_lbl.setText(st)
        if st == "connected":
            self.connect_btn.setText("Disconnect")
            self.cancel_btn.setEnabled(True)
        elif st in ("disconnected", "error"):
            self.connect_btn.setText("Connect")
            self.cancel_btn.setEnabled(False)

    @Slot(str)
    def _append_tr(self, txt: str):
        self.tr.append(txt)