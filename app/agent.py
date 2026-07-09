import concurrent.futures
import inspect
import time

from app.cancellation import CancellationToken
from app.context import ContextManager
from app.events import EventBus, EventName
from app.llm import LLM
from app.permission import PermissionManager
from app.prompt import system_prompt
from app.tools import AgentTool
from app.tools.base import Tool, ToolResult


class Agent:
    def __init__(
        self,
        llm: LLM,
        tools: list[Tool],
        max_content_tokens: int = 128_000,
        max_rounds: int = 50,
        events: EventBus | None = None,
        extra_system_context=None,
        permission_manager: PermissionManager | None = None,
        runtime_state=None,
        cancellation_token: CancellationToken | None = None,
    ):
        self.llm = llm
        self.tools = tools
        self._tool_by_name = {tool.name: tool for tool in self.tools}
        self.messages: list[dict] = []
        self.context = ContextManager(max_tokens=max_content_tokens)
        self.max_content_tokens = max_content_tokens
        self.max_rounds = max_rounds
        self.events = events or EventBus()
        self._system = system_prompt(self.tools)
        self.extra_system_context = extra_system_context
        self.permission_manager = permission_manager or PermissionManager()
        self.runtime_state = runtime_state
        self._permission_handler = None
        self._cancellation_token = cancellation_token

        # sub agent
        for t in self.tools:
            if isinstance(t, AgentTool):
                t._parent_agent = self

    def _full_messages(self) -> list[dict]:
        system = self._system
        if self.extra_system_context:
            extra = self.extra_system_context()
            if extra:
                system += f"\n\n{extra}"
        return [{"role": "system", "content": system}] + self.messages

    def _tool_schemas(self) -> list[dict]:
        return [t.schema() for t in self.tools]

    def _maybe_compress_context(self):
        before_messages = len(self.messages)

        runtime_state = ""
        if self.runtime_state:
            runtime_state = self.runtime_state.render()

        self.events.emit(
            EventName.BEFORE_CONTEXT_COMPRESS,
            {
                "message_count": before_messages,
            },
        )

        result = self.context.maybe_compress(
            self.messages,
            self.llm,
            runtime_state=runtime_state,
        )

        self.events.emit(
            EventName.AFTER_CONTEXT_COMPRESS,
            {
                "compressed": result.compressed,
                "layers": result.layers,
                "before_tokens": result.before_tokens,
                "after_tokens": result.after_tokens,
                "before_message_count": before_messages,
                "after_message_count": len(self.messages),
            },
        )

    def chat(self, user_input: str, on_token=None, on_tool=None, on_reasoning=None, permission_handler=None) -> str:
        self._permission_handler = permission_handler
        self.messages.append({"role": "user", "content": user_input})
        self.events.emit(
            EventName.USER_MESSAGE,
            {
                "input_chars": len(user_input),
                "input_preview": user_input[:200],
            },
        )
        self._maybe_compress_context()

        for _round_index in range(self.max_rounds):
            if self._cancellation_token and self._cancellation_token.cancelled:
                raise InterruptedError("Agent stopped by user")
            self.events.emit(
                EventName.BEFORE_LLM_CALL,
                {
                    "round_index": _round_index + 1,
                    "max_rounds": self.max_rounds,
                    "message_count": len(self.messages),
                    "tool_count": len(self.tools),
                },
            )
            resp = self.llm.chat(
                self._full_messages(),
                self._tool_schemas(),
                on_token=on_token,
                on_reasoning=on_reasoning,
            )

            # no tool calls -> LLM is done, return text
            if not resp.tool_calls:
                self.messages.append(resp.message)
                self.events.emit(
                    EventName.AFTER_LLM_CALL,
                    {
                        "round_index": _round_index + 1,
                        "content_chars": len(resp.content or ""),
                        "content_preview": (resp.content or "")[:200],
                        "tool_call_count": len(resp.tool_calls),
                        "tool_calls": [tc.name for tc in resp.tool_calls],
                    },
                )
                self.events.emit(EventName.AGENT_FINISH, {"message": "Agent finished."})
                return resp.content

            self.messages.append(resp.message)
            self.events.emit(
                EventName.AFTER_LLM_CALL,
                {
                    "round_index": _round_index + 1,
                    "content_chars": len(resp.content or ""),
                    "content_preview": (resp.content or "")[:200],
                    "tool_call_count": len(resp.tool_calls),
                    "tool_calls": [tc.name for tc in resp.tool_calls],
                },
            )

            try:
                if len(resp.tool_calls) == 1:
                    tc = resp.tool_calls[0]
                    if on_tool:
                        on_tool(tc.name, tc.arguments)
                    result = self._exec_tool(tc)
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result.to_llm_content(),
                        }
                    )
                else:
                    results = self._exec_tools_parallel(resp.tool_calls, on_tool)
                    for tc, result in zip(resp.tool_calls, results, strict=False):
                        self.messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": result.to_llm_content(),
                            }
                        )
            except KeyboardInterrupt:
                self._answer_pending_tool_calls(resp.tool_calls)
                raise
            except Exception as e:
                self.events.emit(
                    EventName.AGENT_ERROR,
                    {
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                raise

            # compress if tool_outputs are big
            self._maybe_compress_context()

        self.events.emit(
            EventName.AGENT_ERROR,
            {
                "error": "reached maximum tool-call rounds",
                "error_type": None,
            },
        )
        return "reached maximum tool-call rounds"

    def _check_permission(self, tool_name: str, arguments: dict) -> str | None:
        decision = self.permission_manager.check_tool_call(tool_name, arguments)

        self.events.emit(
            EventName.PERMISSION_CHECK,
            {
                "tool": tool_name,
                "decision": decision.action,
                "reason": decision.reason,
                "arguments_preview": str(arguments)[:300],
            },
        )

        if decision.action == "allow":
            return None

        if decision.action == "deny":
            message = (
                f"Permission denied: {decision.reason}\n"
                "Do not retry the same destructive intent with an alternative command."
            )
            self.events.emit(
                EventName.PERMISSION_DENIED,
                {
                    "tool": tool_name,
                    "reason": decision.reason,
                    "arguments_preview": str(arguments)[:300],
                },
            )
            return message

        if decision.action == "confirm":
            allow_dir = tool_name == "read_file"

            if self._permission_handler:
                answer = self._permission_handler(tool_name, decision.reason, arguments, allow_dir)
            else:
                print("\n⚠️ Permission required")
                print(f"Tool: {tool_name}")
                print(f"Reason: {decision.reason}")
                print(f"Arguments: {arguments}")
                if allow_dir:
                    answer = input("Allow this tool call? [y/N/a=allow this directory for session]: ").strip().lower()
                else:
                    answer = input("Allow this tool call? [y/N]: ").strip().lower()

            if answer == "allow":
                self.events.emit(
                    EventName.PERMISSION_CONFIRMED,
                    {
                        "tool": tool_name,
                        "reason": decision.reason,
                        "arguments_preview": str(arguments)[:300],
                    },
                )
                return None

            if answer == "allow_dir" and allow_dir:
                file_path = arguments.get("file_path") or arguments.get("path")

                if not file_path:
                    message = "Permission denied: cannot determine read_file path for directory authorization"
                    self.events.emit(
                        EventName.PERMISSION_DENIED,
                        {
                            "tool": tool_name,
                            "reason": message,
                            "arguments_preview": str(arguments)[:300],
                        },
                    )
                    return message

                grant_message = self.permission_manager.allow_read_dir_for_session(file_path)

                self.events.emit(
                    EventName.PERMISSION_CONFIRMED,
                    {
                        "tool": tool_name,
                        "reason": grant_message,
                        "arguments_preview": str(arguments)[:300],
                    },
                )

                return None

            message = (
                f"Permission denied by user: {decision.reason}\n"
                "Do not retry the same destructive intent with an alternative command."
            )
            self.events.emit(
                EventName.PERMISSION_DENIED,
                {
                    "tool": tool_name,
                    "reason": decision.reason,
                    "arguments_preview": str(arguments)[:300],
                },
            )
            return message

        return None

    def _exec_tool(self, tc) -> ToolResult:
        started = time.perf_counter()
        self.events.emit(
            EventName.BEFORE_TOOL_CALL,
            {
                "tool_call_id": tc.id,
                "name": tc.name,
                "arguments": tc.arguments,
            },
        )
        tool = self._tool_by_name.get(tc.name)
        if tool is None:
            self.events.emit(
                EventName.TOOL_ERROR,
                {
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "error": f"Error: unknown tool '{tc.name}'",
                    "error_type": "UnknownToolError",
                },
            )
            return ToolResult(
                ok=False,
                content="",
                error=f"Error: unknown tool '{tc.name}'",
                metadata={},
            )

        try:
            inspect.signature(tool.execute).bind(**tc.arguments)
        except TypeError as e:
            self.events.emit(
                EventName.TOOL_ERROR,
                {
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return ToolResult(
                ok=False,
                content="",
                error=f"Bad arguments for {tc.name}: {e}",
                metadata={},
            )

        permission_error = self._check_permission(tc.name, tc.arguments)
        if permission_error:
            self.events.emit(
                EventName.AFTER_TOOL_CALL,
                {
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "result_chars": len(permission_error),
                    "result_preview": permission_error,
                    "success": False,
                },
            )
            return ToolResult(
                ok=False,
                content="",
                error=permission_error,
                metadata={},
            )
        tool_call_token = None
        tool_arguments = dict(tc.arguments)

        if getattr(tool, "supports_cancellation", False):
            tool_call_token = CancellationToken(parent_token=self._cancellation_token)
            tool_arguments["cancellation_token"] = tool_call_token

        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        pool_shutdown_done = False

        try:
            future = pool.submit(tool.execute, **tool_arguments)
            result = future.result(timeout=tool.timeout_seconds)
            self.events.emit(
                EventName.AFTER_TOOL_CALL,
                {
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "ok": result.ok,
                    "error": result.error,
                    "duration_ms": result.metadata.get("duration_ms", int((time.perf_counter() - started) * 1000)),
                    "result_chars": len(result.content),
                    "result_preview": result.content[:1000],
                },
            )
            return result
        except concurrent.futures.TimeoutError as e:
            if tool_call_token is not None:
                tool_call_token.cancel()
                pool.shutdown(wait=True, cancel_futures=True)
                pool_shutdown_done = True

            self.events.emit(
                EventName.TOOL_TIMEOUT,
                {
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "error": f"Tool '{tc.name}' timed out after {tool.timeout_seconds}s",
                    "error_type": type(e).__name__,
                },
            )
            return ToolResult(
                ok=False,
                content="",
                error=f"Tool '{tc.name}' timed out after {tool.timeout_seconds}s",
                metadata={},
            )
        except Exception as e:
            self.events.emit(
                EventName.TOOL_ERROR,
                {
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return ToolResult(
                ok=False,
                content="",
                error=f"Error executing {tc.name}: {type(e).__name__}: {e}",
                metadata={},
            )
        finally:
            if not pool_shutdown_done:
                pool.shutdown(wait=False, cancel_futures=True)

    def _exec_tools_parallel(self, tool_calls, on_tool=None) -> list[ToolResult]:
        # Run tools sequentially if any tool requires permission
        if self._should_run_tools_sequentially(tool_calls):
            results = []

            for tc in tool_calls:
                if on_tool:
                    on_tool(tc.name, tc.arguments)

                results.append(self._exec_tool(tc))

            return results

        for tc in tool_calls:
            if on_tool:
                on_tool(tc.name, tc.arguments)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(self._exec_tool, tc) for tc in tool_calls]
            return [f.result() for f in futures]

    def _should_run_tools_sequentially(self, tool_calls) -> bool:
        for tc in tool_calls:
            if tc.name == "todo":
                return True

            decision = self.permission_manager.check_tool_call(tc.name, tc.arguments)
            if decision.action != "allow":
                return True

        return False

    def _answer_pending_tool_calls(self, tool_calls):
        answered = {m.get("tool_call_id") for m in self.messages if m.get("role") == "tool"}
        for tc in tool_calls:
            if tc.id not in answered:
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": "interrupted",
                    }
                )

    def reset(self):
        self.messages.clear()

    @property
    def tool_by_name(self):
        return self._tool_by_name
