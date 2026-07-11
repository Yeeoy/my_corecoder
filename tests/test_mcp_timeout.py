import asyncio
import concurrent.futures
import threading

import pytest

from app.mcp_client import MCPClientManager
from app.mcp_config import MCPServerConfig


def test_mcp_run_sync_requests_coroutine_cancellation_after_timeout(tmp_path):
    """Timing out in the caller should cancel the coroutine on the MCP loop."""

    manager = MCPClientManager(
        configs=[],
        workspace_root=tmp_path,
    )
    manager._ensure_loop()

    coroutine_started = threading.Event()
    coroutine_cancelled = threading.Event()
    coroutine_finished = threading.Event()

    # 用于在当前错误实现下主动结束协程，避免测试泄漏后台任务。
    release_coroutine = threading.Event()

    async def slow_operation() -> str:
        coroutine_started.set()

        try:
            while not release_coroutine.is_set():
                await asyncio.sleep(0.01)

            return "completed"
        except asyncio.CancelledError:
            coroutine_cancelled.set()
            raise
        finally:
            coroutine_finished.set()

    cancellation_observed = False

    try:
        with pytest.raises(concurrent.futures.TimeoutError):
            manager._run_sync(
                slow_operation(),
                timeout=0.05,
            )

        assert coroutine_started.wait(timeout=0.5)

        # 正确实现会在 result() 超时后调用 future.cancel()，
        # 进而让 slow_operation 收到 asyncio.CancelledError。
        cancellation_observed = coroutine_cancelled.wait(timeout=0.2)

    finally:
        # 当前实现不会取消 coroutine，因此必须手动让它结束，
        # 避免留下 event-loop 后台任务。
        release_coroutine.set()
        coroutine_finished.wait(timeout=1)

        manager.close_sync()

    assert cancellation_observed


def test_mcp_config_with_timeout(tmp_path, monkeypatch):
    config = [
        MCPServerConfig(name="test1", command="test1", timeout_seconds=5.0),
        MCPServerConfig(name="test2", command="test2"),
    ]

    manager = MCPClientManager(
        configs=config,
        workspace_root=tmp_path,
        call_timeout_seconds=30.0,
    )

    captured = {}

    def fake_run_sync(coro, timeout=None):
        coro.close()  # ← 关掉没 await 的协程,免 warning
        captured["timeout"] = timeout
        return "fake result"

    monkeypatch.setattr(manager, "_run_sync", fake_run_sync)
    monkeypatch.setattr(manager, "_ensure_loop", lambda: None)
    manager.call_tool_sync(server_name="test1", tool_name="test1", arguments={})
    assert captured["timeout"] == 5.0
    manager.call_tool_sync(server_name="test2", tool_name="test2", arguments={})
    assert captured["timeout"] == 30.0
