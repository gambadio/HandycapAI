"""
Settings dialog + encrypted persistence +
Custom-functions table with JSON-schema editor.
"""

import os
import json
import logging

from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QCheckBox,
    QButtonGroup,
    QRadioButton,
    QSlider,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QHeaderView,
    QDialog,
)
from PySide6.QtCore import Qt, QSettings, QStandardPaths
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Low-level settings helper (unchanged)
class SettingsManager:
    """Wrapper around QSettings with transparent encryption for secrets."""

    def __init__(self):
        self.qsettings = QSettings("com.handycapai.app", "HandycapAI")
        cfg_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        os.makedirs(cfg_dir, exist_ok=True)
        key_path = os.path.join(cfg_dir, "settings.key")
        if not os.path.exists(key_path):
            with open(key_path, "wb") as f:
                f.write(Fernet.generate_key())
            logger.info("Generated new Fernet key")
        with open(key_path, "rb") as f:
            self.fernet = Fernet(f.read())

    def get(self, key: str, default=None):
        if key == "openai_api_key":
            enc = self.qsettings.value(key, "")
            if not enc:
                return ""
            try:
                return self.fernet.decrypt(enc.encode()).decode()
            except Exception:
                logger.warning("OpenAI key decrypt failed – resetting")
                self.qsettings.setValue(key, "")
                return ""
        return self.qsettings.value(key, default)

    def set(self, key: str, value):
        try:
            if key == "openai_api_key":
                enc = self.fernet.encrypt(value.strip().encode()).decode() if value else ""
                self.qsettings.setValue(key, enc)
            else:
                self.qsettings.setValue(key, value)
            self.qsettings.sync()
        except Exception as exc:
            logger.error("Settings save failed: %s", exc)
            raise

# ──────────────────────────────────────────────────────────
# JSON-schema editor dialog
class FunctionParameterDialog(QDialog):
    def __init__(self, parent=None, initial: str = "{}"):
        super().__init__(parent)
        self.setWindowTitle("Edit Function Parameters (JSON Schema)")
        self.setMinimumSize(500, 400)

        v = QVBoxLayout(self)
        self.editor = QTextEdit()
        self.editor.setPlainText(initial or "{}")
        v.addWidget(self.editor)

        btn_bar = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_bar.addStretch(1)
        btn_bar.addWidget(cancel_btn)
        btn_bar.addWidget(ok_btn)
        v.addLayout(btn_bar)

    @property
    def value(self) -> str:
        return self.editor.toPlainText()

# ──────────────────────────────────────────────────────────
# Main settings window
class SettingsWindow(QWidget):
    def __init__(self, settings: SettingsManager):
        super().__init__()
        self.setWindowTitle("HandycapAI Settings")
        self.setMinimumSize(820, 640)
        self.settings = settings

        layout = QFormLayout(self)

        # Wake-word
        wake_cb = QCheckBox('Enable wake-word ("Hello Freya")')
        wake_cb.setChecked(settings.get("wake_word_enabled", False))
        wake_cb.stateChanged.connect(lambda s: settings.set("wake_word_enabled", bool(s)))
        layout.addRow(wake_cb)

        # Picovoice key
        self.porcupine_edit = QLineEdit(settings.get("porcupine_api_key", ""))
        self.porcupine_edit.setEchoMode(QLineEdit.Password)
        layout.addRow("Picovoice API key:", self.porcupine_edit)

        # Hot-keys
        self.start_edit = QLineEdit(settings.get("hotkey_start", "Shift+Meta+Space"))
        self.end_edit = QLineEdit(settings.get("hotkey_stop", "Esc"))
        layout.addRow("Start hot-key:", self.start_edit)
        layout.addRow("Stop  hot-key:", self.end_edit)

        # API mode
        api_grp = QButtonGroup(self)
        stream_rb = QRadioButton("Chat-Completions (text)")
        realtime_rb = QRadioButton("Realtime Voice")
        api_grp.addButton(stream_rb)
        api_grp.addButton(realtime_rb)
        (realtime_rb if settings.get("api_mode", "stream") == "realtime" else stream_rb).setChecked(
            True
        )
        layout.addRow(stream_rb)
        layout.addRow(realtime_rb)

        # STT source
        stt_grp = QButtonGroup(self)
        local_rb = QRadioButton("Local Whisper")
        cloud_rb = QRadioButton("Cloud whisper-1")
        stt_grp.addButton(local_rb)
        stt_grp.addButton(cloud_rb)
        (cloud_rb if settings.get("stt_source", "local") == "cloud" else local_rb).setChecked(True)
        layout.addRow(local_rb)
        layout.addRow(cloud_rb)

        # Context slider
        self.ctx_slider = QSlider(Qt.Horizontal)
        self.ctx_slider.setRange(5, 50)
        self.ctx_slider.setValue(int(settings.get("max_context_length", 10)))
        ctx_lbl = QLabel(str(self.ctx_slider.value()))
        self.ctx_slider.valueChanged.connect(lambda v: ctx_lbl.setText(str(v)))
        layout.addRow("Max context messages:", self.ctx_slider)
        layout.addRow("", ctx_lbl)

        # OpenAI key
        self.openai_edit = QLineEdit(settings.get("openai_api_key", ""))
        self.openai_edit.setEchoMode(QLineEdit.Password)
        layout.addRow("OpenAI API key:", self.openai_edit)

        # Custom functions table
        self.func_tbl = QTableWidget(0, 4)
        self.func_tbl.setHorizontalHeaderLabels(
            ["Name", "Description", "Action (Python)", "Parameters"]
        )
        self.func_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.func_tbl.cellDoubleClicked.connect(self._edit_param_schema)
        layout.addRow("Custom Functions:", self.func_tbl)
        self._load_functions()

        # Buttons
        btns = QHBoxLayout()
        add_btn = QPushButton("Add")
        rm_btn = QPushButton("Remove")
        save_btn = QPushButton("Save Settings")
        add_btn.clicked.connect(self._add_func_row)
        rm_btn.clicked.connect(self._rm_func_row)
        save_btn.clicked.connect(self._save)
        btns.addWidget(add_btn)
        btns.addWidget(rm_btn)
        btns.addStretch(1)
        btns.addWidget(save_btn)
        layout.addRow(btns)

    # ─────────────────────
    # Function-table helpers
    def _load_functions(self):
        self.func_tbl.setRowCount(0)
        try:
            funcs = json.loads(self.settings.get("functions_json", "[]"))
        except Exception:
            funcs = []
        for f in funcs:
            r = self.func_tbl.rowCount()
            self.func_tbl.insertRow(r)
            self.func_tbl.setItem(r, 0, QTableWidgetItem(f.get("name", "")))
            self.func_tbl.setItem(r, 1, QTableWidgetItem(f.get("description", "")))
            self.func_tbl.setItem(r, 2, QTableWidgetItem(f.get("action", "")))
            self.func_tbl.setItem(
                r, 3, QTableWidgetItem(json.dumps(f.get("parameters", {}), indent=2))
            )

    def _add_func_row(self):
        r = self.func_tbl.rowCount()
        self.func_tbl.insertRow(r)
        default_params = {"type": "object", "properties": {}, "required": []}
        self.func_tbl.setItem(r, 3, QTableWidgetItem(json.dumps(default_params, indent=2)))

    def _rm_func_row(self):
        r = self.func_tbl.currentRow()
        if r >= 0:
            self.func_tbl.removeRow(r)

    def _edit_param_schema(self, row: int, col: int):
        if col != 3:
            return
        item = self.func_tbl.item(row, col)
        dlg = FunctionParameterDialog(self, initial=item.text() if item else "{}")
        if dlg.exec():
            self.func_tbl.setItem(row, col, QTableWidgetItem(dlg.value))

    # ─────────────────────
    def _save(self):
        try:
            self.settings.set("porcupine_api_key", self.porcupine_edit.text())
            self.settings.set("hotkey_start", self.start_edit.text())
            self.settings.set("hotkey_stop", self.end_edit.text())
            self.settings.set(
                "api_mode",
                "realtime"
                if any(rb.isChecked() and rb.text().startswith("Realtime") for rb in self.findChildren(QRadioButton))
                else "stream",
            )
            self.settings.set(
                "stt_source",
                "cloud"
                if any(rb.isChecked() and rb.text().startswith("Cloud") for rb in self.findChildren(QRadioButton))
                else "local",
            )
            self.settings.set("max_context_length", self.ctx_slider.value())
            self.settings.set("openai_api_key", self.openai_edit.text())

            funcs = []
            for r in range(self.func_tbl.rowCount()):
                name = self.func_tbl.item(r, 0)
                desc = self.func_tbl.item(r, 1)
                action = self.func_tbl.item(r, 2)
                params = self.func_tbl.item(r, 3)
                if not name or not action:
                    continue
                try:
                    params_obj = json.loads(params.text() if params else "{}")
                except json.JSONDecodeError:
                    params_obj = {"type": "object", "properties": {}, "required": []}
                funcs.append(
                    {
                        "name": name.text(),
                        "description": desc.text() if desc else "",
                        "action": action.text(),
                        "parameters": params_obj,
                    }
                )
            self.settings.set("functions_json", json.dumps(funcs))
            QMessageBox.information(self, "Settings", "Settings saved ✔")
        except Exception as exc:
            logger.exception("Settings save failed")
            QMessageBox.critical(self, "Error", f"Failed to save:\n{exc}")