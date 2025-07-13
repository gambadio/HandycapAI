"""
Execute user-defined Python functions in-process.
"""
import asyncio
import json
import logging
import textwrap
from typing import Any, Dict

logger = logging.getLogger(__name__)


class FunctionExecutor:
    def __init__(self, settings):
        self.settings = settings
        self.funcs = self._load()

    def _load(self):
        out = {}
        try:
            for f in json.loads(self.settings.get("functions_json", "[]")):
                out[f["name"]] = f
            logger.info("Loaded %d custom functions", len(out))
        except Exception as exc:
            logger.warning("Function load error: %s", exc)
        return out

    # ─────────────────────
    async def execute(self, call: Dict[str, Any]) -> str:
        try:
            name = call.get("name")
            args = call.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)
            if name not in self.funcs:
                return f"Function '{name}' not found."

            code = textwrap.dedent(self.funcs[name]["action"])
            ns: Dict[str, Any] = {
                "args": args,
                "settings": self.settings,
                "logger": logger,
            }

            # Common helpers (clipboard, automation, …)
            import pyperclip, time, os, subprocess, psutil  # noqa: E401
            from automation import Automation

            ns.update({"pyperclip": pyperclip, "time": time, "os": os,
                       "subprocess": subprocess, "psutil": psutil, "Automation": Automation})

            exec(code, ns)
            return str(ns.get("result", "Function executed."))
        except Exception as exc:
            logger.exception("User function failed")
            return f"Execution error: {exc}"