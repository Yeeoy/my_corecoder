from collections import defaultdict
from collections.abc import Callable
from typing import Any

EventHandler = Callable[[dict[str, Any]], None]


class EventName:
    USER_MESSAGE = "user_message"

    BEFORE_LLM_CALL = "before_llm_call"
    AFTER_LLM_CALL = "after_llm_call"

    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"
    TOOL_ERROR = "tool_error"
    TOOL_TIMEOUT = "tool_timeout"

    AGENT_FINISH = "agent_finish"
    AGENT_ERROR = "agent_error"

    BEFORE_CONTEXT_COMPRESS = "before_context_compress"
    AFTER_CONTEXT_COMPRESS = "after_context_compress"

    PERMISSION_CHECK = "permission_check"
    PERMISSION_CONFIRMED = "permission_confirmed"
    PERMISSION_DENIED = "permission_denied"

    TODO_UPDATED = "todo_updated"


class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def on(self, event_name: str, handler: EventHandler) -> None:
        self._handlers[event_name].append(handler)

    def emit(self, event_name: str, payload: dict[str, Any] | None = None) -> None:
        payload = dict(payload or {})
        payload["_event"] = event_name
        handles = self._handlers.get(event_name, []) + self._handlers.get("*", [])
        for handler in handles:
            try:
                handler(payload)
            except Exception as e:
                print(f"Error in event handler for {event_name}:{e}")
