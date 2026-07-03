import threading
from typing import Any

from app.agent import Agent
from app.web.event_bridge import WebEventBridge


class WebAgentSession:
    def __init__(self, agent: Agent, bridge: WebEventBridge):
        self.agent = agent
        self.bridge = bridge
        self._lock = threading.Lock()
        self._permission_event = threading.Event()
        self._permission_result: str | None = None
        self._stop_event = threading.Event()

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
        self._stop_event.set()
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
            self._stop_event.clear()
            self.bridge.publish(
                "user_message",
                {
                    "content": message,
                },
            )

            full_answer: list[str] = []

            def on_token(token: str) -> None:
                if self._stop_event.is_set():
                    raise InterruptedError("Agent stopped by user.")
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

            except InterruptedError:
                self.bridge.publish(
                    "agent_error",
                    {
                        "error": "Agent stopped by user.",
                        "error_type": "InterruptedError",
                    },
                )
            except Exception as e:
                self.bridge.publish(
                    "agent_error",
                    {
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
