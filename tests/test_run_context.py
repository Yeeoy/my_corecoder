from types import SimpleNamespace

from app.run_context import RunContext
from app.tools import AgentTool


def test_run_context_generates_unique_ids():
    assert RunContext().run_id != RunContext().run_id


def test_run_context_stores_parent():
    assert RunContext(parent_run_id="abc").parent_run_id == "abc"


def test_subagent_run_context_links_to_parent(monkeypatch):
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def chat(self, task):
            return "done"

    monkeypatch.setattr("app.agent.Agent", FakeAgent)

    parent = SimpleNamespace(
        llm=...,
        tools=[],
        permission_manager=...,
        events=...,
        _run_context=RunContext(),
    )  # 父已在运行中
    tool = AgentTool()
    tool._parent_agent = parent
    tool.execute(task="x", cancellation_token=None)

    assert captured["parent_run_id"] == parent._run_context.run_id
