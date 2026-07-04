import time
from pathlib import Path

from app.tools.base import Tool, ToolResult

# Files larger than this get smaller default page sizes to avoid
# blowing up context. The LLM can still paginate via offset/limit.
MAX_READ_BYTES = 200_000


class ReadFileTool(Tool):
    """Read a text file and return line-numbered content as a ToolResult.

    Supports pagination via *offset* / *limit* so large files can be read
    in chunks.  File metadata (path, line range, completeness, next offset)
    is duplicated into ``metadata`` so trace, UI, and event subscribers can
    consume it without string parsing.

    Content output is intentionally NOT truncated here — oversized results
    are handled later by ContextManager's snip layer.
    """

    name = "read_file"
    description = (
        "Read a text file with line numbers. The result includes file path, "
        "line range, total lines, whether the read is complete, and the next "
        "offset when more content remains. Use this instead of bash cat/head/tail."
    )

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to read.",
            },
            "offset": {
                "type": "integer",
                "description": (
                    "1-based starting line number. Use this only when continuing from a previous partial read."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read. If omitted, the tool chooses a safe default.",
            },
        },
        "required": ["file_path"],
    }

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()

    def _resolve_path(self, file_path: str) -> Path:
        path = Path(file_path).expanduser()
        if path.is_absolute():
            return path.resolve()
        return (self.workspace_root / path).resolve()

    def execute(
        self,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None,
    ) -> ToolResult:
        """Read a file and return structured result with metadata.

        Returns:
            ToolResult where:
            - ``ok``: False only for system errors (file not found, not a file,
              binary, read error). Offset-past-end and empty files are ok=True
              with a descriptive placeholder in content.
            - ``content``: Line-numbered file body or placeholder string.
            - ``metadata``: tool, path, total_lines, start_line, end_line,
              complete, next_offset (when incomplete), encoding, bytes,
              duration_ms, large_file (when file exceeds MAX_READ_BYTES).
        """
        start = time.perf_counter()
        path = self._resolve_path(file_path)

        # ── system errors → ok=False ──
        if not path.exists():
            return ToolResult(
                ok=False,
                content="",
                error=f"File not found: {file_path}",
                metadata={
                    "tool": self.name,
                    "path": str(path),
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "exists": False,
                },
            )

        if not path.is_file():
            return ToolResult(
                ok=False,
                content="",
                error=f"Not a file: {file_path}",
                metadata={
                    "tool": self.name,
                    "path": str(path),
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "exists": True,
                    "is_file": False,
                },
            )

        # ── size check before reading ──
        file_size = path.stat().st_size
        large_file = file_size > MAX_READ_BYTES

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult(
                ok=False,
                content="",
                error=f"File is not valid UTF-8 text: {file_path}",
                metadata={
                    "tool": self.name,
                    "path": str(path),
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "exists": True,
                    "is_file": True,
                    "is_binary": True,
                    "file_size_bytes": file_size,
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                content="",
                error=f"Error reading file: {type(e).__name__}: {e}",
                metadata={
                    "tool": self.name,
                    "path": str(path),
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )

        lines = text.splitlines()
        total_lines = len(lines)

        # ── edge cases → ok=True with placeholder ──
        if total_lines == 0:
            return ToolResult(
                ok=True,
                content="(empty file)",
                error=None,
                metadata={
                    "tool": self.name,
                    "path": str(path),
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "total_lines": 0,
                    "start_line": 0,
                    "end_line": 0,
                    "complete": True,
                    "encoding": "utf-8",
                    "bytes": 0,
                },
            )

        start_line = self._normalize_offset(offset)
        max_lines = self._normalize_limit(limit)

        if start_line > total_lines:
            return ToolResult(
                ok=True,
                content="(offset exceeds file length)",
                error=None,
                metadata={
                    "tool": self.name,
                    "path": str(path),
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "total_lines": total_lines,
                    "start_line": start_line,
                    "end_line": total_lines,
                    "complete": True,
                    "encoding": "utf-8",
                    "bytes": file_size,
                    "large_file": large_file,
                },
            )

        # ── normal read ──
        start_index = start_line - 1
        end_index = min(start_index + max_lines, total_lines)
        selected = lines[start_index:end_index]
        end_line = end_index
        complete = end_line >= total_lines

        body = self._format_lines(selected, start_line)

        metadata = {
            "tool": self.name,
            "path": str(path),
            "duration_ms": int((time.perf_counter() - start) * 1000),
            "total_lines": total_lines,
            "start_line": start_line,
            "end_line": end_line,
            "complete": complete,
            "encoding": "utf-8",
            "bytes": file_size,
        }
        if large_file:
            metadata["large_file"] = True
        if not complete:
            metadata["next_offset"] = end_line + 1

        return ToolResult(
            ok=True,
            content=body,
            error=None,
            metadata=metadata,
        )

    @staticmethod
    def _normalize_offset(offset: int | None) -> int:
        if offset is None:
            return 1
        try:
            return max(1, int(offset))
        except Exception:
            return 1

    @staticmethod
    def _normalize_limit(limit: int | None) -> int:
        if limit is None:
            return 500
        try:
            return max(1, min(int(limit), 1000))
        except Exception:
            return 500

    @staticmethod
    def _format_lines(lines: list[str], start_line: int) -> str:
        width = len(str(start_line + len(lines)))
        formatted = []
        for index, line in enumerate(lines, start=start_line):
            formatted.append(f"{index:<{width}}  {line}")
        return "\n".join(formatted)
