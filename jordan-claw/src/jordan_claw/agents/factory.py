from __future__ import annotations

from pydantic_ai import Agent, ModelRequest, ModelResponse, TextPart, UserPromptPart

from jordan_claw.tools.time import get_current_datetime
from jordan_claw.tools.web_search import web_search

SYSTEM_PROMPT = """\
You are a helpful AI assistant. You are knowledgeable, concise, and direct.
You have access to tools for checking the current time and searching the web.
Use them when the user's question would benefit from real-time information.
Keep responses focused and practical.\
"""


def create_agent(*, tavily_api_key: str) -> Agent:
    """Create the Phase 1 hardcoded Pydantic AI agent."""
    agent = Agent(
        "anthropic:claude-sonnet-4-20250514",
        system_prompt=SYSTEM_PROMPT,
    )

    @agent.tool_plain
    def current_datetime() -> str:
        """Get the current date and time in UTC."""
        return get_current_datetime()

    @agent.tool_plain
    async def search_web(query: str) -> str:
        """Search the web for current information. Use for questions about recent events, facts, or anything that benefits from up-to-date data."""
        return await web_search(query, api_key=tavily_api_key)

    return agent


def db_messages_to_history(messages: list[dict]) -> list[ModelRequest | ModelResponse]:
    """Convert DB message rows to Pydantic AI message history format.

    Only converts user and assistant messages. Skips system and tool roles.
    """
    history: list[ModelRequest | ModelResponse] = []

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif role == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=content)]))

    return history
