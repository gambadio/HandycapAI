"""
Secure execution of user-defined Python functions.

• Static AST validation (imports, builtins)
• Restricted built-ins
• Optional isolated subprocess execution for unsafe code
"""
from __future__ import annotations

import ast
import asyncio
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

class SecureFunctionExecutor:
    """Validate + execute custom functions with minimal risk."""

    ALLOWED_IMPORTS = {
        "json",
        "math",
        "random",
        "datetime",
        "re",
        "hashlib",
        "base64",
        "itertools",
        "functools",
        "statistics",
    }
    SAFE_BUILTINS = {
        "abs": abs,
        "min": min,
        "max": max,
        "sum": sum,
        "len": len,
        "range": range,
        "enumerate": enumerate,
        "sorted": sorted,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "set": set,
        "print": print,
    }

    def __init__(self, settings):
        self.settings = settings
        self.funcs = self._load()

    # ───────────────────────────────────────────
    def _load(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        try:
            for f in json.loads(self.settings.get("functions_json", "[]")):
                if self._validate_source(f["action"]):
                    out[f["name"]] = f
                else:
                    logger.warning("Function %s rejected by validator", f["name"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Function load error: %s", exc)
        logger.info("Loaded %d secure functions", len(out))
        return out

    # ───────────────────────────────────────────
    def _validate_source(self, code: str) -> bool:
        """Static AST checks for dangerous constructs."""
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] not in self.ALLOWED_IMPORTS:
                            return False
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split(".")[0] not in self.ALLOWED_IMPORTS:
                        return False
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in {
                        "eval",
                        "exec",
                        "__import__",
                        "open",
                        "compile",
                    }:
                        return False
        except SyntaxError:
            return False
        return True

    # ───────────────────────────────────────────
    async def execute(self, call: Dict[str, Any]) -> str:
        name = call.get("name")
        args_json = call.get("arguments", "{}")

        if name not in self.funcs:
            return f"Function '{name}' not found."

        try:
            args = json.loads(args_json) if isinstance(args_json, str) else args_json
        except json.JSONDecodeError:
            args = {}

        src = self.funcs[name]["action"]

        if self.settings.get("allow_subprocess_functions", False):
            return await self._run_subprocess(src, args)
        return await self._run_restricted(src, args)

    # ───────────────────────────────────────────
    async def _run_restricted(self, src: str, args: Dict[str, Any]) -> str:
        env: Dict[str, Any] = {"__builtins__": self.SAFE_BUILTINS, "args": args, "result": None}
        loop = asyncio.get_running_loop()

        def runner() -> None:  # noqa: D401
            exec(src, env)  # pylint: disable=exec-used

        try:
            await loop.run_in_executor(None, runner)
            return str(env.get("result", "Function executed."))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Secure function failed")
            return f"Execution error: {exc}"

    # ───────────────────────────────────────────
    async def _run_subprocess(self, src: str, args: Dict[str, Any]) -> str:
        code = f"args={json.dumps(args, indent=2)}\nresult=None\n{src}\nprint(result)"
        with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=False) as fp:
            Path(fp.name).write_text(code, encoding="utf-8")
            path = fp.name

        proc = await asyncio.create_subprocess_exec(
            sys.executable, path, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            return "Function timed-out"

        if proc.returncode != 0:
            return f"Error: {err.decode()}"
        return out.decode().strip()