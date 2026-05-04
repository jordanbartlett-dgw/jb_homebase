"""RLS verification gate — BLOCKS PR5 MERGE.

The eval-only org (eval_test_org_id) seeds synthetic Obsidian notes into the
shared dev Supabase project. Production code paths read with the service-role
key, which bypasses RLS, so isolation rests on two things together:

1. App code filters every Obsidian read by org_id (verifiable in the source).
2. RLS denies any non-service-role query to obsidian_notes /
   obsidian_note_chunks (verified here).

Migration 003 enables RLS on both tables but creates no policies, so anon-key
queries return zero rows by default. This test asserts that contract holds. If
a future migration adds an unrestricted policy, this test will fail and
PR5/eval_test_org_id must move to a separate Supabase project.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from supabase import create_async_client

EVA_ORG_ID = "eaa1eaa1-eaa1-eaa1-eaa1-eaa1eaa1eaa1"
DUMMY_NON_EVA_ORG_ID = "00000000-0000-0000-0000-000000000111"


def _has_creds() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_ANON_KEY"))


@pytest.mark.skipif(
    not _has_creds(),
    reason="Requires SUPABASE_URL + SUPABASE_ANON_KEY (live RLS check).",
)
def test_anon_key_cannot_read_obsidian_notes_for_any_org() -> None:
    """Anon key must return zero rows from obsidian_notes regardless of org_id filter.

    Strongest possible isolation: RLS is enabled with no policies → deny all.
    """

    async def _check() -> tuple[int, int, int]:
        client = await create_async_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_ANON_KEY"],
        )
        # Filtered to eva org
        eva_rows = (
            await client.table("obsidian_notes")
            .select("id")
            .eq("org_id", EVA_ORG_ID)
            .limit(10)
            .execute()
        )
        # Filtered to a non-eva org
        other_rows = (
            await client.table("obsidian_notes")
            .select("id")
            .eq("org_id", DUMMY_NON_EVA_ORG_ID)
            .limit(10)
            .execute()
        )
        # Unfiltered
        all_rows = (
            await client.table("obsidian_notes").select("id").limit(10).execute()
        )
        return len(eva_rows.data), len(other_rows.data), len(all_rows.data)

    eva_count, other_count, all_count = asyncio.run(_check())

    assert eva_count == 0, "anon key must NOT read eva-org Obsidian notes"
    assert other_count == 0, "anon key must NOT read any other-org Obsidian notes"
    assert all_count == 0, "anon key must NOT read any Obsidian notes (RLS deny-all)"


@pytest.mark.skipif(
    not _has_creds(),
    reason="Requires SUPABASE_URL + SUPABASE_ANON_KEY (live RLS check).",
)
def test_anon_key_cannot_read_obsidian_note_chunks() -> None:
    """Same contract for the chunks table (where embeddings live)."""

    async def _check() -> int:
        client = await create_async_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_ANON_KEY"],
        )
        rows = await client.table("obsidian_note_chunks").select("id").limit(10).execute()
        return len(rows.data)

    assert asyncio.run(_check()) == 0
