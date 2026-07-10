import threading
import time
from types import SimpleNamespace

from app.agent import Agent
from app.cancellation import CancellationToken
from app.permission import PermissionManager
from app.tools.base import Tool, ToolResult


class RecordingTool(Tool):
    """可观测并发状态的 bash 替身:记录同时活跃数与 start/end 顺序。"""

    name = "bash"
    description = "recording bash test double"
    parameters = {"type": "object", "properties": {}}
    timeout_seconds = 5  # 洞2: 必须 > 下面的 sleep,否则被 future.result(timeout=) 砍掉

    def __init__(self, parallel_safe: bool):
        self.parallel_safe = parallel_safe  # 洞2 鉴别力: 用参数控制,好写两个子场景
        self._lock = threading.Lock()  # 保护记录本身,别让替身自己有 race
        self.active = 0
        self.max_active = 0
        self.events = []

    def execute(self, **kwargs) -> ToolResult:
        label = kwargs.get("command")  # 用 arguments 里的标记区分 first/second
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.events.append(f"start:{label}")
        time.sleep(0.05)  # 洞2: 占住时间,并行才观测得到重叠
        with self._lock:
            self.active -= 1
            self.events.append(f"end:{label}")
        return ToolResult(ok=True, content="", metadata={})


def _tc(command, call_id):
    # 洞1: command 必须是 allow 命令(echo/pwd/ls),否则走权限那条顺序路径 = 绿在错的原因
    return SimpleNamespace(id=call_id, name="bash", arguments={"command": command})


def test_bash_calls_run_sequentially(tmp_path):
    """parallel_safe=False 的 bash 一批调用必须顺序执行,不进并行池。"""
    tool = RecordingTool(parallel_safe=False)
    agent = Agent(
        llm=SimpleNamespace(),
        tools=[tool],
        permission_manager=PermissionManager(workspace_root=tmp_path),
        cancellation_token=CancellationToken(),
    )
    tool_calls = [_tc("echo hi", "c1"), _tc("echo hi", "c2")]  # 洞1: allow 命令

    agent._exec_tools_parallel(tool_calls)

    assert tool.max_active == 1  # 顺序 → 从不重叠
    # 更强的断言(可选): events == ["start:...","end:...","start:...","end:..."]
    # TODO: 你补顺序断言(注意两个 command 都是 "echo hi",要区分 first/second 就用不同 label)


def test_parallel_safe_true_tool_overlaps(tmp_path):
    """洞2 鉴别力: 同样的 harness,parallel_safe=True 时应观测到并发(max_active==2)。
    没有这个测试,上面的 max_active==1 可能是空洞的真。"""
    tool = RecordingTool(parallel_safe=True)
    agent = Agent(
        llm=SimpleNamespace(),
        tools=[tool],
        permission_manager=PermissionManager(workspace_root=tmp_path),
        cancellation_token=CancellationToken(),
    )
    tool_calls = [_tc("echo hi", "c1"), _tc("echo hi", "c2")]

    agent._exec_tools_parallel(tool_calls)

    assert tool.max_active == 2  # 并行 → 重叠
