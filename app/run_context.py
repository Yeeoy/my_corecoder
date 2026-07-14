import uuid
from dataclasses import dataclass, field

from app.file_journal import FileJournal


@dataclass
class RunContext:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    parent_run_id: str | None = None
    journal: FileJournal = field(default_factory=FileJournal)
