import threading
import time
from types import SimpleNamespace

from app.agent import Agent
from app.cancellation import CancellationToken
from app.permission import PermissionManager
from app.tools import AgentTool


def make_tool_call(
    name: str,
    arguments: dict,
    call_id: str = "call-agent",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id,
        name=name,
        arguments=arguments,
    )


def test_subagent_stops_after_tool_timeout(tmp_path, monkeypatch):
    """A timed-out AgentTool must not continue running in the background."""

    subagent_started = threading.Event()
    subagent_finished = threading.Event()

    class FakeSubAgent:
        def __init__(
            self,
            *,
            cancellation_token=None,
            **kwargs,
        ) -> None:
            self.cancellation_token = cancellation_token

        def chat(self, task: str) -> str:
            subagent_started.set()

            deadline = time.monotonic() + 0.3

            while time.monotonic() < deadline:
                if self.cancellation_token is not None and self.cancellation_token.cancelled:
                    raise InterruptedError("Sub-agent cancelled")

                time.sleep(0.01)

            subagent_finished.set()
            return "late result"

    agent_tool = AgentTool()

    # 不等真实的 30 秒，测试中把超时缩短到 50ms。
    agent_tool.timeout_seconds = 0.05

    parent_token = CancellationToken()

    # 必须先创建真正的父 Agent。
    parent_agent = Agent(
        llm=SimpleNamespace(),
        tools=[agent_tool],
        permission_manager=PermissionManager(
            workspace_root=tmp_path,
        ),
        cancellation_token=parent_token,
    )

    # AgentTool.execute() 内部会在运行时导入 app.agent.Agent。
    # 替换成可控的 FakeSubAgent，避免调用真实 LLM。
    monkeypatch.setattr(
        "app.agent.Agent",
        FakeSubAgent,
    )

    result = parent_agent._exec_tool(
        make_tool_call(
            name="agent",
            arguments={"task": "perform slow work"},
        )
    )

    assert subagent_started.is_set()

    # 外层应该已经因为 50ms 超时而返回。
    assert not result.ok
    assert "timed out" in (result.error or "").lower()

    # 给错误实现足够时间继续完成后台任务。
    time.sleep(0.4)

    # 正确实现中，软超时应该取消 child token，
    # FakeSubAgent 不应该运行到 set(finished)。
    assert not subagent_finished.is_set()
