"""
Small macOS automation helpers.
"""
import logging
import time
import subprocess
import os
import io

import pyperclip
from PIL import Image
from Quartz import CGDisplayCreateImage, CGMainDisplayID, CIContext, CIImage

logger = logging.getLogger(__name__)


class Automation:
    @staticmethod
    def insert_text(txt: str) -> bool:
        """Pastes text at current cursor location (⌘V)."""
        try:
            pyperclip.copy(txt)
            time.sleep(0.1)
            from AppKit import NSAppleScript  # type: ignore[reportMissingImports]

            script = NSAppleScript.alloc().initWithSource_(
                'tell application "System Events" to keystroke "v" using {command down}'
            )
            _, err = script.executeAndReturnError_(None)
            if err:
                logger.error("AppleScript error: %s", err)
                return False
            return True
        except Exception as exc:
            logger.error("insert_text failed: %s", exc)
            return False

    @staticmethod
    def take_screenshot() -> bytes:
        """Capture primary display – returns PNG bytes."""
        try:
            img_ref = CGDisplayCreateImage(CGMainDisplayID())
            ci_img = CIImage.imageWithCGImage_(img_ref)
            ctx = CIContext.contextWithOptions_(None)
            tiff = ctx.TIFFRepresentationOfImage_format_colorSpace_options_(ci_img, 0, None, None)
            pil = Image.open(io.BytesIO(tiff))
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as exc:
            logger.error("Screenshot failed: %s", exc)
            return b""

    @staticmethod
    def system_info() -> dict:
        """Basic CPU / mem / disk metrics."""
        import psutil, platform  # noqa: E401
        info = {
            "platform": platform.platform(),
            "cpu": psutil.cpu_percent(interval=1),
            "mem": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage("/").percent,
        }
        try:
            batt = psutil.sensors_battery()
            if batt:
                info["battery"] = {"percent": batt.percent, "plugged": batt.power_plugged}
        except Exception:
            pass
        return info

    @staticmethod
    def run_command(cmd: str, timeout: int = 30) -> str:
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return res.stdout if res.returncode == 0 else res.stderr
        except subprocess.TimeoutExpired:
            return "Command timed-out"
        except Exception as exc:
            return f"Error: {exc}"