import concurrent.futures
import inspect

from app.context import ContextManager
from app.llm import LLM
from app.prompt import system_prompt
from app.tools import AgentTool
from app.tools.base import Tool


class Agent:
    def __init__(
        self,
        llm: LLM,
        tools: list[Tool],
        max_content_tokens: int = 128_000,
        max_rounds: int = 50,
    ):
        self.llm = llm
        self.tools = tools
        self._tool_by_name = {tool.name: tool for tool in self.tools}
        self.messages: list[dict] = []
        self.context = ContextManager(max_tokens=max_content_tokens)
        self.max_content_tokens = max_content_tokens
        self.max_rounds = max_rounds
        self._system = system_prompt(self.tools)

        # sub agent
        for t in self.tools:
            if isinstance(t, AgentTool):
                t._parent_agent = self

    def _full_messages(self) -> list[dict]:
        return [{"role": "system", "content": self._system}] + self.messages

    def _tool_schemas(self) -> list[dict]:
        return [t.schema() for t in self.tools]

    def chat(self, user_input: str, on_token=None, on_tool=None, on_reasoning=None) -> str:
        self.messages.append({"role": "user", "content": user_input})
        self.context.maybe_compress(self.messages, self.llm)

        for _ in range(self.max_rounds):
            resp = self.llm.chat(
                self._full_messages(),
                self._tool_schemas(),
                on_token=on_token,
                on_reasoning=on_reasoning,
            )

            # no tool calls -> LLM is done, return text
            if not resp.tool_calls:
                self.messages.append(resp.message)
                return resp.content

            self.messages.append(resp.message)

            try:
                if len(resp.tool_calls) == 1:
                    tc = resp.tool_calls[0]
                    if on_tool:
                        on_tool(tc.name, tc.arguments)
                    result = self._exec_tool(tc)
                    print(result)
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        }
                    )
                else:
                    results = self._exec_tools_parallel(resp.tool_calls, on_tool)
                    for tc, result in zip(resp.tool_calls, results, strict=False):
                        self.messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": result,
                            }
                        )
            except KeyboardInterrupt:
                self._answer_pending_tool_calls(self.messages, self.llm)
                print("[red]KeyboardInterrupt[/red]")
                raise

            # compress if tool_outputs are big
            self.context.maybe_compress(self.messages, self.llm)
        return "reached maximum tool-call rounds"

    def _exec_tool(self, tc) -> str:
        tool = self._tool_by_name.get(tc.name)
        if tool is None:
            return f"Error: unknown tool '{tc.name}'"

        try:
            inspect.signature(tool.execute).bind(**tc.arguments)
        except TypeError as e:
            return f"Error: bad arguments for {tc.name}: {e}"

        try:
            return tool.execute(**tc.arguments)
        except Exception as e:
            return f"Error executing {tc.name}: {e}"

    def _exec_tools_parallel(self, tool_calls, on_tool=None) -> list[str]:
        for tc in tool_calls:
            if on_tool:
                on_tool(tc.name, tc.arguments)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(self._exec_tool, tc) for tc in tool_calls]
            return [f.result() for f in futures]

    def _answer_pending_tool_calls(self, tool_calls):
        answered = {m.get("tool_call_id") for m in self.messages if m.get("tole") == "tool"}
        for tc in tool_calls:
            if tc.id not in answered:
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": ["interrupted"],
                    }
                )

    def reset(self):
        self.messages.clear()
