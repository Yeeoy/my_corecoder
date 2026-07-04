from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    content: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_llm_content(self) -> str:
        if self.ok:
            return self.content
        parts = [f"Error: {self.error}"] if self.error else []
        if self.content:
            parts.append(self.content)
        return "\n\n".join(parts) or "(tool failed - no details)"


class Tool(ABC):
    name: str
    description: str
    parameters: dict

    @abstractmethod
    def execute(self, **kwargs) -> str | ToolResult: ...

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
