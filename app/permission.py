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

    HIGH_RISK_READ_FILES = [
        Path("/etc/shadow"),
        Path("/etc/sudoers"),
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
        self.allowed_read_dirs: set[Path] = set()
        self.mcp_allow_tools: set[str] = set()
        self.mcp_confirm_tools: set[str] = set()
        self.mcp_deny_tools: set[str] = set()

        self._resolved_system_roots = [r.resolve() for r in self.SYSTEM_ROOTS]
        self._resolved_high_risk_files = [f.resolve() for f in self.HIGH_RISK_READ_FILES]

    # ── public API ──────────────────────────────────────────────────

    def check_tool_call(self, tool_name: str, arguments: dict) -> PermissionDecision:
        if self.mode == "yolo":
            return PermissionDecision("allow", "permission mode yolo")

        if tool_name.startswith("mcp__"):
            if tool_name in self.mcp_deny_tools:
                return PermissionDecision("deny", f"MCP tool denied by policy: {tool_name}")

            if tool_name in self.mcp_allow_tools:
                return PermissionDecision("allow", f"MCP tool allowed by policy: {tool_name}")

            if tool_name in self.mcp_confirm_tools:
                return PermissionDecision("confirm", f"MCP tool requires confirmation by policy: {tool_name}")

            return PermissionDecision("confirm", "MCP tool call requires confirmation")

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

        if self._is_read_dir_allowed(target):
            return PermissionDecision("allow", f"session read directory allowed: {target}")

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
            p = Path(file_path).expanduser()
            if p.is_absolute():
                return p.resolve()
            return (self.workspace_root / p).resolve()
        except Exception:
            return PermissionDecision("deny", f"invalid file path: {file_path}")

    @staticmethod
    def _extract_file_path(arguments: dict) -> str | None:
        for key in ("file_path", "path", "target_path", "filename"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _is_system_path(self, path: Path) -> bool:
        return any(path.is_relative_to(root) for root in self._resolved_system_roots)

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

    def _is_high_risk_read_path(self, path: Path) -> bool:
        """Check if an absolute path is too sensitive to read even with confirmation."""
        if any(path == f.resolve() for f in self._resolved_high_risk_files):
            return True
        if ".ssh" in path.parts and path.name.startswith("id_"):
            return True
        return bool(".ssh" in path.parts and path.name in {"known_hosts", "authorized_keys"})

    def allow_read_dir_for_session(self, file_path: str) -> str:
        try:
            target = Path(file_path).expanduser().resolve()
        except Exception:
            return f"Invalid file path: {file_path}"

        directory = target if target.is_dir() else target.parent
        self.allowed_read_dirs.add(directory)

        return f"Allowed read access for this session: {directory}"

    def render_allowed_read_dirs(self) -> str:
        if not self.allowed_read_dirs:
            return "No session read directories allowed."

        lines = ["Session read directories:"]
        for directory in sorted(self.allowed_read_dirs):
            lines.append(f"- {directory}")

        return "\n".join(lines)

    def clear_allowed_read_dirs(self) -> str:
        self.allowed_read_dirs.clear()
        return "Cleared session read directory grants."

    def _is_read_dir_allowed(self, target: Path) -> bool:
        return any(target.is_relative_to(directory) for directory in self.allowed_read_dirs)

    def set_mcp_policy(
        self,
        allow: set[str] | None = None,
        confirm: set[str] | None = None,
        deny: set[str] | None = None,
    ) -> None:
        self.mcp_allow_tools = allow or set()
        self.mcp_confirm_tools = confirm or set()
        self.mcp_deny_tools = deny or set()
