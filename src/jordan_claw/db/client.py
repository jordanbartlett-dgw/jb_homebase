from __future__ import annotations

from supabase._async.client import AsyncClient, create_client

_client: AsyncClient | None = None


async def get_supabase_client(url: str, service_key: str) -> AsyncClient:
    """Get or create the async Supabase client singleton."""
    global _client
    if _client is None:
        _client = await create_client(url, service_key)
    return _client


async def close_supabase_client() -> None:
    """Close the Supabase client connection."""
    global _client
    if _client is not None:
        _client = None
