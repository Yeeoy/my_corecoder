"""File creation and full overwrite."""

import time
from pathlib import Path

from app.tools.base import Tool, ToolResult
from app.tools.edit import _changed_files


class WriteFileTool(Tool):
    """Create a new file or completely overwrite an existing one.

    Writes UTF-8 text to disk, creating parent directories as needed.
    Tracked files are added to ``_changed_files`` for downstream diff
    and checkpoint workflows.
    """

    name = "write_file"
    description = (
        "Create a new file or completely overwrite an existing one. "
        "For small edits to existing files, prefer edit_file instead."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path for the file",
            },
            "content": {
                "type": "string",
                "description": "Full file content to write",
            },
        },
        "required": ["file_path", "content"],
    }

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()

    def _resolve_path(self, path: str) -> Path:
        p = Path(path).expanduser()
        if p.is_absolute():
            return p.resolve()
        return (self.workspace_root / p).resolve()

    def execute(self, file_path: str, content: str) -> ToolResult:
        """Write *content* to *file_path*, creating parent directories.

        Returns:
            ToolResult with:
            - ``ok``: True when the write succeeded.
            - ``content``: Human-readable summary (lines written, path).
            - ``metadata``: tool, path, lines_written, bytes, duration_ms.
        """
        start = time.perf_counter()

        try:
            p = self._resolve_path(file_path)
            p.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            p.write_text(content, encoding="utf-8")
            _changed_files.add(str(p))
            n_lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            return ToolResult(
                ok=True,
                content=f"Wrote {n_lines} lines to {file_path}",
                error=None,
                metadata={
                    "tool": self.name,
                    "path": file_path,
                    "lines_written": n_lines,
                    "bytes": len(content.encode("utf-8")),
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                content="",
                error=f"Error writing file: {type(e).__name__}: {e}",
                metadata={
                    "tool": self.name,
                    "path": file_path,
                    "lines_written": 0,
                    "bytes": 0,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
