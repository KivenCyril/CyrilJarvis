from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote_plus

from jarvis.tools.base import BaseTool, ToolResult

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]


def _parse_results(body: str) -> list[dict[str, str]]:
    """Extract search results from DuckDuckGo HTML response.

    DuckDuckGo's HTML search page returns results in a minimal format.
    We look for ``<a class="result__a" ...>`` links and their sibling
    snippets.
    """
    results: list[dict[str, str]] = []

    # Each organic result lives inside a <div class="result ..."> block.
    result_blocks = re.findall(
        r'<a\s+[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        body,
        re.DOTALL,
    )

    snippet_blocks = re.findall(
        r'<a\s+class="result__snippet"[^>]*>(.*?)</a>',
        body,
        re.DOTALL,
    )

    for idx, (url, raw_title) in enumerate(result_blocks):
        title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        snippet = ""
        if idx < len(snippet_blocks):
            snippet = html.unescape(
                re.sub(r"<[^>]+>", "", snippet_blocks[idx])
            ).strip()
        if url and title:
            results.append({"title": title, "url": url, "snippet": snippet})

    return results


class WebSearchTool(BaseTool):
    """Search the web via DuckDuckGo (no API key required)."""

    name = "web_search"
    description = (
        "Search the web using DuckDuckGo and return a list of results, "
        "each containing a title, URL, and snippet."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5).",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if httpx is None:
            return ToolResult(
                success=False,
                output="httpx is not installed. Run: pip install httpx",
            )

        query: str = arguments["query"]
        max_results: int = arguments.get("max_results", 5)

        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=15.0
            ) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            return ToolResult(success=False, output=f"Search request failed: {exc}")

        results = _parse_results(resp.text)[:max_results]

        if not results:
            return ToolResult(
                success=True,
                output="No results found.",
                data={"results": []},
            )

        # Build a human-readable summary as well.
        lines: list[str] = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}")

        return ToolResult(
            success=True,
            output="\n\n".join(lines),
            data={"results": results},
        )
