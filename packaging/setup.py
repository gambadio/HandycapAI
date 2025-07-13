"""
py2app bundle generator (macOS).
Run:  python packaging/setup.py py2app
"""
from setuptools import setup

APP = ["main.py"]
DATA_FILES = ["icons", "sounds"]
OPTIONS = {
    "argv_emulation": True,
    "iconfile": "icons/mic_grey.icns",
    "plist": {
        "CFBundleName": "HandycapAI",
        "CFBundleShortVersionString": "0.9.5",
        "LSMinimumSystemVersion": "10.15.0",
    },
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)