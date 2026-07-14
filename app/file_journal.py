import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.utils import _unified_diff


@dataclass
class JournalEntry:
    status: str
    original_content: str | None
    original_hash: str | None = None


class FileJournal:
    def __init__(self):
        self.entries: dict[str, JournalEntry] = {}

    def snapshot_before_write(self, path: Path) -> None:
        if str(path) in self.entries:
            return
        if path.exists():
            original_content = path.read_text(encoding="utf-8")
            original_hash = self._hash(original_content)
            self.entries[str(path)] = JournalEntry(
                status="modified",
                original_content=original_content,
                original_hash=original_hash,
            )
        else:
            self.entries[str(path)] = JournalEntry(
                status="created",
                original_content=None,
                original_hash=None,
            )

    def rollback(self) -> None:
        for key, entry in self.entries.items():
            if entry.status == "created":
                Path(key).unlink(missing_ok=True)
            elif entry.status == "modified":
                original_content = entry.original_content
                Path(key).write_text(original_content, encoding="utf-8")
        self.entries.clear()

    def changes(self) -> list[tuple[str, str]]:
        return [(key, entry.status) for key, entry in self.entries.items()]

    def diff(self) -> str:
        parts = []
        for key, entry in self.entries.items():
            old = entry.original_content or ""  # created 的 old 当空串
            new = Path(key).read_text(encoding="utf-8")  # 当前磁盘内容
            parts.append(f"File: {key}")
            parts.append(_unified_diff(old, new, key))
        return "\n".join(parts)

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def accept(self) -> None:
        self.entries.clear()
