class TodoPrinter:
    def __init__(self, console, enabled: bool = True):
        self.console = console
        self.enabled = enabled

    def handle(self, payload: dict):
        if not self.enabled:
            return

        todo = payload.get("todo", "")
        action = payload.get("action", "")

        self.console.print()
        self.console.print(f"[cyan]Todo updated: {action}[/cyan]")
        self.console.print(todo, markup=False)
