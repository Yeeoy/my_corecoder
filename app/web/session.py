import threading
from typing import Any

from app.agent import Agent
from app.cancellation import CancellationToken
from app.session import delete_session, list_sessions, load_session, save_session
from app.web.event_bridge import WebEventBridge


class WebAgentSession:
    def __init__(
        self,
        agent: Agent,
        bridge: WebEventBridge,
        cancellation_token: CancellationToken,
    ):
        self.agent = agent
        self.bridge = bridge
        self._session_id = None
        self._lock = threading.Lock()
        self._permission_event = threading.Event()
        self._permission_result: str | None = None
        self._cancellation_token = cancellation_token

    def submit(self, message: str) -> dict[str, Any]:
        if self._lock.locked():
            return {
                "ok": False,
                "error": "Agent is already running.",
            }

        thread = threading.Thread(
            target=self._run_agent,
            args=(message,),
            name="web-agent-run",
            daemon=True,
        )
        thread.start()

        return {
            "ok": True,
            "message": "Agent run started.",
        }

    def respond_permission(self, action: str) -> dict[str, Any]:
        self._permission_result = action
        self._permission_event.set()

        return {
            "ok": True,
            "action": action,
        }

    def stop(self) -> dict[str, Any]:
        self._cancellation_token.cancel()
        return {
            "ok": True,
            "message": "Stop signal sent.",
        }

    def _wait_permission(self, tool_name: str, reason: str, arguments: dict, allow_dir: bool = False) -> str:
        self._permission_result = None
        self._permission_event.clear()

        self.bridge.publish(
            "permission_request",
            {
                "tool": tool_name,
                "reason": reason,
                "arguments": arguments,
                "allow_dir": allow_dir,
            },
        )

        self._permission_event.wait()
        return self._permission_result or "deny"

    def _run_agent(self, message: str) -> None:
        with self._lock:
            self._cancellation_token.clear()
            self.bridge.publish(
                "user_message",
                {
                    "content": message,
                },
            )

            full_answer: list[str] = []

            def on_token(token: str) -> None:
                if self._cancellation_token.cancelled:
                    raise InterruptedError("The user performs a cancel operation")
                full_answer.append(token)
                self.bridge.publish(
                    "assistant_token",
                    {
                        "token": token,
                    },
                )

            def on_tool(name: str, arguments: dict) -> None:
                self.bridge.publish(
                    "tool_display",
                    {
                        "name": name,
                        "arguments": arguments,
                    },
                )

            try:
                result = self.agent.chat(
                    message,
                    on_token=on_token,
                    on_tool=on_tool,
                    on_reasoning=None,
                    permission_handler=self._wait_permission,
                )

                self.bridge.publish(
                    "assistant_done",
                    {
                        "content": result or "".join(full_answer),
                    },
                )
                self._session_id = save_session(
                    self.agent.messages,
                    self.agent.llm.model,
                    self._session_id,
                )

            except InterruptedError:
                self.bridge.publish(
                    "agent_error",
                    {
                        "error": "Agent stopped by user.",
                        "error_type": "InterruptedError",
                    },
                )
                self._session_id = save_session(
                    self.agent.messages,
                    self.agent.llm.model,
                    self._session_id,
                )
            except Exception as e:
                self.bridge.publish(
                    "agent_error",
                    {
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

    def get_current(self) -> dict:
        return {
            "ok": True,
            "session_id": self._session_id,
            "messages": list(self.agent.messages),
        }

    def list_sessions(self):
        return {"ok": True, "sessions": list_sessions()}

    def new_session(self) -> dict:
        if self._lock.locked():
            self._cancellation_token.cancel()
        with self._lock:
            self.agent.messages.clear()
            self._session_id = None  # 下次 save 会自生成新 id
        return {"ok": True}

    def switch_session(self, session_id: str) -> dict:
        loaded = load_session(session_id)  # 返回 (messages, model) 或 None
        if loaded is None:
            return {"ok": False, "error": "Session not found"}

        # 若 Agent 正在跑 发送取消信号
        if self._lock.locked():
            self._cancellation_token.cancel()

        # 等_run_agent 走完
        with self._lock:
            messages, model = loaded
            self.agent.messages.clear()
            self.agent.messages.extend(messages)
            self.agent.llm.model = model
            self._session_id = session_id
        return {"ok": True, "session_id": session_id, "messages": messages}

    def delete_session(self, session_id: str) -> dict:
        deleted = delete_session(session_id)
        if not deleted:
            return {"ok": False, "error": "Session not found"}

        # 删的是当前会话 → 就地清空,回到「新会话」状态
        if session_id == self._session_id:
            if self._lock.locked():
                self._cancellation_token.cancel()
            with self._lock:
                self.agent.messages.clear()
                self._session_id = None

        return {"ok": True, "deleted": session_id, "current": self._session_id}
