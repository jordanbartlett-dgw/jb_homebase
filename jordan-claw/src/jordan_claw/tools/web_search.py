from __future__ import annotations

from tavily import AsyncTavilyClient


async def web_search(query: str, *, api_key: str, max_results: int = 3) -> str:
    """Search the web using Tavily and return a formatted summary."""
    client = AsyncTavilyClient(api_key=api_key)
    response = await client.search(query=query, max_results=max_results)

    results = response.get("results", [])
    if not results:
        return "No results found."

    formatted = []
    for r in results:
        title = r.get("title", "No title")
        url = r.get("url", "")
        snippet = r.get("content", "No description")
        formatted.append(f"**{title}**\n{snippet}\n{url}")

    return "\n\n---\n\n".join(formatted)
