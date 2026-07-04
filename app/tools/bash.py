import os
import re
import subprocess
import threading
import time
from pathlib import Path

from app.tools.base import Tool, ToolResult

_local = threading.local()

# ── BashTool-internal danger patterns ────────────────────────────────────
# These are the FIRST line of defense, applied before PermissionManager.
# PermissionManager has its own overlapping rules (DENY_RULES + CONFIRM_RULES)
# that provide a second, mode-aware layer. The duplication is intentional:
# BashTool blocks truly catastrophic commands even in yolo mode, while
# PermissionManager handles risk-tiered decisions (allow / confirm / deny).
_DANGEROUS_PATTERNS = [
    (
        r"\brm\b\s+(?=.*(?:-\w*[rR]\w*|--recursive))(?=.*(?:-\w*f\w*|--force))"
        r".*(?:\s|^)(/|/\*|~|~/|\$HOME|\$\{HOME\}|['\"]\$HOME['\"]|['\"]\$\{HOME\}['\"])(?:\s|$)",
        "force recursive delete on root/home",
    ),
    (r"\bmkfs\b", "format filesystem"),
    (r"\bdd\s+.*of=/dev/", "raw disk write"),
    (r">\s*/dev/sd[a-z]", "overwrite block device"),
    (r"\bchmod\s+(-R\s+)?777\s+/", "chmod 777 on root"),
    (r":\(\)\s*\{.*:\|:.*\}", "fork bomb"),
    (r"\bcurl\b.*\|\s*(sudo\s+)?(ba)?sh\b", "pipe curl to shell"),
    (r"\bwget\b.*\|\s*(sudo\s+)?(ba)?sh\b", "pipe wget to shell"),
]


class BashTool(Tool):
    """Execute shell commands with safety checks, timeout, and cwd tracking.

    Output is captured via subprocess and returned as a structured ToolResult.
    Successful ``cd`` commands persist the working directory across calls via
    thread-local storage.
    """

    name = "bash"
    description = (
        "Execute a shell command. Return stdout, stderr, and exit code. "
        "Use this for running tests, installing packages, git operations, etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to run.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 120)",
            },
        },
        "required": ["command"],
    }

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()

    def execute(self, command: str, timeout: int = 120) -> ToolResult:
        """Run a shell command and return a structured result.

        Args:
            command: The shell command string to execute.
            timeout: Maximum execution time in seconds (default 120).

        Returns:
            ToolResult with:
            - ``ok``: True when exit code is 0.
            - ``content``: Formatted stdout/stderr (always present so the LLM
              can inspect output even on failure).
            - ``error``: None on success, or a human-readable reason on failure.
            - ``metadata``: exit_code, duration_ms, cwd, timeout flag, byte counts.
        """
        start = time.perf_counter()

        # First line of defense — block catastrophically dangerous commands
        # before they reach the shell.
        warning = _check_dangerous(command)
        cwd = getattr(_local, "cwd", None) or str(self.workspace_root)

        if warning:
            return ToolResult(
                ok=False,
                content="",
                error=f"Blocked: {warning}\nCommand: {command}\nIf intentional, modify the command to be more specific.",
                metadata={
                    "tool": self.name,
                    "command": command,
                    "cwd": cwd,
                    "exit_code": None,
                    "duration_ms": 0,
                    "timeout": False,
                },
            )

        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=cwd,
                shell=True,
            )

            duration_ms = int((time.perf_counter() - start) * 1000)

            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            content = self._build_content(stdout, stderr)

            ok = proc.returncode == 0
            if ok:
                _update_cwd(command, cwd)

            return ToolResult(
                ok=ok,
                content=content,
                error=None if ok else (stderr.strip() or f"Command failed with exit code {proc.returncode}"),
                metadata={
                    "tool": self.name,
                    "command": command,
                    "cwd": cwd,
                    "exit_code": proc.returncode,
                    "duration_ms": duration_ms,
                    "timeout": False,
                    "stdout_bytes": len(stdout.encode("utf-8")),
                    "stderr_bytes": len(stderr.encode("utf-8")),
                },
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)

            # TimeoutExpired may carry partial output as bytes or str.
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            return ToolResult(
                ok=False,
                content=self._build_content(stdout, stderr),
                error=f"Command timed out after {timeout} seconds",
                metadata={
                    "tool": self.name,
                    "command": command,
                    "cwd": cwd,
                    "exit_code": None,
                    "duration_ms": duration_ms,
                    "timeout": True,
                },
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolResult(
                ok=False,
                content="",
                error=f"Failed to run command: {type(exc).__name__}: {exc}",
                metadata={
                    "tool": self.name,
                    "command": command,
                    "cwd": cwd,
                    "exit_code": None,
                    "duration_ms": duration_ms,
                    "timeout": False,
                },
            )

    def _build_content(self, stdout: str, stderr: str) -> str:
        """Format captured stdout and stderr for LLM consumption.

        Prepends ``STDOUT:`` / ``STDERR:`` labels so the model can distinguish
        the two streams. Returns a placeholder string when both are empty.
        Output truncation is intentionally NOT done here — oversized outputs
        are handled later by ContextManager's snip layer.
        """
        parts = []

        if stdout.strip():
            parts.append(f"STDOUT:\n{stdout.strip()}")

        if stderr.strip():
            parts.append(f"STDERR:\n{stderr.strip()}")

        if not parts:
            return "Command completed with no output."

        return "\n\n".join(parts)


def _check_dangerous(cmd: str) -> str | None:
    """Return a human-readable reason if *cmd* matches a known-dangerous pattern.

    Returns None when the command passes the safety check.
    """
    for pattern, reason in _DANGEROUS_PATTERNS:
        if re.search(pattern, cmd):
            return reason
    return None


def _update_cwd(command: str, current_cwd: str):
    """Track working-directory changes across bash invocations.

    Parses ``cd`` segments in a ``&&``-chained command and updates
    thread-local storage so subsequent bash calls inherit the new cwd.
    Only persists a change when the target directory actually exists.
    """
    running = current_cwd
    changed = False
    for part in command.split("&&"):
        part = part.strip()
        if part.startswith("cd "):
            target = part[3:].strip().strip("'\"")
            if target:
                new_dir = os.path.normpath(os.path.join(running, os.path.expanduser(target)))
                if os.path.isdir(new_dir):
                    running = new_dir
                    changed = True

    if changed:
        _local.cwd = running
