from __future__ import annotations

from pydantic_ai import RunContext
from tavily import AsyncTavilyClient

from jordan_claw.agents.deps import AgentDeps


async def search_web(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search the web for current information.

    Use for questions about recent events, facts, or anything
    that benefits from up-to-date data.
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
