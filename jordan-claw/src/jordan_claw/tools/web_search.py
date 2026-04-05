from __future__ import annotations

from pydantic_ai import RunContext
from tavily import AsyncTavilyClient

from jordan_claw.agents.deps import AgentDeps


async def search_web(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search the web for information from the outside world.
    Use for discovering new people, companies, content creators, products,
    recommendations, current events, comparisons, or anything not already
    in Jordan's notes or memory. Default to this tool when unsure whether
    information is in Jordan's notes or on the web.
    """
    client = AsyncTavilyClient(api_key=ctx.deps.tavily_api_key)
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
