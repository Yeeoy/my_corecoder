class CommandRouter:
    def __init__(self, console, events, trace, debug, runlog):
        self.console = console
        self.events = events
        self.trace = trace
        self.debug = debug
        self.runlog = runlog

    def handle(self, user_input: str) -> bool:

        if not user_input.startswith("/"):
            return False

        if user_input == "":
            return True

        if user_input == "/debug":
            status = "on" if self.debug.enabled else "off"
            self.console.print(f"Debug events: {status}")
            return True

        if user_input == "/debug on":
            self.debug.on()
            self.console.print("[green]Debug events enabled.[/green]")
            return True

        if user_input == "/debug off":
            self.debug.off()
            self.console.print("[yellow]Debug events disabled.[/yellow]")
            return True

        if user_input == "/trace":
            self.console.print(self.trace.format())
            return True

        if user_input == "/trace tools":
            self.console.print(self.trace.format_tools())
            return True

        if user_input == "/trace errors":
            self.console.print(self.trace.format_errors())
            return True

        if user_input == "/trace clear":
            self.trace.clear()
            self.console.print("[green]Trace cleared.[/green]")
            return True

        if user_input == "/runs":
            self.console.print(self.runlog.list_run_ids())
            return True

        if user_input in {"/run last", "/runs last"}:
            self.console.print(self.runlog.format_last_run())
            return True

        if user_input in {"/run last tools", "/runs last tools"}:
            self.console.print(self.runlog.format_last_run_tools())
            return True

        if user_input.startswith("/run ") and user_input.endswith(" tools"):
            run_id = user_input[len("/run ") : -len(" tools")].strip()
            self.console.print(self.runlog.format_run_tools(run_id))
            return True

        if user_input in {"/run last errors", "/runs last errors"}:
            self.console.print(self.runlog.format_last_run_errors())
            return True

        if user_input.startswith("/run ") and user_input.endswith(" errors"):
            run_id = user_input[len("/run ") : -len(" errors")].strip()
            self.console.print(self.runlog.format_run_errors(run_id))
            return True

        if user_input == "/run current tools":
            self.console.print(self.runlog.format_current_run_tools())
            return True

        if user_input == "/run current errors":
            self.console.print(self.runlog.format_current_run_errors())
            return True

        if user_input == "/run current":
            self.console.print(self.runlog.format_current_run())
            return True

        if user_input.startswith("/run "):
            run_id = user_input[5:].strip()
            self.console.print(self.runlog.format_run(run_id))
            return True

        if user_input in {"/", "/help"}:
            self.print_usage()
            return True

        self.console.print(f"[yellow]Unknown command:[/yellow] {user_input}")
        self.print_usage()
        return True

    def _debug_status(self):
        status = "on" if self.debug.enabled else "off"
        self.console.print(f"Debug events: {status}")

    def print_usage(self):
        self.console.print("\n[blue]Usage:[/blue]")
        self.console.print("  /debug: show debug status")
        self.console.print("  /debug on: print events live")
        self.console.print("  /debug off: stop printing events live")
        self.console.print("  /trace: show trace")
        self.console.print("  /trace tools: show tool trace")
        self.console.print("  /trace errors: show error trace")
        self.console.print("  /trace clear: clear trace")
        self.console.print("  /runs: show recent run ids")
        self.console.print("  /run last: show last run")
        self.console.print("  /run last tools: show last run tool events")
        self.console.print("  /run last errors: show last run error events")
        self.console.print("  /run <id>: show specific run")
        self.console.print("  /run <id> tools: show specific run tool events")
        self.console.print("  /run <id> errors: show specific run error events")
        self.console.print("  /run current: show current run")
        self.console.print("  /help or /: show usage")
