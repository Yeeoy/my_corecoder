import asyncio
import concurrent.futures
import json
import logging
import os
import threading
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from app.mcp_adapter import MCPToolAdapter
from app.mcp_config import MCPServerConfig

logger = logging.getLogger(__name__)


@dataclass
class MCPServerRuntime:
    config: MCPServerConfig
    stack: AsyncExitStack
    session: ClientSession
    tools: list[Any]
    authenticated: bool = False


class MCPClientManager:
    def __init__(
        self,
        configs: list[MCPServerConfig],
        workspace_root: str | Path,
        call_timeout_seconds: float = 30.0,
    ):
        self.configs = {cfg.name: cfg for cfg in configs}
        self.workspace_root = Path(workspace_root).resolve()
        self.call_timeout_seconds = call_timeout_seconds

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

        self._runtimes: dict[str, MCPServerRuntime] = {}
        self._started = False

    def _get_auth_env(self, server_name: str) -> dict[str, str] | None:
        """Return auth env vars for a server, or None if no auth_key configured or key missing."""
        cfg = self.configs.get(server_name)
        if not cfg or not cfg.auth_key:
            return None

        value = os.environ.get(cfg.auth_key, "")
        if not value:
            return None

        return {cfg.auth_key: value}

    def start_sync(self) -> list[MCPToolAdapter]:
        self._ensure_loop()
        return self._run_sync(self.start())

    async def start(self) -> list[MCPToolAdapter]:
        if self._started:
            return self._build_tool_adapters()

        for server_name, cfg in self.configs.items():
            try:
                runtime = await self._start_server(cfg)
                self._runtimes[server_name] = runtime
                logger.info("Connected %s: %d tools", server_name, len(runtime.tools))
            except Exception as e:
                logger.error("Failed to start server %s: %s", server_name, e)

        self._started = True
        return self._build_tool_adapters()

    async def _start_server(self, cfg: MCPServerConfig, auth_env: dict[str, str] | None = None) -> MCPServerRuntime:
        stack = AsyncExitStack()

        try:
            env = dict(cfg.env) if cfg.env else {}
            if auth_env:
                env.update(auth_env)

            params = StdioServerParameters(
                command=cfg.command,
                args=cfg.args,
                env=env or None,
            )

            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))

            await session.initialize()
            result = await session.list_tools()

            return MCPServerRuntime(
                config=cfg,
                stack=stack,
                session=session,
                tools=result.tools,
                authenticated=bool(auth_env),
            )
        except Exception:
            await stack.aclose()
            raise

    def _build_tool_adapters(self) -> list[MCPToolAdapter]:
        adapters: list[MCPToolAdapter] = []

        for server_name, runtime in self._runtimes.items():
            for tool in runtime.tools:
                adapters.append(
                    MCPToolAdapter(
                        server_name=server_name,
                        tool_name=tool.name,
                        description=tool.description or "",
                        input_schema=tool.inputSchema,
                        manager=self,
                    )
                )

        return adapters

    def call_tool_sync(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        self._ensure_loop()
        cfg = self.configs.get(server_name)
        timeout = cfg.timeout_seconds if cfg and cfg.timeout_seconds else self.call_timeout_seconds
        return self._run_sync(
            self.call_tool(
                server_name=server_name,
                tool_name=tool_name,
                arguments=arguments,
            ),
            timeout=timeout,
        )

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        runtime = self._runtimes.get(server_name)

        if runtime is None:
            return f"Error: MCP server not connected: {server_name}"

        try:
            result = await runtime.session.call_tool(tool_name, arguments=arguments)
            return self._format_tool_result(result)
        except Exception as e:
            error_msg = str(e)

            # If 429 rate limit, try reconnection with API key
            if "429" in error_msg or "rate" in error_msg.lower():
                upgraded = await self._try_auth_reconnect(server_name)
                if upgraded:
                    logger.info("Reconnected %s with API key, retrying...", server_name)
                    new_runtime = self._runtimes.get(server_name)
                    if new_runtime:
                        try:
                            result = await new_runtime.session.call_tool(tool_name, arguments=arguments)
                            return self._format_tool_result(result)
                        except Exception as retry_e:
                            return f"Error calling MCP tool {server_name}/{tool_name} (after auth retry): {retry_e}"

            return f"Error calling MCP tool {server_name}/{tool_name}: {e}"

    async def _try_auth_reconnect(self, server_name: str) -> bool:
        """Reconnect a server with API key. Returns True if reconnected."""
        runtime = self._runtimes.get(server_name)
        if not runtime:
            return False

        if runtime.authenticated:
            return False

        auth_env = self._get_auth_env(server_name)
        if not auth_env:
            return False

        with suppress(Exception):
            await runtime.stack.aclose()

        try:
            new_runtime = await self._start_server(runtime.config, auth_env=auth_env)
            self._runtimes[server_name] = new_runtime
            return True
        except Exception as e:
            logger.error("Failed to reconnect %s with auth: %s", server_name, e)
            return False

    def close_sync(self) -> None:
        if not self._loop:
            return

        try:
            self._run_sync(self.close(), timeout=10.0)
        except Exception as e:
            logger.error("Error during shutdown: %s", e)

        if self._loop.is_running():
            self._loop.call_soon_threadsafe(
                self._loop.stop,
            )

        if self._thread:
            self._thread.join(timeout=3)

        self._loop = None
        self._thread = None
        self._started = False

    async def close(self) -> None:
        for server_name, runtime in list(self._runtimes.items()):
            try:
                await runtime.stack.aclose()
                logger.info("Closed %s", server_name)
            except Exception as e:
                logger.error("Failed to close %s: %s", server_name, e)

        self._runtimes.clear()

    def _ensure_loop(self) -> None:
        if self._loop and self._loop.is_running():
            return

        self._ready.clear()
        self._loop = asyncio.new_event_loop()

        def run_loop() -> None:
            asyncio.set_event_loop(self._loop)
            self._ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(
            target=run_loop,
            name="mcp-event-loop",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=5)

    def _run_sync(self, coro, timeout: float | None = None):
        if not self._loop:
            raise RuntimeError("MCP event loop is not running")

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise

    @staticmethod
    def _format_tool_result(result) -> str:
        parts: list[str] = []

        if getattr(result, "isError", False):
            parts.append("MCP tool error:")

        structured = getattr(result, "structuredContent", None)
        if structured:
            parts.append("Structured result:")
            parts.append(json.dumps(structured, ensure_ascii=False, indent=2))

        for item in getattr(result, "content", []) or []:
            if isinstance(item, types.TextContent):
                parts.append(item.text)
            else:
                parts.append(repr(item))

        return "\n".join(parts).strip() or "(empty MCP result)"
