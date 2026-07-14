"""Search-and-replace file editing (Claude Code's key innovation).

The core idea: instead of sending whole-file rewrites or line-number patches,
the LLM specifies an *exact* substring to find and its replacement. The
substring must appear exactly once in the file, which eliminates ambiguity
and makes edits safe and reviewable.
"""

import time
from pathlib import Path

from app.file_journal import FileJournal
from app.tools.base import Tool, ToolResult
from app.utils import _unified_diff

MAX_RESULTS = 3000

# track files changed this session for /diff
_changed_files: set[str] = set()


class EditFileTool(Tool):
    """Edit a file by replacing an exact string match.

    Uses the Claude-Code-style *old_string* / *new_string* approach:
    *old_string* must appear exactly once in the file, which eliminates
    ambiguity and makes every edit reviewable via its unified diff.
    """

    name = "edit_file"
    description = (
        "Edit a file by replacing an exact string match. "
        "old_string must appear exactly once in the file for safety. "
        "Include enough surrounding context to ensure uniqueness."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to edit",
            },
            "old_string": {
                "type": "string",
                "description": "Exact text to find (must be unique in file)",
            },
            "new_string": {
                "type": "string",
                "description": "Replacement text",
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    }
    wants_journal: bool = True

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()

    def _resolve_path(self, path: str) -> Path:
        p = Path(path).expanduser()
        if p.is_absolute():
            return p.resolve()
        return (self.workspace_root / p).resolve()

    def execute(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        journal: FileJournal | None = None,
    ) -> ToolResult:
        """Replace *old_string* with *new_string* in *file_path*.

        *old_string* must appear exactly once in the file. When it doesn't,
        the first 500 characters of the file are included in ``content`` so
        the LLM can adjust its match.

        Returns:
            ToolResult with:
            - ``ok``: True when the edit was applied and a unified diff is
              returned.
            - ``content``: Unified diff on success, file preview on match
              failure.
            - ``metadata``: tool, path, duration_ms.
        """
        start = time.perf_counter()
        try:
            p = self._resolve_path(file_path)
            if not p.exists():
                return ToolResult(
                    ok=False,
                    content="",
                    error=f"File not found: {file_path}",
                    metadata={
                        "tool": self.name,
                        "path": file_path,
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                    },
                )

            try:
                content = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return ToolResult(
                    ok=False,
                    content="",
                    error=f"File is not a UTF-8 text file (edit_file only edits text files): {file_path}",
                    metadata={
                        "tool": self.name,
                        "path": file_path,
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                    },
                )
            occurrences = content.count(old_string)
            preview = content[:500] + ("..." if len(content) > 500 else "")
            if occurrences == 0:
                return ToolResult(
                    ok=False,
                    content=f"File starts with:\n{preview}",
                    error=f"old_string not found in {file_path}",
                    metadata={
                        "tool": self.name,
                        "path": file_path,
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                    },
                )
            if occurrences > 1:
                return ToolResult(
                    ok=False,
                    content=f"File starts with:\n{preview}",
                    error=f"old_string appears {occurrences} times in {file_path}. "
                    f"Include more surrounding lines to make it unique.",
                    metadata={
                        "tool": self.name,
                        "path": file_path,
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                    },
                )

            new_content = content.replace(old_string, new_string, 1)
            if journal is not None:
                journal.snapshot_before_write(p)
            p.write_text(new_content, encoding="utf-8")
            _changed_files.add(str(p))

            # generate a unified diff so the user/LLM can see exactly what changed
            diff = _unified_diff(content, new_content, str(p), max_result=MAX_RESULTS)
            return ToolResult(
                ok=True,
                content=f"Edited {file_path}\n{diff}",
                metadata={
                    "tool": self.name,
                    "path": file_path,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                content="",
                error=f"Error: {e}",
                metadata={
                    "tool": self.name,
                    "path": file_path,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
