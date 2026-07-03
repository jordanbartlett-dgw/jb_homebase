from __future__ import annotations

from pydantic_ai import RunContext
from tavily import AsyncTavilyClient

from jordan_claw.agents.deps import AgentDeps

# Cached per key so the underlying httpx connection pool is reused across calls
_tavily_clients: dict[str, AsyncTavilyClient] = {}


def get_tavily_client(api_key: str) -> AsyncTavilyClient:
    client = _tavily_clients.get(api_key)
    if client is None:
        client = _tavily_clients[api_key] = AsyncTavilyClient(api_key=api_key)
    return client


async def search_web(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search the web for information from the outside world.
    Use for discovering new people, companies, content creators, products,
    recommendations, current events, comparisons, or anything not already
    in Jordan's notes or memory. Default to this tool when unsure whether
    information is in Jordan's notes or on the web.
    """
    client = get_tavily_client(ctx.deps.tavily_api_key)
    response = await client.search(query=query, max_results=3)

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
