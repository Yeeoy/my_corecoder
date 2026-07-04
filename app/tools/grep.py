import fnmatch
import os
import re
import time
from pathlib import Path

from app.tools.base import Tool, ToolResult

# skip these dirs to avoid noise
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", "dist", "build"}

MAX_MATCHES = 200
MAX_RESULTS = 5000


class GrepTool(Tool):
    """Search file contents with a regex pattern.

    Walks the workspace (or a specific path), skipping binary files and
    noise directories.  Results are capped at *MAX_MATCHES* to avoid
    flooding the LLM context.
    """

    name = "grep"
    description = "Search file contents with regex. Returns matching lines with file path and line number."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for",
            },
            "path": {
                "type": "string",
                "description": "File or directory to search (default: workspace root)",
            },
            "include": {
                "type": "string",
                "description": "Only search files matching this glob (e.g. '*.py')",
            },
        },
        "required": ["pattern"],
    }

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()

    def _resolve_path(self, path: str | None) -> Path:
        if not path or path == ".":
            return self.workspace_root
        p = Path(path).expanduser()
        if p.is_absolute():
            return p.resolve()
        return (self.workspace_root / p).resolve()

    def execute(self, pattern: str, path: str = ".", include: str | None = None) -> ToolResult:
        """Search for *pattern* in *path*, optionally filtered by *include* glob.

        Returns:
            ToolResult with:
            - ``ok``: False only for invalid regex or missing path.
            - ``content``: Matching lines in ``file:lineno: text`` format,
              or ``"No matches found."``.
            - ``metadata``: tool, path, match_count, truncated, duration_ms.
        """
        start = time.perf_counter()
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return ToolResult(
                ok=False,
                content="",
                error=f"Invalid regex pattern: {type(e).__name__}: {e}",
                metadata={
                    "tool": self.name,
                    "path": path,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )

        base = self._resolve_path(path)
        if not base.exists():
            return ToolResult(
                ok=False,
                content="",
                error=f"Error: {path} not found",
                metadata={
                    "tool": self.name,
                    "path": path,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )

        files = [base] if base.is_file() else self._walk(base, include)

        matches = []
        for fp in files:
            try:
                raw = fp.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw[:8192]:
                continue
            text = raw.decode("utf-8", errors="ignore")
            for lineno, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    matches.append(f"{fp}:{lineno}: {line.rstrip()}")
                    if len(matches) >= MAX_MATCHES:
                        matches.append(f"... ({MAX_MATCHES} match limit reached)")
                        return ToolResult(
                            ok=True,
                            content="\n".join(matches),
                            metadata={
                                "tool": self.name,
                                "path": path,
                                "match_count": MAX_MATCHES,
                                "truncated": True,
                                "duration_ms": int((time.perf_counter() - start) * 1000),
                            },
                        )

        return ToolResult(
            ok=True,
            content="\n".join(matches) if matches else "No matches found.",
            metadata={
                "tool": self.name,
                "path": path,
                "match_count": len(matches),
                "truncated": False,
                "duration_ms": int((time.perf_counter() - start) * 1000),
            },
        )

    @staticmethod
    def _walk(root: Path, include: str | None) -> list[Path]:
        """Walk dir tree with directory pruning, skipping junk dirs entirely.

        Uses os.walk(top_down=True) so we can prune skipped directories
        in-place, avoiding iteration over their contents altogether.
        Previous implementation used Path.rglob() which generated entries
        for every file inside skipped dirs (e.g. thousands in node_modules)
        before filtering them out.
        """
        results = []
        root_str = str(root)
        for dirpath, dirnames, filenames in os.walk(root_str, topdown=True):
            # prune skipped dirs in-place so os.walk never descends into them
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

            for fname in filenames:
                if include and not fnmatch.fnmatch(fname, include):
                    continue
                results.append(Path(dirpath) / fname)
                if len(results) >= MAX_RESULTS:
                    return results
        return results
