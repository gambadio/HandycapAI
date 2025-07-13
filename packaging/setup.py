"""
Bundle HandycapAI into a macOS .app via py2app.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from setuptools import setup

ROOT = Path(__file__).resolve().parent.parent

def _git_ver():
    try:
        return subprocess.check_output(["git", "describe", "--tags", "--always"]).decode().strip()
    except Exception:  # noqa: BLE001
        return "0.0.0"

APP = ["main.py"]
DATA_FILES = ["icons", "sounds", "wake_words"]
OPTIONS = {
    "argv_emulation": True,
    "iconfile": "icons/mic_grey.icns",
    "packages": ["PySide6.QtMultimedia", "openai", "cryptography"],
    "includes": ["asyncio", "multiprocessing"],
    "plist": {
        "CFBundleName": "HandycapAI",
        "CFBundleShortVersionString": _git_ver(),
        "LSMinimumSystemVersion": "10.15.0",
    },
}

setup(
    app=APP,
    data_files=[(str(Path(f)), []) for f in DATA_FILES if Path(f).exists()],
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)