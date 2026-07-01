import fnmatch
import os
import re
from pathlib import Path

from app.tools.base import Tool

# skip these dirs to avoid noise
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", "dist", "build"}


class GrepTool(Tool):
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
                "description": "File or directory to search (default: cwd)",
            },
            "include": {
                "type": "string",
                "description": "Only search files matching this glob (e.g. '*.py')",
            },
        },
        "required": ["pattern"],
    }

    def execute(self, pattern: str, path: str = ".", include: str | None = None) -> str:
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Invalid regex: {e}"

        base = Path(path).expanduser().resolve()
        if not base.exists():
            return f"Error: {path} not found"

        files = [base] if base.is_file() else self._walk(base, include)

        matches = []
        for fp in files:
            # read file as bytes, skip binary files
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
                    if len(matches) >= 200:
                        matches.append("... (200 match limit reached)")
                        return "\n".join(matches)

        return "\n".join(matches) if matches else "No matches found."

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
                if len(results) >= 5000:
                    return results
        return results
