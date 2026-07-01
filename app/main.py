import sys

from rich.console import Console

from app.agent import Agent
from app.commands import CommandRouter
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

        command_router = CommandRouter(console, events, trace, debug, runlog)
        if command_router.handle(user_input):
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
