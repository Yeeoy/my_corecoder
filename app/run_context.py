import uuid
from dataclasses import dataclass, field


@dataclass
class RunContext:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    parent_run_id: str | None = None
