import threading
from types import SimpleNamespace

from app.cancellation import CancellationToken
from app.web.session import WebAgentSession


class FakeBridge:
    """Minimal event bridge used by WebAgentSession tests."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict | None]] = []
        self.permission_requested = threading.Event()

    def publish(
        self,
        event_type: str,
        payload: dict | None = None,
    ) -> None:
        self.events.append((event_type, payload))

        if event_type == "permission_request":
            self.permission_requested.set()


def test_stop_releases_pending_permission_wait():
    bridge = FakeBridge()
    cancellation_token = CancellationToken()

    session = WebAgentSession(
        agent=SimpleNamespace(),
        bridge=bridge,
        cancellation_token=cancellation_token,
    )

    responses: list[str] = []

    permission_thread = threading.Thread(
        target=lambda: responses.append(
            session._wait_permission(
                tool_name="bash",
                reason="Command requires confirmation",
                arguments={"command": "rm temp.txt"},
            )
        ),
        daemon=True,
    )

    permission_thread.start()

    # 确保测试线程已经进入权限等待流程
    assert bridge.permission_requested.wait(timeout=0.5)
    session.stop()

    # 正常实现应该在 stop 后迅速唤醒权限等待线程
    permission_thread.join(timeout=0.3)

    still_waiting_after_stop = permission_thread.is_alive()

    # 当前有 bug 时，收到用解除等待，避免测试残留后台线程
    if still_waiting_after_stop:
        session.respond_permission("deny")
        permission_thread.join(timeout=1)

    assert not still_waiting_after_stop
    assert responses in (["deny"], ["cancel"])
