"""
Settings dialog with encrypted persistence + toggle between
basic / advanced realtime + TTS controls.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, List

from cryptography.fernet import Fernet  # type: ignore
from PySide6.QtCore import Qt, QSettings, QStandardPaths
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────
class SettingsManager:
    """QSettings wrapper with encrypted OpenAI key."""

    def __init__(self):
        self.qs = QSettings("com.handycapai.app", "HandycapAI")
        cfg_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        os.makedirs(cfg_dir, exist_ok=True)
        key_path = os.path.join(cfg_dir, "settings.key")
        if not os.path.exists(key_path):
            with open(key_path, "wb") as fh:
                fh.write(Fernet.generate_key())
        self.fernet = Fernet(open(key_path, "rb").read())

    # ----------
    def get(self, key: str, default=None):
        if key == "openai_api_key":
            enc = self.qs.value(key, "")
            if not enc:
                return ""
            try:
                return self.fernet.decrypt(enc.encode()).decode()
            except Exception:  # noqa: BLE001
                logger.warning("API key decrypt failed")
                self.qs.setValue(key, "")
                return ""
        return self.qs.value(key, default)

    def set(self, key: str, value):
        if key == "openai_api_key":
            enc = self.fernet.encrypt(value.strip().encode()).decode() if value else ""
            self.qs.setValue(key, enc)
        else:
            self.qs.setValue(key, value)
        self.qs.sync()

# ───────────────────────────────────────────
class SettingsWindow(QWidget):
    def __init__(self, settings: SettingsManager):
        super().__init__()
        self.setWindowTitle("HandycapAI Settings")
        self.setMinimumSize(860, 700)
        self.settings = settings

        lay = QVBoxLayout(self)

        # ─── API section ───
        api_group = QGroupBox("API")
        api_form = QFormLayout(api_group)

        # Mode
        self.mode_grp = QButtonGroup(self)
        rb_stream = QRadioButton("Chat-Completions (stream)")
        rb_rt = QRadioButton("Realtime API")
        self.mode_grp.addButton(rb_stream, 0)
        self.mode_grp.addButton(rb_rt, 1)
        (rb_rt if settings.get("api_mode", "stream") == "realtime" else rb_stream).setChecked(True)
        api_form.addRow(rb_stream)
        api_form.addRow(rb_rt)

        # Basic vs advanced
        self.cb_basic = QCheckBox("Use basic realtime implementation (text-only)")
        self.cb_basic.setChecked(settings.get("realtime_basic_mode", True))
        self.cb_basic.setEnabled(rb_rt.isChecked())
        rb_rt.toggled.connect(self.cb_basic.setEnabled)
        api_form.addRow(self.cb_basic)

        # OpenAI key
        self.key_edit = QLineEdit(settings.get("openai_api_key", ""))
        self.key_edit.setEchoMode(QLineEdit.Password)
        api_form.addRow("OpenAI API key:", self.key_edit)

        lay.addWidget(api_group)

        # ─── TTS ───
        tts_group = QGroupBox("Voice output (TTS)")
        tts_form = QFormLayout(tts_group)
        self.cb_tts = QCheckBox("Enable TTS")
        self.cb_tts.setChecked(settings.get("tts_enabled", False))
        tts_form.addRow(self.cb_tts)

        self.voice_combo = QComboBox()
        self.voice_combo.addItems(["alloy", "echo", "fable", "onyx", "nova", "shimmer"])
        self.voice_combo.setCurrentText(settings.get("tts_voice", "alloy"))
        tts_form.addRow("Voice model:", self.voice_combo)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(1, 100)
        self.vol_slider.setValue(int(float(settings.get("tts_volume", 1.0)) * 100))
        tts_form.addRow("Volume:", self.vol_slider)

        lay.addWidget(tts_group)

        # ─── Custom functions ───
        func_group = QGroupBox("Custom functions")
        func_lay = QVBoxLayout(func_group)

        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["Name", "Description", "Action (Python)", "Parameters"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        func_lay.addWidget(self.tbl)

        btns = QHBoxLayout()
        add_btn = QPushButton("Add")
        rm_btn = QPushButton("Remove")
        add_btn.clicked.connect(self._add_row)
        rm_btn.clicked.connect(lambda: self.tbl.removeRow(self.tbl.currentRow()))
        btns.addWidget(add_btn)
        btns.addWidget(rm_btn)
        btns.addStretch()
        func_lay.addLayout(btns)

        lay.addWidget(func_group)
        lay.addStretch()

        # Save
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        lay.addWidget(save_btn, alignment=Qt.AlignRight)

        self._load_funcs()

    # ───────────────────────────────────────────
    def _load_funcs(self):
        self.tbl.setRowCount(0)
        try:
            funcs = json.loads(self.settings.get("functions_json", "[]"))
        except Exception:  # noqa: BLE001
            funcs = []
        for f in funcs:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(f.get("name", "")))
            self.tbl.setItem(r, 1, QTableWidgetItem(f.get("description", "")))
            self.tbl.setItem(r, 2, QTableWidgetItem(f.get("action", "")))
            self.tbl.setItem(r, 3, QTableWidgetItem(json.dumps(f.get("parameters", {}), indent=2)))

    def _add_row(self):
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        self.tbl.setItem(r, 3, QTableWidgetItem('{"type":"object","properties":{}}'))

    # ───────────────────────────────────────────
    def _save(self):
        try:
            self.settings.set("api_mode", "realtime" if self.mode_grp.checkedId() == 1 else "stream")
            self.settings.set("realtime_basic_mode", self.cb_basic.isChecked())
            self.settings.set("openai_api_key", self.key_edit.text())
            self.settings.set("tts_enabled", self.cb_tts.isChecked())
            self.settings.set("tts_voice", self.voice_combo.currentText())
            self.settings.set("tts_volume", self.vol_slider.value() / 100.0)

            funcs: List[Dict] = []
            for r in range(self.tbl.rowCount()):
                name = self.tbl.item(r, 0)
                action = self.tbl.item(r, 2)
                if not name or not action:
                    continue
                desc = self.tbl.item(r, 1)
                params = self.tbl.item(r, 3)
                try:
                    params_obj = json.loads(params.text() if params else "{}")
                except json.JSONDecodeError:
                    params_obj = {}
                funcs.append(
                    {
                        "name": name.text(),
                        "description": desc.text() if desc else "",
                        "action": action.text(),
                        "parameters": params_obj,
                    }
                )
            self.settings.set("functions_json", json.dumps(funcs))
            QMessageBox.information(self, "Settings", "Saved ✔")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Settings save failed")
            QMessageBox.critical(self, "Failure", str(exc))