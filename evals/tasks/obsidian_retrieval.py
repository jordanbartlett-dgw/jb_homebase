"""Obsidian retrieval task: pure semantic-search scoring against the eva corpus.

No LLM call inside the task fn — only embedding + Supabase RPC. Emits the slugs
of returned notes (parsed from the seeded frontmatter) in rank order. Caller's
scorer measures top-k set membership against the case's expected_slugs.
"""

from __future__ import annotations

from evals.types import ObsidianRetrievalInputs, RetrievalOutput
from jordan_claw.config import get_settings
from jordan_claw.db.obsidian import search_notes_semantic
from jordan_claw.obsidian.embeddings import generate_embeddings
from supabase import create_async_client


async def obsidian_retrieval_task(inputs: ObsidianRetrievalInputs) -> RetrievalOutput:
    settings = get_settings()
    embeddings = await generate_embeddings([inputs.query], api_key=settings.openai_api_key)
    query_embedding = embeddings[0]

    client = await create_async_client(settings.supabase_url, settings.supabase_service_key)
    rows = await search_notes_semantic(
        client,
        org_id=settings.eval_test_org_id,
        embedding=query_embedding,
        limit=10,
    )

    # The RPC returns chunk-level rows; collapse to per-note (preserve rank).
    seen: set[str] = set()
    slugs: list[str] = []
    for row in rows:
        note_id = row["note_id"]
        if note_id in seen:
            continue
        seen.add(note_id)
        # Pull the slug out of the title's vault_path. We seeded with
        # vault_path=evals/{slug}.md and slug also lives in frontmatter, but
        # the RPC doesn't return frontmatter, so re-derive from title.
        title = row["title"]
        slugs.append(_title_to_slug_lookup(title))

    return RetrievalOutput(returned_slugs=slugs)


# Title → slug mapping. The slug is authoritative in fixtures/corpus.yaml.
# We rebuild the mapping at module load so this stays in sync.
def _build_title_slug_map() -> dict[str, str]:
    from pathlib import Path as _Path

    import yaml as _yaml

    corpus = _yaml.safe_load(
        (_Path(__file__).parent.parent / "fixtures" / "corpus.yaml").read_text()
    )
    return {n["title"]: n["slug"] for n in corpus["notes"]}


_TITLE_TO_SLUG = _build_title_slug_map()


def _title_to_slug_lookup(title: str) -> str:
    return _TITLE_TO_SLUG.get(title, title)
