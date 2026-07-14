from types import SimpleNamespace

import pytest

from app.agent import Agent
from app.llm import ToolCall
from app.permission import PermissionManager
from app.run_context import RunContext
from app.tools import EditFileTool, WriteFileTool


def test_write_then_edit_share_first_snapshot_and_rollback(tmp_path):
    target_path = tmp_path / "target.txt"
    target_path.write_text("original\n", encoding="utf-8")

    write_tool = WriteFileTool(workspace_root=tmp_path)
    edit_tool = EditFileTool(workspace_root=tmp_path)

    agent = Agent(
        llm=SimpleNamespace(),
        tools=[write_tool, edit_tool],
        permission_manager=PermissionManager(workspace_root=tmp_path),
    )
    agent._run_context = RunContext()

    write_result = agent._exec_tool(
        ToolCall(
            id="call-write",
            name="write_file",
            arguments={"file_path": "target.txt", "content": "written\n"},
        )
    )

    assert write_result.ok

    edit_result = agent._exec_tool(
        ToolCall(
            id="call-edit",
            name="edit_file",
            arguments={"file_path": "target.txt", "old_string": "written\n", "new_string": "edited\n"},
        )
    )

    assert edit_result.ok

    journal = agent._run_context.journal

    assert journal.changes() == [(str(target_path), "modified")]

    diff = agent.file_diff()
    assert "-original\n" in diff
    assert "+edited\n" in diff
    assert "+written\n" not in diff

    agent.rollback_file_changes()
    assert target_path.read_text(encoding="utf-8") == "original\n"
    assert journal.changes() == []


def test_agent_write_created_file_and_rollback_removes_it(tmp_path):
    target_path = tmp_path / "created.txt"
    assert not target_path.exists()

    write_tool = WriteFileTool(workspace_root=tmp_path)
    agent = Agent(
        llm=SimpleNamespace(),
        tools=[write_tool],
        permission_manager=PermissionManager(workspace_root=tmp_path),
    )
    agent._run_context = RunContext()

    result = agent._exec_tool(
        ToolCall(
            id="call-create",
            name="write_file",
            arguments={
                "file_path": "created.txt",
                "content": "new content\n",
            },
        )
    )

    assert result.ok
    assert target_path.read_text(encoding="utf-8") == "new content\n"

    journal = agent._run_context.journal
    assert journal.changes() == [(str(target_path), "created")]

    diff = agent.file_diff()
    assert "+new content\n" in diff

    agent.rollback_file_changes()

    assert not target_path.exists()
    assert journal.changes() == []


def test_agent_accept_file_changes_keeps_content_and_clears_journal(tmp_path):
    target_path = tmp_path / "accepted.txt"
    target_path.write_text("original\n", encoding="utf-8")

    write_tool = WriteFileTool(workspace_root=tmp_path)
    agent = Agent(
        llm=SimpleNamespace(),
        tools=[write_tool],
        permission_manager=PermissionManager(workspace_root=tmp_path),
    )
    agent._run_context = RunContext()

    result = agent._exec_tool(
        ToolCall(
            id="call-accept",
            name="write_file",
            arguments={
                "file_path": "accepted.txt",
                "content": "accepted\n",
            },
        )
    )

    assert result.ok
    assert agent._run_context.journal.changes() == [(str(target_path), "modified")]

    agent.accept_file_changes()

    assert target_path.read_text(encoding="utf-8") == "accepted\n"
    assert agent._run_context.journal.changes() == []

    agent.rollback_file_changes()
    assert target_path.read_text(encoding="utf-8") == "accepted\n"


def test_agent_file_journal_api_requires_active_run():
    agent = Agent(
        llm=SimpleNamespace(),
        tools=[],
    )

    with pytest.raises(RuntimeError, match="No active run"):
        agent.file_diff()

    with pytest.raises(RuntimeError, match="No active run"):
        agent.rollback_file_changes()

    with pytest.raises(RuntimeError, match="No active run"):
        agent.accept_file_changes()
