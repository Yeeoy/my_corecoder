import time

from app.events import EventName
from app.todo import TodoManager, TodoStatus
from app.tools.base import Tool, ToolResult


class TodoTool(Tool):
    """Manage the agent's task plan via a stateful TodoManager.

    Actions: plan, add, start, done, update, delete, list, clear.
    Emits ``TODO_UPDATED`` events so the UI and runtime state stay in sync.
    """

    name = "todo"
    description = (
        "Manage the current task plan. For any task involving analysis, code changes, "
        "and verification, this tool must be called first with action='plan' before "
        "reading files or running commands. Then mark steps as start/done while working."
    )

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "plan",
                    "add",
                    "start",
                    "done",
                    "update",
                    "delete",
                    "list",
                    "clear",
                ],
                "description": "Todo action to perform.",
            },
            "items": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Todo items for action='plan'.",
            },
            "content": {
                "type": "string",
                "description": "Todo content for action='add'.",
            },
            "id": {
                "type": "integer",
                "description": "Todo id for start/done/update/delete.",
            },
            "status": {
                "type": "string",
                "enum": [
                    TodoStatus.PENDING,
                    TodoStatus.IN_PROGRESS,
                    TodoStatus.COMPLETED,
                ],
                "description": "New status for action='update'.",
            },
        },
        "required": ["action"],
    }

    def __init__(self, todo_manager: TodoManager, events):
        self.todo_manager = todo_manager
        self.events = events

    def execute(
        self,
        action: str,
        items: list[str] | None = None,
        content: str | None = None,
        id: int | None = None,
        status: str | None = None,
    ) -> ToolResult:
        """Perform a todo *action* with the given arguments.

        Returns:
            ToolResult with:
            - ``ok``: False when required arguments are missing or the
              action is unknown.
            - ``content``: Todo list rendering or status message.
            - ``metadata``: tool, action, duration_ms.
        """
        start = time.perf_counter()
        try:
            if action == "plan":
                if not items:
                    return ToolResult(
                        ok=False,
                        content="",
                        error="Error: action='plan' requires items.",
                        metadata={
                            "tool": self.name,
                            "action": "plan",
                            "duration_ms": int((time.perf_counter() - start) * 1000),
                        },
                    )
                result = self.todo_manager.plan(items)
            elif action == "add":
                if not content:
                    return ToolResult(
                        ok=False,
                        content="",
                        error="Error: action='add' requires content.",
                        metadata={
                            "tool": self.name,
                            "action": "add",
                            "duration_ms": int((time.perf_counter() - start) * 1000),
                        },
                    )
                result = self.todo_manager.add_todo(content)
            elif action == "start":
                if id is None:
                    return ToolResult(
                        ok=False,
                        content="",
                        error="Error: action='start' requires id.",
                        metadata={
                            "action": "start",
                            "tool": self.name,
                            "duration_ms": int((time.perf_counter() - start) * 1000),
                        },
                    )
                result = self.todo_manager.update_todo(id, TodoStatus.IN_PROGRESS)
            elif action == "done":
                if id is None:
                    return ToolResult(
                        ok=False,
                        content="",
                        error="Error: action='done' requires id.",
                        metadata={
                            "tool": self.name,
                            "action": "done",
                            "duration_ms": int((time.perf_counter() - start) * 1000),
                        },
                    )
                result = self.todo_manager.update_todo(id, TodoStatus.COMPLETED)
            elif action == "update":
                if id is None:
                    return ToolResult(
                        ok=False,
                        content="",
                        error="Error: action='update' requires id.",
                        metadata={
                            "tool": self.name,
                            "action": "update",
                            "duration_ms": int((time.perf_counter() - start) * 1000),
                        },
                    )
                if not status:
                    return ToolResult(
                        ok=False,
                        content="",
                        error="Error: action='update' requires status.",
                        metadata={
                            "tool": self.name,
                            "action": "update",
                            "duration_ms": int((time.perf_counter() - start) * 1000),
                        },
                    )
                result = self.todo_manager.update_todo(id, status)
            elif action == "delete":
                if id is None:
                    return ToolResult(
                        ok=False,
                        content="",
                        error="Error: action='delete' requires id.",
                        metadata={
                            "tool": self.name,
                            "action": "delete",
                            "duration_ms": int((time.perf_counter() - start) * 1000),
                        },
                    )
                result = self.todo_manager.delete_todo(id)
            elif action == "list":
                result = self.todo_manager.render_todo()
            elif action == "clear":
                result = self.todo_manager.clear_todo()
            else:
                return ToolResult(
                    ok=False,
                    content="",
                    error=f"Unknown todo action: {action}",
                    metadata={
                        "tool": self.name,
                        "action": "unknown",
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                    },
                )

            self.events.emit(
                EventName.TODO_UPDATED,
                {
                    "action": action,
                    "todo": self.todo_manager.render_todo(),
                },
            )

            return ToolResult(
                ok=True,
                content=result,
                error=None,
                metadata={
                    "tool": self.name,
                    "action": action,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )

        except Exception as e:
            return ToolResult(
                ok=False,
                content="",
                error=str(e),
                metadata={
                    "tool": self.name,
                    "action": "unknown",
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
