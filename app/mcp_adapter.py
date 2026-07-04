import time

from app.tools.base import Tool, ToolResult


class MCPToolAdapter(Tool):
    def __init__(
        self,
        server_name: str,
        tool_name: str,
        description: str,
        input_schema: dict,
        manager,
    ):
        self.server_name = server_name
        self.input_schema = input_schema
        self.manager = manager

        self.name = f"mcp__{server_name}__{tool_name}"
        self.mcp_tool_name = tool_name
        self.description = f"[MCP:{server_name}] {description or tool_name}"
        self.parameters = input_schema or {
            "type": "object",
            "properties": {},
        }

    def execute(self, **kwargs) -> ToolResult:
        start = time.perf_counter()
        try:
            result = self.manager.call_tool_sync(
                server_name=self.server_name,
                tool_name=self.mcp_tool_name,
                arguments=kwargs,
            )
            return ToolResult(
                ok=True,
                content=result,
                error=None,
                metadata={
                    "tool": self.name,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                content="",
                error=f"Error: {type(e).__name__}: {e}",
                metadata={
                    "tool": self.name,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
