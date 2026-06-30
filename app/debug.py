class DebugPrinter:
    def __init__(self, console, enabled: bool = False):
        self.console = console
        self.enabled = enabled

    def on(self):
        self.enabled = True

    def off(self):
        self.enabled = False

    def handle(self, payload: dict):
        if not self.enabled:
            return

        event = payload.get("_event", "unknown")
        self.console.print(f"\n[dim][event] {event}: {payload}[/dim]")
