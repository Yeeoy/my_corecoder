"""Sub-agent spawning (inspired by Claude Code's AgentTool).

The idea: for complex sub-tasks, spawn an independent agent with its own
conversation history and tool access. This lets the main agent delegate
work like "go research this codebase and report back" without polluting
its own context window.

The sub-agent runs to completion and returns a text summary.
"""

import time

from .base import Tool, ToolResult


class AgentTool(Tool):
    """Spawn an isolated sub-agent for a complex sub-task.

    The sub-agent gets its own context window and a copy of the parent's
    tools (minus this agent tool to prevent recursion).  Output is
    truncated at 5000 characters to avoid flooding the parent context.
    """

    name = "agent"
    description = (
        "Spawn a sub-agent to handle a complex sub-task independently. "
        "The sub-agent has its own context and tool access. Use this for: "
        "researching a codebase, implementing a multi-step change in isolation, "
        "or any task that would benefit from a fresh context window."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "What the sub-agent should accomplish",
            },
        },
        "required": ["task"],
    }

    # set by Agent.__init__ after construction
    _parent_agent = None
    supports_cancellation = True
    timeout_seconds = 120

    def execute(self, task: str, cancellation_token=None) -> ToolResult:
        """Spawn a sub-agent, run it to completion, and return its summary.

        Returns:
            ToolResult with:
            - ``ok``: False when the parent agent is not set or the
              sub-agent raised an exception.
            - ``content``: Sub-agent output, prefixed with
              ``"[Sub-agent completed]"``.
            - ``metadata``: tool, task, truncated, duration_ms.
        """
        start = time.perf_counter()

        if self._parent_agent is None:
            return ToolResult(
                ok=False,
                content="",
                error="Agent tool not initialized (no parent agent)",
                metadata={
                    "tool": self.name,
                    "task": task,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )

        # import here to avoid circular dep
        from ..agent import Agent

        parent = self._parent_agent
        sub = Agent(
            llm=parent.llm,
            tools=[t for t in parent.tools if t.name != "agent"],  # no recursive agents
            max_rounds=20,
            cancellation_token=cancellation_token,
            permission_manager=parent.permission_manager,
            events=parent.events,
        )

        try:
            result = sub.chat(task)
            duration_ms = int((time.perf_counter() - start) * 1000)

            # trim long results to avoid blowing up parent's context
            truncated = len(result) > 5000
            if truncated:
                result = result[:4500] + "\n... (sub-agent output truncated)"

            return ToolResult(
                ok=True,
                content=f"[Sub-agent completed]\n{result}",
                error=None,
                metadata={
                    "tool": self.name,
                    "task": task,
                    "truncated": truncated,
                    "duration_ms": duration_ms,
                },
            )
        except InterruptedError:
            raise
        except Exception as e:
            return ToolResult(
                ok=False,
                content="",
                error=f"Sub-agent error: {type(e).__name__}: {e}",
                metadata={
                    "tool": self.name,
                    "task": task,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
