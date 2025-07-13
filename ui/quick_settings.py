"""
A tiny bar with check-boxes to flip between streaming / realtime
and basic / advanced realtime without opening the full settings window.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QWidget

class QuickSettingsBar(QWidget):
    settings_changed = Signal()

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        h = QHBoxLayout(self)
        h.setContentsMargins(4, 2, 4, 2)

        h.addWidget(QLabel("Mode:"))

        self.cb_stream = QCheckBox("Stream")
        self.cb_rt = QCheckBox("Realtime")
        self.cb_basic = QCheckBox("Basic RT")

        h.addWidget(self.cb_stream)
        h.addWidget(self.cb_rt)
        h.addWidget(self.cb_basic)
        h.addStretch()

        self.cb_stream.toggled.connect(lambda v: self.cb_rt.setChecked(not v))
        self.cb_rt.toggled.connect(lambda v: self.cb_stream.setChecked(not v))

        self.cb_stream.setChecked(self.settings.get("api_mode", "stream") == "stream")
        self.cb_rt.setChecked(not self.cb_stream.isChecked())
        self.cb_basic.setChecked(self.settings.get("realtime_basic_mode", True))
        self.cb_basic.setEnabled(self.cb_rt.isChecked())

        self.cb_rt.toggled.connect(self.cb_basic.setEnabled)

        for cb in (self.cb_stream, self.cb_rt, self.cb_basic):
            cb.toggled.connect(self._save)

    def _save(self):
        self.settings.set("api_mode", "stream" if self.cb_stream.isChecked() else "realtime")
        self.settings.set("realtime_basic_mode", self.cb_basic.isChecked())
        self.settings_changed.emit()