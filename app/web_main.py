import atexit
import threading
from pathlib import Path

import uvicorn
from rich.console import Console

from app.agent import Agent
from app.config import get_config
from app.events import EventBus, EventName
from app.llm import LLM
from app.logging_config import setup_logging
from app.mcp_client import MCPClientManager
from app.mcp_config import load_mcp_config, load_mcp_permission_policy
from app.permission import PermissionManager
from app.runlog import RunLogger
from app.skills import SkillManager
from app.todo import TodoManager
from app.todo_printer import TodoPrinter
from app.tools import create_tools
from app.trace import TraceCollector
from app.web.event_bridge import WebEventBridge
from app.web.server import WebRuntime, create_web_app
from app.web.session import WebAgentSession

setup_logging()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
console = Console(force_terminal=True)


def build_agent_runtime():
    events = EventBus()
    trace = TraceCollector()
    runlog = RunLogger()

    skills = SkillManager()
    skills.load_all_skills()

    todo_manager = TodoManager()
    permission_manager = PermissionManager(workspace_root=PROJECT_ROOT)

    mcp_policy = load_mcp_permission_policy(PROJECT_ROOT / ".mcp.json")
    permission_manager.set_mcp_policy(
        allow=mcp_policy.allow,
        confirm=mcp_policy.confirm,
        deny=mcp_policy.deny,
    )

    bridge = WebEventBridge()
    todo_printer = TodoPrinter(console)

    events.on("*", trace.handle)
    events.on("*", runlog.handle)
    events.on("*", bridge.handle)
    events.on(EventName.TODO_UPDATED, todo_printer.handle)

    tools = create_tools(
        skills=skills,
        todo_manager=todo_manager,
        events=events,
        workspace_root=PROJECT_ROOT,
    )

    cfg = get_config()
    llm = LLM(
        cfg.CORECODER_MODEL,
        cfg.OPENAI_API_KEY,
        cfg.OPENAI_BASE_URL,
    )

    agent = Agent(
        llm=llm,
        tools=tools,
        max_content_tokens=128_000,
        max_rounds=50,
        events=events,
        extra_system_context=skills.render_active_skills,
        permission_manager=permission_manager,
    )

    session = WebAgentSession(agent=agent, bridge=bridge)

    runtime = WebRuntime(
        bridge=bridge,
        session=session,
        tools=tools,
        skills=skills,
    )

    # 异步加载 MCP
    def load_mcp_async():
        console.print("[cyan]Loading MCP tools in background...[/cyan]")
        try:
            mcp_configs = load_mcp_config(PROJECT_ROOT / ".mcp.json")
            mcp_manager = MCPClientManager(mcp_configs, workspace_root=PROJECT_ROOT)
            mcp_tools = mcp_manager.start_sync()
            tools.extend(mcp_tools)
            # Agent._tool_by_name was built in __init__ before MCP loaded;
            # update it so _exec_tool can find MCP tools at runtime.
            for t in mcp_tools:
                agent.tool_by_name[t.name] = t
            atexit.register(mcp_manager.close_sync)
            console.print(f"[green]Loaded MCP tools: {len(mcp_tools)}[/green]")
        except Exception as e:
            console.print(f"[red]Failed to load MCP: {e}[/red]")

    mcp_thread = threading.Thread(target=load_mcp_async, daemon=True)
    mcp_thread.start()

    return runtime


runtime = build_agent_runtime()
app = create_web_app(runtime)


if __name__ == "__main__":
    uvicorn.run(
        "app.web_main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
