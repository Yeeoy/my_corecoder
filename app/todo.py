from dataclasses import dataclass


class TodoStatus:
    PENDING = "pending"
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"


@dataclass
class Todo:
    id: str
    content: str
    status: str = TodoStatus.PENDING


class TodoManager:
    def __init__(self):
        self.todos: dict[int, Todo] = {}
        self._next_id = 1

    def plan(self, items: list[str]) -> str:
        self.clear_todo()

        for item in items:
            self.add_todo(item)

        return self.render_todo()

    def add_todo(self, content: str) -> str:
        todo = Todo(
            id=self._next_id,
            content=content,
            status=TodoStatus.PENDING,
        )
        self.todos[todo.id] = todo
        self._next_id += 1
        return f"Todo added: {todo.id}. {todo.content}"

    def update_todo(self, todo_id: int, status: str) -> str:
        if status not in {
            TodoStatus.PENDING,
            TodoStatus.IN_PROGRESS,
            TodoStatus.COMPLETED,
        }:
            return f"Invalid todo status: {status}"

        todo = self.todos.get(todo_id)
        if not todo:
            return f"Todo '{todo_id}' not found"

        todo.status = status
        return self.render_todo()

    def delete_todo(self, todo_id: int) -> str:
        if todo_id not in self.todos:
            return f"Todo '{todo_id}' not found"

        del self.todos[todo_id]
        return self.render_todo()

    def clear_todo(self) -> str:
        self.todos.clear()
        self._next_id = 1
        return "All todos cleared."

    def count_todo(self) -> int:
        return len(self.todos)

    def get_todo(self, todo_id: int) -> Todo | None:
        return self.todos.get(todo_id)

    def render_todo(self) -> str:
        if not self.todos:
            return "No todos."

        lines = ["Todo list:"]

        for todo in self.todos.values():
            marker = {
                TodoStatus.PENDING: " ",
                TodoStatus.IN_PROGRESS: ">",
                TodoStatus.COMPLETED: "x",
            }.get(todo.status, " ")

            lines.append(f"{todo.id}. [{marker}] {todo.content}")

        return "\n".join(lines)
