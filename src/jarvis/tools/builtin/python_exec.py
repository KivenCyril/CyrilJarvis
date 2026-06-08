from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class PythonExecTool(BaseTool):
    """Execute Python code in an isolated subprocess."""

    name = "python_execute"
    description = (
        "Execute a Python code snippet in a subprocess and return its "
        "stdout and stderr. Useful for calculations, data processing, "
        "and quick prototyping."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The Python source code to execute.",
            },
        },
        "required": ["code"],
    }

    _TIMEOUT = 30  # seconds

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        code: str = arguments["code"]

        # Write the code to a temporary file so the subprocess inherits a
        # clean ``__file__`` and avoids shell-escaping headaches.
        tmp = Path(tempfile.mktemp(suffix=".py", prefix="jarvis_exec_"))
        try:
            tmp.write_text(code, encoding="utf-8")

            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(tmp),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self._TIMEOUT
                )
            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(
                    success=False,
                    output=f"Execution timed out after {self._TIMEOUT}s",
                )
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to execute code: {exc}")
        finally:
            tmp.unlink(missing_ok=True)

        stdout_text = stdout.decode(errors="replace") if stdout else ""
        stderr_text = stderr.decode(errors="replace") if stderr else ""

        success = proc.returncode == 0
        parts: list[str] = []
        if stdout_text:
            parts.append(stdout_text)
        if stderr_text:
            parts.append(f"[stderr]\n{stderr_text}")

        output = "\n".join(parts) or ("(no output)" if success else "(no output)")

        return ToolResult(
            success=success,
            output=output,
            data={"returncode": proc.returncode},
        )
