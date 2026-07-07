import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path

from app.events import EventName

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "token",
    "password",
    "secret",
    "authorization",
    "cookie",
}


class RunLogger:
    def __init__(self):
        self.log_dir = Path.home() / ".my_corecoder" / "runs"
        self.run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        self.log_file = self.log_dir / (self.run_id + ".jsonl")

        self.log_dir.mkdir(parents=True, exist_ok=True)

    def handle(self, payload: dict):
        payload = dict(payload)
        event = payload.pop("_event", "unknown")

        record = {
            "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "event": event,
            **self._sanitize(payload),
        }

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except FileNotFoundError as e:
            logger.error("Log file path does not exist: %s", e)
        except PermissionError as e:
            logger.error("No write permission: %s", e)
        except OSError as e:
            logger.error("Disk/path exception: %s", e)
        except Exception as e:
            logger.error("Write log unknown error: %s", e)

    def _sanitize(self, value):
        return self._sanitize_value(value)

    def _sanitize_value(self, value, key: str | None = None):
        if key and self._is_sensitive_key(key):
            return "***REDACTED***"

        if isinstance(value, dict):
            return {k: self._sanitize_value(v, k) for k, v in value.items()}

        if isinstance(value, list):
            items = [self._sanitize_value(v) for v in value[:50]]
            if len(value) > 50:
                items.append(f"... truncated list ({len(value)} items total)")
            return items

        if isinstance(value, str):
            if len(value) > 1000:
                return value[:1000] + f"... truncated ({len(value)} chars total)"
            return value

        if isinstance(value, (int, float, bool)) or value is None:
            return value

        return str(value)

    def _is_sensitive_key(self, key: str) -> bool:
        key_lower = key.lower()
        return (
            key_lower in SENSITIVE_KEYS
            or key_lower.endswith("_api_key")
            or key_lower.endswith("_token")
            or key_lower in {"access_token", "refresh_token", "id_token"}
            or "authorization" in key_lower
            or "password" in key_lower
            or "secret" in key_lower
            or "cookie" in key_lower
            or key_lower.endswith("_key")
        )

    def list_run_ids(self, limit: int = 20) -> list[str]:
        if not self.log_dir.exists():
            return []

        logs = sorted(
            [p.stem for p in self.log_dir.glob("*.jsonl")],
            reverse=True,
        )
        return logs[:limit]

    def load_run(self, run_id: str) -> list[dict] | str:
        if not self.log_dir.exists():
            return "Log dir doesn't exist"

        if run_id.endswith(".jsonl"):
            run_id = run_id[:-6]

        full_file_path = (self.log_dir / f"{run_id}.jsonl").resolve()
        log_root = self.log_dir.resolve()

        if not full_file_path.is_relative_to(log_root):
            return "Invalid log id"

        if full_file_path.exists():
            logs = []
            with open(full_file_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        logs.append(json.loads(line))
                    except json.JSONDecodeError:
                        logs.append({"event": "log_parse_error", "raw": line[:200]})
            return logs
        return "Log file doesn't exist"

    def load_last_run(self) -> list[dict] | str:
        runs = self.list_run_ids()
        if not runs:
            return "No logs found."
        return self.load_run(runs[0])

    def load_run_tools(self, run_id: str) -> list[dict] | str:
        logs = self.load_run(run_id)

        if isinstance(logs, str):
            return logs

        tool_logs = self._filter_tool_events(logs)
        return tool_logs or f"No tools found in run_id {run_id}"

    def load_last_run_tools(self) -> list[dict] | str:
        runs = self.list_run_ids()
        if not runs:
            return "No logs found."
        return self.load_run_tools(runs[0])

    def _filter_tool_events(self, logs: list[dict]) -> list[dict]:
        tool_events = {
            EventName.BEFORE_TOOL_CALL,
            EventName.AFTER_TOOL_CALL,
            EventName.TOOL_ERROR,
            EventName.TOOL_TIMEOUT,
        }

        return [log for log in logs if log.get("event") in tool_events]

    def format_run_tools(self, run_id: str) -> str:
        logs = self.load_run_tools(run_id)

        if isinstance(logs, str):
            return logs

        if not logs:
            return f"No tools found in run_id {run_id}"

        lines = [f"Run Tools: {len(logs)} events\n"]

        for index, log in enumerate(logs, start=1):
            event = log.get("event", "unknown")
            ts = log.get("ts", "")

            lines.append(f"{index}. {ts} {event}")
            lines.append(self._format_tool_event(log))
            lines.append("")

        return "\n".join(lines)

    def format_last_run_tools(self) -> str:
        runs = self.list_run_ids()
        if not runs:
            return "No logs found."

        return self.format_run_tools(runs[0])

    def format_run(self, run_id: str) -> str:
        logs = self.load_run(run_id)

        if isinstance(logs, str):
            return logs

        if not logs:
            return f"No events found in run_id {run_id}"

        lines = [f"Run: {run_id}", f"Events: {len(logs)}\n"]

        for index, log in enumerate(logs, start=1):
            event = log.get("event", "unknown")
            ts = log.get("ts", "")

            lines.append(f"{index}. {ts} {event}")
            lines.append(self._format_event(log))
            lines.append("")

        return "\n".join(lines)

    def format_last_run(self) -> str:
        runs = self.list_run_ids()
        if not runs:
            return "No logs found."

        return self.format_run(runs[0])

    def format_current_run(self) -> str:
        if not self.log_file.exists():
            return f"Current run: {self.run_id}\nNo events logged yet."

        return self.format_run(self.run_id)

    def format_current_run_tools(self) -> str:
        if not self.log_file.exists():
            return f"Current run: {self.run_id}\nNo events logged yet."

        return self.format_run_tools(self.run_id)

    def format_current_run_errors(self) -> str:
        if not self.log_file.exists():
            return f"Current run: {self.run_id}\nNo events logged yet."

        return self.format_run_errors(self.run_id)

    def _format_event(self, log: dict) -> str:
        event = log.get("event", "unknown")

        if event == EventName.BEFORE_TOOL_CALL:
            return self._format_tool_event(log)

        if event == EventName.AFTER_TOOL_CALL:
            return self._format_tool_event(log)

        if event in (EventName.TOOL_ERROR, EventName.TOOL_TIMEOUT):
            return self._format_tool_event(log)

        if event == EventName.BEFORE_LLM_CALL:
            return (
                f"   round: {log.get('round_index')}/{log.get('max_rounds')}\n"
                f"   messages: {log.get('message_count')}\n"
                f"   tools: {log.get('tool_count')}"
            )

        if event == EventName.AFTER_LLM_CALL:
            tool_calls = log.get("tool_calls") or []

            if tool_calls:
                return f"   tool_calls: {', '.join(tool_calls)}"

            return (
                f"   content: {log.get('content_chars')} chars\n"
                f"   preview: {self._shorten(log.get('content_preview', ''))}"
            )

        if event == EventName.USER_MESSAGE:
            return f"   input: {self._shorten(log.get('input_preview', ''))}"

        if event == EventName.BEFORE_CONTEXT_COMPRESS:
            return f"   messages: {log.get('message_count')}"

        if event == EventName.AFTER_CONTEXT_COMPRESS:
            return (
                f"   compressed: {log.get('compressed')}\n"
                f"   messages: {log.get('before_message_count')} -> {log.get('after_message_count')}"
            )

        if event == EventName.AGENT_FINISH:
            return f"   {log.get('message', 'finished')}"

        if event == EventName.AGENT_ERROR:
            error_type = log.get("error_type") or "AgentError"
            return f"   error: {error_type}: {log.get('error')}"

        return f"   {log}"

    def _format_tool_event(self, log: dict) -> str:
        event = log.get("event", "unknown")

        if event == EventName.BEFORE_TOOL_CALL:
            return f"   tool: {log.get('name')}\n   args: {self._shorten(str(log.get('arguments', {})), 300)}"

        if event == EventName.AFTER_TOOL_CALL:
            return (
                f"   tool: {log.get('name')} finished in {log.get('duration_ms')}ms\n"
                f"   result: {log.get('result_chars')} chars\n"
                f"   preview: {self._shorten(log.get('result_preview', ''))}"
            )

        if event in (EventName.TOOL_ERROR, EventName.TOOL_TIMEOUT):
            error_type = log.get("error_type") or "ToolError"
            return f"   tool: {log.get('name')}\n   error: {error_type}: {log.get('error')}"

        return f"   {log}"

    @staticmethod
    def _shorten(text: str, limit: int = 200) -> str:
        text = str(text).replace("\n", "\\n")

        if len(text) > limit:
            return text[:limit] + "..."

        return text

    def load_run_errors(self, run_id: str) -> list[dict] | str:
        logs = self.load_run(run_id)

        if isinstance(logs, str):
            return logs

        error_logs = self._filter_error_events(logs)
        return error_logs or f"No errors found in run_id {run_id}"

    def load_last_run_errors(self) -> list[dict] | str:
        runs = self.list_run_ids()
        if not runs:
            return "No logs found."
        return self.load_run_errors(runs[0])

    def format_run_errors(self, run_id: str) -> str:
        logs = self.load_run_errors(run_id)

        if isinstance(logs, str):
            return logs

        if not logs:
            return f"No errors found in run_id {run_id}"

        lines = [f"Run Errors: {len(logs)} events\n"]

        for index, log in enumerate(logs, start=1):
            event = log.get("event", "unknown")
            ts = log.get("ts", "")

            lines.append(f"{index}. {ts} {event}")
            lines.append(self._format_event(log))
            lines.append("")

        return "\n".join(lines)

    def format_last_run_errors(self) -> str:
        runs = self.list_run_ids()
        if not runs:
            return "No logs found."

        return self.format_run_errors(runs[0])

    def _filter_error_events(self, logs: list[dict]) -> list[dict]:
        error_events = {
            EventName.TOOL_ERROR,
            EventName.TOOL_TIMEOUT,
            EventName.AGENT_ERROR,
        }

        return [log for log in logs if log.get("event") in error_events]
