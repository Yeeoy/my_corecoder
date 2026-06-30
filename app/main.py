import sys

from rich.console import Console

from app.agent import Agent
from app.config import config
from app.llm import LLM
from app.tools import ALL_TOOLS

# 状态追踪
_is_first_token = True
_is_reasoning = False

console = Console(force_terminal=True)


def on_reasoning(reasoning):
    global _is_reasoning
    if not _is_reasoning:
        print("\n\033[34m💭 Thinking:\033[0m ", end="", flush=True)
        _is_reasoning = True
    # dim 样式显示思考内容
    print(f"\033[2m{reasoning}\033[0m", end="", flush=True)


def _brief(kwargs: dict, maxlen: int = 80) -> str:
    s = ", ".join(f"{k}={repr(v)[:80]}" for k, v in kwargs.items())
    return s[:maxlen] + ("..." if len(s) > maxlen else "")


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


llm = LLM(config.CORECODER_MODEL, config.OPENAI_API_KEY, config.OPENAI_BASE_URL)
agent = Agent(llm=llm, tools=ALL_TOOLS, max_content_tokens=128_000, max_rounds=50)
while True:
    user_input = input("\n\033[32mUser:\033[0m ")
    if user_input.strip() == "":
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
