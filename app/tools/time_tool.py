import time

from app.tools.base import Tool, ToolResult


class TimeTool(Tool):
    """Return the current date and time as a formatted string."""

    name = "get_current_time"
    description = "Get the current date and time in YYYY-MM-DD HH:MM:SS format."
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def execute(self, **kwargs) -> ToolResult:
        """Return the current wall-clock time.

        Returns:
            ToolResult with ``ok=True``, content as a human-readable
            timestamp, and metadata with duration_ms.
        """
        start = time.perf_counter()
        return ToolResult(
            ok=True,
            content=time.strftime("%Y-%m-%d %H:%M:%S"),
            error=None,
            metadata={
                "tool": self.name,
                "duration_ms": int((time.perf_counter() - start) * 1000),
            },
        )

