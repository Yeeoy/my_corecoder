from pathlib import Path

from app.tools.base import Tool


class ReadFileTool(Tool):
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
                "description": ("Maximum number of lines to read. If omitted, the tool chooses a safe default."),
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
    ) -> str:
        path = self._resolve_path(file_path)

        if not path.exists():
            return f"Error: file not found: {file_path}"

        if not path.is_file():
            return f"Error: not a file: {file_path}"

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"Error: file is not valid UTF-8 text: {file_path}"
        except Exception as e:
            return f"Error reading file {file_path}: {e}"

        lines = text.splitlines()

        total_lines = len(lines)

        if total_lines == 0:
            return f"File: {path}\nLines: 0-0 of 0\nComplete: true\n\n<empty file>"

        start_line = self._normalize_offset(offset)
        max_lines = self._normalize_limit(limit)

        if start_line > total_lines:
            return (
                f"File: {path}\n"
                f"Lines: {start_line}-{start_line} of {total_lines}\n"
                "Complete: true\n\n"
                "<offset is past end of file>"
            )

        start_index = start_line - 1
        end_index = min(start_index + max_lines, total_lines)
        selected = lines[start_index:end_index]

        end_line = end_index
        complete = end_line >= total_lines

        header = [
            f"File: {path}",
            f"Lines: {start_line}-{end_line} of {total_lines}",
            f"Complete: {str(complete).lower()}",
        ]

        if not complete:
            header.append(f"Next offset: {end_line + 1}")

        body = self._format_lines(selected, start_line)

        return "\n".join(header) + "\n\n" + body

    @staticmethod
    def _normalize_offset(offset: int | None) -> int:
        if offset is None:
            return 1

        try:
            offset = int(offset)
        except Exception:
            return 1

        return max(1, offset)

    @staticmethod
    def _normalize_limit(limit: int | None) -> int:
        if limit is None:
            return 500

        try:
            limit = int(limit)
        except Exception:
            return 500

        return max(1, min(limit, 1000))

    @staticmethod
    def _format_lines(lines: list[str], start_line: int) -> str:
        width = len(str(start_line + len(lines)))

        formatted = []

        for index, line in enumerate(lines, start=start_line):
            formatted.append(f"{index:<{width}}  {line}")

        return "\n".join(formatted)
