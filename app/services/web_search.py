"""Web search service using DuckDuckGo for fetching latest public information."""

import asyncio
from dataclasses import dataclass

from ddgs import DDGS


@dataclass
class WebSearchResult:
    title: str
    snippet: str
    url: str


async def search_web(query: str, max_results: int = 3) -> list[WebSearchResult]:
    """Search the web using DuckDuckGo and return top results.

    Runs the synchronous DDGS client in a thread pool to avoid blocking.
    """
    def _search():
        try:
            with DDGS() as ddgs:
                raw = ddgs.text(query, max_results=max_results)
                return [
                    WebSearchResult(
                        title=r.get("title", ""),
                        snippet=r.get("body", ""),
                        url=r.get("href", ""),
                    )
                    for r in raw
                ]
        except Exception:
            return []

    return await asyncio.get_event_loop().run_in_executor(None, _search)


def format_web_results(results: list[WebSearchResult]) -> str:
    """Format web search results into a text block for the LLM prompt."""
    if not results:
        return ""
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"[网络来源 {i}: {r.title}]\n{r.snippet}\n链接: {r.url}")
    return "\n\n---\n\n".join(parts)
