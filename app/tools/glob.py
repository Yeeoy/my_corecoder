import time
from pathlib import Path

from app.tools.base import Tool, ToolResult

MAX_RESULTS = 100


class GlobTool(Tool):
    """Find files matching a glob pattern with ``**`` recursive support.

    Results are sorted by modification time (newest first) and capped at
    *MAX_RESULTS* to avoid flooding the LLM context.
    """
    name = "glob"
    description = "Find files matching a glob pattern. Supports ** for recursive matching(e.g. '**/*.py')"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern, e.g. '**/*.py' or 'src/**/*.ts'",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: cwd)",
            },
        },
        "required": ["pattern"],
    }

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()

    def _resolve_path(self, path: str | None) -> Path:
        if not path:
            return self.workspace_root

        p = Path(path).expanduser()

        if p.is_absolute():
            return p.resolve()

        return (self.workspace_root / p).resolve()

    def execute(self, pattern: str, path: str = ".") -> ToolResult:
        """Search for files matching *pattern* under *path*.

        Returns:
            ToolResult with:
            - ``ok``: False only when *path* is not a directory.
            - ``content``: Newline-separated file paths, or
              ``"No files matched"``.
            - ``metadata``: tool, pattern, path, match_count, truncated,
              duration_ms.
        """
        start = time.perf_counter()
        try:
            base = self._resolve_path(path)
            if not base.is_dir():
                return ToolResult(
                    ok=False,
                    content="",
                    error=f"Not a directory: {path}",
                    metadata={
                        "tool": self.name,
                        "pattern": pattern,
                        "path": path,
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                    },
                )

            hits = list(base.glob(pattern))
            hits.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

            total = len(hits)
            shown = hits[:MAX_RESULTS]
            lines = [str(h) for h in shown]
            result = "\n".join(lines)

            if total > MAX_RESULTS:
                result += f"\n...({total} matches, showing first {MAX_RESULTS})"

            return ToolResult(
                ok=True,
                content=result if result else "No files matched",
                metadata={
                    "tool": self.name,
                    "pattern": pattern,
                    "path": path,
                    "match_count": total,
                    "truncated": total > MAX_RESULTS,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                content="",
                error=f"Error during glob search: {type(e).__name__}: {e}",
                metadata={
                    "tool": self.name,
                    "pattern": pattern,
                    "path": path,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
