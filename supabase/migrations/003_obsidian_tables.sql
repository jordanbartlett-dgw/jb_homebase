-- Enable pgvector if not already enabled
create extension if not exists vector with schema extensions;

-- Obsidian notes ingested from vault or created by Claw
create table obsidian_notes (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references organizations(id) on delete cascade,
    vault_path text not null,
    title text not null,
    note_type text not null,
    content text not null,
    frontmatter jsonb not null default '{}',
    tags text[] default '{}',
    wiki_links text[] default '{}',
    source_origin text not null default 'vault'
        check (source_origin in ('vault', 'claw')),
    sync_status text not null default 'synced'
        check (sync_status in ('synced', 'pending_export')),
    content_hash text not null,
    is_archived boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (org_id, vault_path)
);

create index idx_obsidian_notes_org_type
    on obsidian_notes (org_id, note_type)
    where is_archived = false;

create index idx_obsidian_notes_tags
    on obsidian_notes using gin (tags)
    where is_archived = false;

-- Chunks with vector embeddings for semantic search
create table obsidian_note_chunks (
    id uuid primary key default gen_random_uuid(),
    note_id uuid not null references obsidian_notes(id) on delete cascade,
    chunk_index int not null default 0,
    content text not null,
    embedding vector(512),
    token_count int not null default 0,
    created_at timestamptz not null default now()
);

create index idx_obsidian_note_chunks_note_id
    on obsidian_note_chunks (note_id);

create index idx_obsidian_note_chunks_embedding
    on obsidian_note_chunks using hnsw (embedding vector_cosine_ops);

-- RLS
alter table obsidian_notes enable row level security;
alter table obsidian_note_chunks enable row level security;

-- RPC function for semantic search with optional filters
create or replace function search_obsidian_notes(
    p_org_id uuid,
    p_embedding vector(512),
    p_limit int default 10,
    p_note_type text default null,
    p_tags text[] default null
)
returns table (
    note_id uuid,
    title text,
    note_type text,
    tags text[],
    chunk_content text,
    chunk_index int,
    similarity float
)
language sql stable
as $$
    select
        n.id as note_id,
        n.title,
        n.note_type,
        n.tags,
        c.content as chunk_content,
        c.chunk_index,
        1 - (c.embedding <=> p_embedding) as similarity
    from obsidian_note_chunks c
    join obsidian_notes n on n.id = c.note_id
    where n.org_id = p_org_id
      and n.is_archived = false
      and (p_note_type is null or n.note_type = p_note_type)
      and (p_tags is null or n.tags && p_tags)
    order by c.embedding <=> p_embedding
    limit p_limit;
$$;
