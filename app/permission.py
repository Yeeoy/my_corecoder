import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PermissionAction = Literal["allow", "confirm", "deny"]


@dataclass
class PermissionDecision:
    action: PermissionAction
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.action in {"allow", "confirm"}

    @property
    def require_confirm(self) -> bool:
        return self.action == "confirm"


class PermissionManager:
    """
    PermissionManager v0.2

    - Bash: safe commands allowed, risky commands require confirmation, dangerous commands denied.
    - File write: system paths blocked, outside workspace requires confirmation, sensitive files require confirmation.
    - File read: high-risk paths blocked, outside workspace requires confirmation, secrets require confirmation.
    """

    # ── sensitive file patterns (shared by read & write) ────────────

    SENSITIVE_NAMES = {
        "pyproject.toml",
        "requirements.txt",
        "uv.lock",
        "poetry.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "credentials",
        "credentials.json",
        "secrets.json",
        "secret.json",
        "config.json",
    }

    SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx")

    SENSITIVE_DIRS = {".ssh", ".git"}

    # ── system roots (write blocked) ────────────────────────────────

    SYSTEM_ROOTS = [
        Path("/etc"),
        Path("/bin"),
        Path("/sbin"),
        Path("/usr/bin"),
        Path("/usr/sbin"),
        Path("/System"),
        Path("/Library"),
    ]

    # ── bash rules ──────────────────────────────────────────────────

    DENY_RULES: list[tuple[re.Pattern, str]] = [
        (
            re.compile(r"\bmkfs(\.\w+)?\b", re.I),
            "filesystem formatting command is blocked",
        ),
        (
            re.compile(r"\bdd\s+.*\bof=/dev/", re.I),
            "dd writing to device is blocked",
        ),
        (
            re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\};\s*:", re.I),
            "fork bomb is blocked",
        ),
        (
            re.compile(r"\brm\s+-[^\s]*r[^\s]*f\s+/\S*\s*$", re.I | re.M),
            "attempt to delete root directory is blocked",
        ),
    ]

    CONFIRM_RULES: list[tuple[re.Pattern, str]] = [
        (
            re.compile(r"\brm\s+(-[^\s]*r[^\s]*f|-rf|-fr)\b", re.I),
            "recursive force delete detected: rm -rf",
        ),
        (
            re.compile(r"\brm\b", re.I),
            "delete command requires confirmation: rm",
        ),
        (
            re.compile(r"\brmdir\b", re.I),
            "directory removal requires confirmation: rmdir",
        ),
        (
            re.compile(r"\bunlink\b", re.I),
            "file deletion requires confirmation: unlink",
        ),
        (
            re.compile(r"\bfind\b.*\s-delete\b", re.I | re.S),
            "find -delete requires confirmation",
        ),
        (
            re.compile(r"\bfind\b.*-exec\s+rm\b", re.I | re.S),
            "find -exec rm requires confirmation",
        ),
        (
            re.compile(r"\bpython\b.*\b(os\.remove|os\.unlink|shutil\.rmtree)\b", re.I | re.S),
            "python deletion code requires confirmation",
        ),
        (
            re.compile(r"\bsudo\b", re.I),
            "sudo command requires confirmation",
        ),
        (
            re.compile(r"\bchmod\s+-R\b", re.I),
            "recursive chmod requires confirmation",
        ),
        (
            re.compile(r"\bchown\s+-R\b", re.I),
            "recursive chown requires confirmation",
        ),
        (
            re.compile(r"\b(curl|wget)\b.*\|\s*(bash|sh|zsh)\b", re.I | re.S),
            "remote script piped into shell",
        ),
    ]

    def __init__(self, workspace_root: str | Path | None = None):
        self.mode = "default"
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()

    # ── public API ──────────────────────────────────────────────────

    def check_tool_call(self, tool_name: str, arguments: dict) -> PermissionDecision:
        if self.mode == "yolo":
            return PermissionDecision("allow", "permission mode yolo")

        dispatch = {
            "bash": self._check_bash,
            "write_file": self._check_file_write,
            "edit_file": self._check_file_write,
            "read_file": self._check_file_read,
        }

        handler = dispatch.get(tool_name)
        decision = handler(arguments) if handler else PermissionDecision("allow", "tool allowed")

        if self.mode == "strict" and decision.action == "confirm":
            return PermissionDecision("deny", f"strict mode blocked: {decision.reason}")

        return decision

    def set_mode(self, mode: str) -> str:
        if mode not in {"default", "strict", "yolo"}:
            return f"Unknown permission mode: {mode}"
        self.mode = mode
        return f"Permission mode set to: {mode}"

    def get_mode(self) -> str:
        return self.mode

    # ── bash checking ───────────────────────────────────────────────

    def _check_bash(self, arguments: dict) -> PermissionDecision:
        command = str(arguments.get("command", "")).strip()

        if not command:
            return PermissionDecision("deny", "empty bash command")

        for pattern, reason in self.DENY_RULES:
            if pattern.search(command):
                return PermissionDecision("deny", reason)

        for pattern, reason in self.CONFIRM_RULES:
            if pattern.search(command):
                return PermissionDecision("confirm", reason)

        return PermissionDecision("allow", "bash command allowed")

    # ── file write checking ─────────────────────────────────────────

    def _check_file_write(self, arguments: dict) -> PermissionDecision:
        target = self._resolve_path(arguments)
        if isinstance(target, PermissionDecision):
            return target

        if self._is_system_path(target):
            return PermissionDecision("deny", f"system path write blocked: {target}")

        if not target.is_relative_to(self.workspace_root):
            return PermissionDecision("confirm", f"write outside workspace: {target}")

        rel = target.relative_to(self.workspace_root)
        if self._is_sensitive_path(rel):
            return PermissionDecision("confirm", f"sensitive workspace file: {rel}")

        return PermissionDecision("allow", "write inside workspace")

    # ── file read checking ──────────────────────────────────────────

    def _check_file_read(self, arguments: dict) -> PermissionDecision:
        target = self._resolve_path(arguments)
        if isinstance(target, PermissionDecision):
            return target

        if self._is_high_risk_read_path(target):
            return PermissionDecision("deny", f"high-risk sensitive file read blocked: {target}")

        if not target.is_relative_to(self.workspace_root):
            return PermissionDecision("confirm", f"read outside workspace: {target}")

        rel = target.relative_to(self.workspace_root)
        if self._is_sensitive_path(rel):
            return PermissionDecision("confirm", f"sensitive workspace file read: {rel}")

        return PermissionDecision("allow", "read inside workspace")

    # ── shared helpers ──────────────────────────────────────────────

    def _resolve_path(self, arguments: dict) -> Path | PermissionDecision:
        """Extract and resolve a file path from arguments, or return a deny decision."""
        file_path = self._extract_file_path(arguments)

        if not file_path:
            return PermissionDecision("deny", "missing file path")

        try:
            return Path(file_path).expanduser().resolve()
        except Exception:
            return PermissionDecision("deny", f"invalid file path: {file_path}")

    @staticmethod
    def _extract_file_path(arguments: dict) -> str | None:
        for key in ("file_path", "path", "target_path", "filename"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _is_system_path(path: Path) -> bool:
        return any(path.is_relative_to(root) for root in PermissionManager.SYSTEM_ROOTS)

    def _is_sensitive_path(self, rel: Path) -> bool:
        """Check if a workspace-relative path is sensitive (shared by read & write)."""
        name = rel.name

        if name == ".env" or name.startswith(".env."):
            return True
        if name in self.SENSITIVE_NAMES:
            return True
        if any(name.endswith(s) for s in self.SENSITIVE_SUFFIXES):
            return True
        return bool(set(rel.parts) & self.SENSITIVE_DIRS)

    @staticmethod
    def _is_high_risk_read_path(path: Path) -> bool:
        """Check if an absolute path is too sensitive to read even with confirmation."""
        if str(path) in {"/etc/shadow", "/etc/sudoers"}:
            return True
        if ".ssh" in path.parts and path.name.startswith("id_"):
            return True
        return bool(".ssh" in path.parts and path.name in {"known_hosts", "authorized_keys"})
