from app.todo import TodoManager, TodoStatus
from app.tools.base import Tool


class TodoTool(Tool):
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

    def __init__(self, todo_manager: TodoManager):
        self.todo_manager = todo_manager

    def execute(
        self,
        action: str,
        items: list[str] | None = None,
        content: str | None = None,
        id: int | None = None,
        status: str | None = None,
    ) -> str:
        try:
            if action == "plan":
                if not items:
                    return "Error: action='plan' requires items."
                return self.todo_manager.plan(items)

            if action == "add":
                if not content:
                    return "Error: action='add' requires content."
                return self.todo_manager.add_todo(content)

            if action == "start":
                if id is None:
                    return "Error: action='start' requires id."
                return self.todo_manager.update_todo(id, TodoStatus.IN_PROGRESS)

            if action == "done":
                if id is None:
                    return "Error: action='done' requires id."
                return self.todo_manager.update_todo(id, TodoStatus.COMPLETED)

            if action == "update":
                if id is None:
                    return "Error: action='update' requires id."
                if not status:
                    return "Error: action='update' requires status."
                return self.todo_manager.update_todo(id, status)

            if action == "delete":
                if id is None:
                    return "Error: action='delete' requires id."
                return self.todo_manager.delete_todo(id)

            if action == "list":
                return self.todo_manager.render_todo()

            if action == "clear":
                return self.todo_manager.clear_todo()

            return f"Unknown todo action: {action}"

        except Exception as e:
            return f"Error: {e}"
