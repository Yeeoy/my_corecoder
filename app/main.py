import sys

from rich.console import Console

from app.agent import Agent
from app.config import config
from app.debug import DebugPrinter
from app.events import EventBus
from app.llm import LLM
from app.runlog import RunLogger
from app.tools import ALL_TOOLS
from app.trace import TraceCollector

# 状态追踪
_is_first_token = True
_is_reasoning = False

console = Console(force_terminal=True)


events = EventBus()
trace = TraceCollector()
debug = DebugPrinter(console)
runlog = RunLogger()

events.on("*", trace.handle)
events.on("*", debug.handle)
events.on("*", runlog.handle)


def on_reasoning(reasoning):
    global _is_reasoning
    if not _is_reasoning:
        print("\n\033[34m💭 Thinking:\033[0m ", end="", flush=True)
        _is_reasoning = True
    print(f"\033[2m{reasoning}\033[0m", end="", flush=True)


def _brief(kwargs: dict, maxlength: int = 80) -> str:
    s = ", ".join(f"{k}={repr(v)[:80]}" for k, v in kwargs.items())
    return s[:maxlength] + ("..." if len(s) > maxlength else "")


def on_token(tok):
    global _is_first_token, _is_reasoning
    if _is_reasoning:
        print()  # 思考结束后换行
        _is_reasoning = False
    if _is_first_token:
        print("\033[36m✨ Answer:\033[0m ", end="", flush=True)
        _is_first_token = False
    print(tok, end="", flush=True)


def on_tool(name, kwargs):
    console.print(f"\n[dim]> {name}({_brief(kwargs)})[/dim]")


def reset_state():
    global _is_first_token, _is_reasoning
    _is_first_token = True
    _is_reasoning = False


def main():
    llm = LLM(config.CORECODER_MODEL, config.OPENAI_API_KEY, config.OPENAI_BASE_URL)
    agent = Agent(
        llm=llm,
        tools=ALL_TOOLS,
        max_content_tokens=128_000,
        max_rounds=50,
        events=events,
    )
    while True:
        raw_input = input("\n\033[32mUser:\033[0m ")
        user_input = raw_input.strip()
        if user_input == "":
            continue

        if user_input == "/debug":
            status = "on" if debug.enabled else "off"
            console.print(f"Debug events: {status}")
            continue

        if user_input == "/debug on":
            debug.on()
            console.print("[green]Debug events enabled.[/green]")
            continue

        if user_input == "/debug off":
            debug.off()
            console.print("[yellow]Debug events disabled.[/yellow]")
            continue

        if user_input == "/trace":
            console.print(trace.format())
            continue

        if user_input == "/trace tools":
            console.print(trace.format_tools())
            continue

        if user_input == "/trace errors":
            console.print(trace.format_errors())
            continue

        if user_input == "/trace clear":
            trace.clear()
            console.print("[green]Trace cleared.[/green]")
            continue

        if user_input == "/runs":
            console.print(runlog.list_run_ids())
            continue

        if user_input in {"/run last", "/runs last"}:
            console.print(runlog.format_last_run())
            continue

        if user_input in {"/run last tools", "/runs last tools"}:
            console.print(runlog.format_last_run_tools())
            continue

        if user_input.startswith("/run ") and user_input.endswith(" tools"):
            run_id = user_input[len("/run ") : -len(" tools")].strip()
            console.print(runlog.format_run_tools(run_id))
            continue

        if user_input in {"/run last errors", "/runs last errors"}:
            console.print(runlog.format_last_run_errors())
            continue

        if user_input.startswith("/run ") and user_input.endswith(" errors"):
            run_id = user_input[len("/run ") : -len(" errors")].strip()
            console.print(runlog.format_run_errors(run_id))
            continue

        if user_input == "/run current tools":
            console.print(runlog.format_current_run_tools())
            continue

        if user_input == "/run current errors":
            console.print(runlog.format_current_run_errors())
            continue

        if user_input == "/run current":
            console.print(runlog.format_current_run())
            continue

        if user_input.startswith("/run "):
            run_id = user_input[5:].strip()
            console.print(runlog.format_run(run_id))
            continue

        if user_input.startswith("/"):
            print("\n\033[34mUsage:\033[0m ")
            print("  /debug: show debug status")
            print("  /debug on: print events live")
            print("  /debug off: stop printing events live")
            print("  /trace: show trace")
            print("  /trace tools: show tool trace")
            print("  /trace errors: show error trace")
            print("  /trace clear: clear trace")
            print("  /runs: show recent run ids")
            print("  /run last: show last run")
            print("  /run last tools: show last run tool events")
            print("  /run <id>: show specific run")
            print("  /run <id> tools: show specific run tool events")
            print("  /run last errors: show last run error events")
            print("  /run <id> errors: show specific run error events")
            print("  /run current: show current run")
            print("  /run current tools: show current run tool events")
            print("  /run current errors: show current run error events")
            print("  /: show usage")
            continue

        reset_state()

        try:
            agent.chat(user_input, on_token=on_token, on_tool=on_tool, on_reasoning=None)
        except KeyboardInterrupt:
            print("\n\033[31mInterrupted!\033[0m")
            sys.exit(130)
        except Exception as e:
            print(f"\n\033[31mError: {e}\033[0m")
            sys.exit(1)
        print()


if __name__ == "__main__":
    main()
