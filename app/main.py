import atexit
import sys
from pathlib import Path

from rich.console import Console

from app.agent import Agent
from app.commands import CommandRouter
from app.config import get_config
from app.debug import DebugPrinter
from app.events import EventBus, EventName
from app.llm import LLM
from app.mcp_client import MCPClientManager
from app.mcp_config import load_mcp_config, load_mcp_permission_policy
from app.permission import PermissionManager
from app.runlog import RunLogger
from app.runtime_state import RuntimeStateRenderer
from app.skills import SkillManager
from app.todo import TodoManager
from app.todo_printer import TodoPrinter
from app.tools import create_tools
from app.trace import TraceCollector

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 状态追踪
_is_first_token = True
_is_reasoning = False

console = Console(force_terminal=True)


events = EventBus()
trace = TraceCollector()
debug = DebugPrinter(console)
runlog = RunLogger()
skills = SkillManager()
skills.load_all_skills()
todo_manager = TodoManager()
permission_manager = PermissionManager(workspace_root=PROJECT_ROOT)
todo_printer = TodoPrinter(console)

events.on("*", trace.handle)
events.on("*", debug.handle)
events.on("*", runlog.handle)
events.on(EventName.TODO_UPDATED, todo_printer.handle)


mcp_configs = load_mcp_config(PROJECT_ROOT / ".mcp.json")
mcp_manager = MCPClientManager(mcp_configs, workspace_root=PROJECT_ROOT)
atexit.register(mcp_manager.close_sync)
mcp_tools = mcp_manager.start_sync()

tools = create_tools(
    skills=skills,
    todo_manager=todo_manager,
    events=events,
    workspace_root=PROJECT_ROOT,
)
tools.extend(mcp_tools)

console.print(f"[cyan]Loaded MCP tools: {len(mcp_tools)}[/cyan]")

mcp_policy = load_mcp_permission_policy(PROJECT_ROOT / ".mcp.json")
permission_manager.set_mcp_policy(
    allow=mcp_policy.allow,
    confirm=mcp_policy.confirm,
    deny=mcp_policy.deny,
)

runtime_state = RuntimeStateRenderer(
    skills=skills,
    permission_manager=permission_manager,
    todo_manager=todo_manager,
)


def on_reasoning(reasoning):
    global _is_reasoning
    if not _is_reasoning:
        print("\n\033[34m💭 Thinking:\033[0m ", end="", flush=True)
        _is_reasoning = True
    print(f"\033[2m{reasoning}\033[0m", end="", flush=True)


def _brief(kwargs: dict, maxlength: int = 200) -> str:
    s = ", ".join(f"{k}={repr(v)[:120]}" for k, v in kwargs.items())
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
    cfg = get_config()
    llm = LLM(cfg.CORECODER_MODEL, cfg.OPENAI_API_KEY, cfg.OPENAI_BASE_URL)
    agent = Agent(
        llm=llm,
        tools=tools,
        max_rounds=50,
        events=events,
        extra_system_context=skills.render_active_skills,
        permission_manager=permission_manager,
        runtime_state=runtime_state,
    )

    command_router = CommandRouter(
        agent, console, events, trace, debug, runlog, skills, permission_manager, todo_manager
    )

    while True:
        raw_input = input("\n\033[32mUser:\033[0m ")
        user_input = raw_input.strip()

        if user_input == "":
            continue

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
