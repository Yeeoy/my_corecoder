from pathlib import Path

from app.tools.base import Tool


class GlobTool(Tool):
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

    def execute(self, pattern: str, path: str = ".") -> str:
        try:
            base = self._resolve_path(path)
            if not base.is_dir():
                return f"Error: {path} is not a directory"

            hits = list(base.glob(pattern))
            hits.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

            total = len(hits)
            shown = hits[:100]
            lines = [str(h) for h in shown]
            result = "\n".join(lines)

            if total > 100:
                result += f"\n...({total} matches, showing first 100)"
            return result or "No files matched."
        except Exception as e:
            return f"Error: {e}"
