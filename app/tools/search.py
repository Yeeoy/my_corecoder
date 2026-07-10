import time
from typing import Any

from pydantic import BaseModel
from tavily import TavilyClient

from app.config import get_config
from app.tools.base import Tool, ToolResult


class SearchResult(BaseModel):
    url: str
    title: str
    content: str
    score: float | None = None
    raw_content: str | None = None


class SearchTool(Tool):
    name = "search"
    description = "Search for information on the internet"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
        },
        "required": ["query"],
    }

    def execute(self, query: str) -> ToolResult:
        start = time.perf_counter()
        try:
            if not get_config().TAVILY_API_KEY:
                return ToolResult(
                    ok=False,
                    content="",
                    error="TAVILY_API_KEY NOT SET",
                    metadata={
                        "tool": self.name,
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                    },
                )
            client = TavilyClient(api_key=get_config().TAVILY_API_KEY)
            response = client.search(query=query, search_depth="advanced")
            results = self.format_search_results(response.get("results", []))
            return ToolResult(
                ok=True,
                content=results or f"(No Results found for query:{query})",
                error="",
                metadata={
                    "tool": self.name,
                    "query": query,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                content="",
                error=f"Error: {type(e).__name__} : {str(e)}",
                metadata={
                    "tool": self.name,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )

    def format_search_results(self, search_results: list[dict[str, Any]]) -> str:
        results = []
        if not search_results:
            return ""
        for idx, item in enumerate(search_results, start=1):
            obj = SearchResult(**item)
            block = (
                f"Search Result: {idx} \n"
                f"Search url: {obj.url}\n"
                f"Search title: {obj.title}\n"
                f"Search score: {obj.score}\n"
                f"Search content: {obj.content}\n"
            )

            if obj.raw_content:
                block += f"Search raw content: {obj.raw_content}\n"
            results.append(block)
        return "\n\n".join(results)
