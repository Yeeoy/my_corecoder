from app.events import EventName


class TraceCollector:
    def __init__(self, max_events: int = 200):
        self.events: list[dict] = []
        self.max_events = max_events

    def handle(self, payload: dict):
        event = payload.get("_event")
        if not event:
            return

        if event == EventName.USER_MESSAGE:
            self.clear()

        self.events.append(dict(payload))

        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events :]

    def format(self) -> str:
        if not self.events:
            return "No trace events yet."
        lines = [f"Trace: {len(self.events)} events\n"]

        for index, payload in enumerate(self.events, start=1):
            event = payload.get("_event", "unknown")
            lines.append(f"{index}. {event}")
            lines.append(self._format_payload(event, payload))
            lines.append("")
        return "\n".join(lines)

    def format_tools(self) -> str:
        tool_events = [
            e
            for e in self.events
            if e.get("_event")
            in [
                EventName.BEFORE_TOOL_CALL,
                EventName.AFTER_TOOL_CALL,
                EventName.TOOL_ERROR,
            ]
        ]

        if not tool_events:
            return "No tool events in current trace."

        lines = [f"Tool Trace: {len(tool_events)} events\n"]

        for index, payload in enumerate(tool_events, start=1):
            event = payload.get("_event", "unknown")
            lines.append(f"{index}. {event}")
            lines.append(self._format_payload(event, payload))
            lines.append("")

        return "\n".join(lines)

    def format_errors(self) -> str:
        error_events = [
            e
            for e in self.events
            if e.get("_event")
            in [
                EventName.TOOL_ERROR,
                EventName.AGENT_ERROR,
            ]
        ]

        if not error_events:
            return "No error events in current trace."

        lines = [f"Error Trace: {len(error_events)} events\n"]

        for index, payload in enumerate(error_events, start=1):
            event = payload.get("_event", "unknown")
            lines.append(f"{index}. {event}")
            lines.append(self._format_payload(event, payload))
            lines.append("")

        return "\n".join(lines)

    def _format_payload(self, event: str, payload: dict) -> str:
        if event == EventName.USER_MESSAGE:
            return f"   input: {payload.get('input_preview', '')}"

        if event == EventName.BEFORE_LLM_CALL:
            return (
                f"   round: {payload.get('round_index')}/{payload.get('max_rounds')}\n"
                f"   messages: {payload.get('message_count')}\n"
                f"   tools: {payload.get('tool_count')}"
            )

        if event == EventName.AFTER_LLM_CALL:
            tool_calls = payload.get("tool_calls") or []
            if tool_calls:
                return f"   tool_calls: {', '.join(tool_calls)}"

            preview = payload.get("content_preview", "")
            return f"   content: {payload.get('content_chars')} chars\n   preview: {self._shorten(preview)}"

        if event == EventName.BEFORE_TOOL_CALL:
            return f"   tool: {payload.get('name')}\n   args: {payload.get('arguments', {})}"

        if event == EventName.AFTER_TOOL_CALL:
            return (
                f"   tool: {payload.get('name')} finished in {payload.get('duration_ms')}ms\n"
                f"   result: {payload.get('result_chars')} chars\n"
                f"   preview: {self._shorten(payload.get('result_preview', ''))}"
            )

        if event == EventName.TOOL_ERROR:
            error_type = payload.get("error_type") or "ToolError"
            return f"   tool: {payload.get('name')}\n   error: {error_type}: {payload.get('error')}"

        if event == EventName.AGENT_FINISH:
            return f"   {payload.get('message', 'finished')}"

        if event == EventName.AGENT_ERROR:
            error_type = payload.get("error_type") or "AgentError"
            return f"   error: {error_type}: {payload.get('error')}"

        if event == EventName.BEFORE_CONTEXT_COMPRESS:
            return f"   messages: {payload.get('message_count')}"

        if event == EventName.AFTER_CONTEXT_COMPRESS:
            layers = payload.get("layers") or []
            layers_text = ", ".join(layers) if layers else "none"

            return (
                f"   compressed: {payload.get('compressed')}\n"
                f"   layers: {layers_text}\n"
                f"   tokens: {payload.get('before_tokens')} -> {payload.get('after_tokens')}\n"
                f"   messages: {payload.get('before_message_count')} -> {payload.get('after_message_count')}"
            )

        if event == EventName.PERMISSION_CHECK:
            return (
                f"   tool: {payload.get('tool')}\n"
                f"   decision: {payload.get('decision')}\n"
                f"   reason: {payload.get('reason')}"
            )

        if event == EventName.PERMISSION_CONFIRMED:
            return f"   tool: {payload.get('tool')}\n   confirmed: {payload.get('reason')}"

        if event == EventName.PERMISSION_DENIED:
            return f"   tool: {payload.get('tool')}\n   denied: {payload.get('reason')}"

        return f"   {payload}"

    @staticmethod
    def _shorten(text: str, limit: int = 200) -> str:
        text = text.replace("\n", "\\n")
        if len(text) > limit:
            return text[:limit] + "..."
        return text

    def clear(self):
        self.events = []
