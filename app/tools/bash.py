import os
import queue
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

from app.tools.base import Tool, ToolResult

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
    """
    Execute shell commands with safety checks, timeout, and cwd tracking.
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
    parallel_safe = False
    timeout_seconds = 120
    supports_cancellation = True

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self._cwd = str(self.workspace_root)

    def execute(
        self,
        command: str,
        timeout: int = timeout_seconds,
        cancellation_token=None,
    ) -> ToolResult:
        return self._execute_serialized(
            command=command,
            timeout=timeout,
            cancellation_token=cancellation_token,
        )

    def _kill_tree(self, proc: subprocess.Popen, sig: signal.Signals):
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), sig)
            else:
                proc.terminate()
        except ProcessLookupError:
            pass

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

    def _execute_serialized(
        self,
        command: str,
        timeout: int,
        cancellation_token=None,
    ) -> ToolResult:
        start = time.perf_counter()
        token = cancellation_token

        # First line of defense — block catastrophically dangerous commands
        # before they reach the shell.
        warning = _check_dangerous(command)
        cwd = self._cwd

        if warning:
            return ToolResult(
                ok=False,
                content="",
                error=(
                    f"Blocked: {warning}\nCommand: {command}\nIf intentional, modify the command to be more specific."
                ),
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
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                shell=True,
                start_new_session=True,
            )

            output_queue: queue.Queue[tuple[str, str, Exception | None]] = queue.Queue(maxsize=1)

            def collect_output() -> None:
                try:
                    stdout, stderr = proc.communicate()

                    output_queue.put(
                        (
                            stdout or "",
                            stderr or "",
                            None,
                        )
                    )
                except Exception as exc:
                    output_queue.put(("", "", exc))

            drain_thread = threading.Thread(
                target=collect_output,
                name=f"bash-output-drain-{proc.pid}",
                daemon=True,
            )
            drain_thread.start()

            cancelled = False
            timed_out = False
            deadline = time.perf_counter() + timeout

            stdout = ""
            stderr = ""
            drain_error: Exception | None = None

            while True:
                try:
                    stdout, stderr, drain_error = output_queue.get(
                        timeout=0.05,
                    )
                    break

                except queue.Empty:
                    if token and token.cancelled:
                        cancelled = True
                        self._kill_tree(proc, signal.SIGTERM)
                        break

                    if time.perf_counter() >= deadline:
                        timed_out = True
                        self._kill_tree(proc, signal.SIGTERM)
                        break

            if cancelled or timed_out:
                try:
                    stdout, stderr, drain_error = output_queue.get(
                        timeout=5,
                    )
                except queue.Empty:
                    self._kill_tree(proc, signal.SIGKILL)

                    try:
                        stdout, stderr, drain_error = output_queue.get(
                            timeout=5,
                        )
                    except queue.Empty:
                        reason = (
                            "Command cancelled by user" if cancelled else f"Command timed out after {timeout} seconds"
                        )

                        return ToolResult(
                            ok=False,
                            content="Command produced no collectable output.",
                            error=(f"{reason}; failed to collect subprocess output after forced termination"),
                            metadata={
                                "tool": self.name,
                                "command": command,
                                "cwd": cwd,
                                "exit_code": proc.returncode,
                                "duration_ms": int((time.perf_counter() - start) * 1000),
                                "timeout": timed_out,
                            },
                        )

            drain_thread.join(timeout=0.1)

            if drain_error is not None:
                raise drain_error

            content = self._build_content(stdout, stderr)

            if timed_out:
                return ToolResult(
                    ok=False,
                    content=content,
                    error=f"Command timed out after {timeout} seconds",
                    metadata={
                        "tool": self.name,
                        "command": command,
                        "cwd": cwd,
                        "exit_code": proc.returncode,
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                        "timeout": True,
                        "stdout_bytes": len(stdout.encode("utf-8")),
                        "stderr_bytes": len(stderr.encode("utf-8")),
                    },
                )

            if cancelled:
                return ToolResult(
                    ok=False,
                    content=content,
                    error="Command cancelled by user",
                    metadata={
                        "tool": self.name,
                        "command": command,
                        "cwd": cwd,
                        "exit_code": proc.returncode,
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                        "timeout": False,
                        "stdout_bytes": len(stdout.encode("utf-8")),
                        "stderr_bytes": len(stderr.encode("utf-8")),
                    },
                )

            ok = proc.returncode == 0

            if ok:
                self._cwd = _resolve_next_cwd(command, cwd)

            return ToolResult(
                ok=ok,
                content=content,
                error=(None if ok else (stderr.strip() or f"Command failed with exit code {proc.returncode}")),
                metadata={
                    "tool": self.name,
                    "command": command,
                    "cwd": cwd,
                    "exit_code": proc.returncode,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "timeout": False,
                    "stdout_bytes": len(stdout.encode("utf-8")),
                    "stderr_bytes": len(stderr.encode("utf-8")),
                },
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                content="",
                error=f"Failed to run command: {type(exc).__name__}: {exc}",
                metadata={
                    "tool": self.name,
                    "command": command,
                    "cwd": cwd,
                    "exit_code": None,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "timeout": False,
                },
            )


def _check_dangerous(cmd: str) -> str | None:
    """Return a human-readable reason if *cmd* matches a known-dangerous pattern.

    Returns None when the command passes the safety check.
    """
    for pattern, reason in _DANGEROUS_PATTERNS:
        if re.search(pattern, cmd):
            return reason
    return None


def _resolve_next_cwd(command: str, current_cwd: str):
    running = current_cwd

    for part in command.split("&&"):
        part = part.strip()

        if not part.startswith("cd "):
            continue

        target = part[3:].strip().strip("'\"")

        if not target:
            continue

        expanded_target = os.path.expanduser(target)

        if os.path.isabs(expanded_target):
            new_dir = os.path.normpath(expanded_target)
        else:
            new_dir = os.path.normpath(os.path.join(running, expanded_target))

        if os.path.isdir(new_dir):
            running = new_dir
    return running
