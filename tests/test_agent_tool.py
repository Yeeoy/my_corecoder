from types import SimpleNamespace

from app.cancellation import CancellationToken
from app.tools.agent import AgentTool


def test_subagent_inherits_parent_context(monkeypatch):
    """子 agent 必须继承父的 token / permission_manager / events —— 否则静默降级
    (无取消、掉回 default 权限模式、事件不广播)。这条锚定"三根线真接上了",
    防将来重构 Agent 构造时手滑漏参数又静默回退。
    """
    captured = {}

    class FakeAgent:
        """Agent 替身:只记下构造参数,不真跑 LLM(离线、确定性)。"""

        def __init__(self, **kwargs):
            captured.update(kwargs)

        def chat(self, task):
            return "done"

    # 关键:AgentTool.execute 里是 `from ..agent import Agent`(函数内延迟 import,
    # 为破循环依赖)。执行时去 app.agent 模块取 Agent 属性 —— 所以在这里替换该属性
    # 就能拦住子 Agent 的构造,不必真实例化。
    monkeypatch.setattr("app.agent.Agent", FakeAgent)

    # 父 agent 替身:三个哨兵对象用 `is` 可辨识。tools 给空列表(execute 会遍历它)。
    parent = SimpleNamespace(
        llm=object(),
        tools=[],
        _cancellation_token=CancellationToken(),
        permission_manager=object(),
        events=object(),
    )

    tool = AgentTool()
    tool._parent_agent = parent

    result = tool.execute(task="anything")

    # 用 `is`(身份)不是 `==`(相等):要证"同一个对象被传下去",而非"两个相等对象"。
    assert captured["cancellation_token"] is parent._cancellation_token
    assert captured["permission_manager"] is parent.permission_manager
    assert captured["events"] is parent.events
    # 顺带确认 execute 正常走完、包了前缀
    assert result.ok is True
    assert "[Sub-agent completed]" in result.content
