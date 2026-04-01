from __future__ import annotations

from pydantic_ai import Agent, ModelRequest, ModelResponse, TextPart, UserPromptPart

from jordan_claw.tools.time import get_current_datetime
from jordan_claw.tools.web_search import web_search

SYSTEM_PROMPT = """\
You are Jordan's AI assistant. You work for a builder who runs a promotional \
products company, a foster care community platform, and an AI consultancy. \
Your job is to be useful.

Be direct. Lead with the answer, not the reasoning. Short sentences. Plain \
language. If you don't know something, say so and offer a next step.

You have tools for checking the current time and searching the web. Use them \
when the question needs real-time information. Don't mention your tools unless \
someone asks what you can do.

When you search the web, summarize what you found. Don't just list links.

A few things to keep in mind:
- Specific over vague. Numbers, names, dates when you have them.
- No corporate jargon. Don't say "leverage," "optimize," "facilitate," or \
"implement."
- No motivational filler. No "Great question!" No "The future is here!"
- No em dashes.
- If someone asks about foster care or foster youth, use "people with lived \
experience in foster care." Never say "at-risk youth" or "broken homes." \
Never use charity framing.
- You're a tool, not a personality. Be helpful, be concise, move on.\
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
        """Search the web for current information.

        Use for questions about recent events, facts, or anything
        that benefits from up-to-date data.
        """
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
