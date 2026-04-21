-- Jordan Claw Memory System Schema
-- Run this in the Supabase SQL Editor

-- Persistent facts about a tenant
create table memory_facts (
    id uuid primary key default gen_random_uuid(),
    org_id uuid references organizations(id) on delete cascade not null,
    category text not null check (category in ('preference', 'decision', 'entity', 'workflow', 'relationship')),
    content text not null,
    source text not null check (source in ('conversation', 'explicit', 'inferred')),
    confidence float not null default 0.8,
    metadata jsonb default '{}',
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    expires_at timestamptz,
    is_archived boolean default false
);

-- Timestamped log of significant interactions
create table memory_events (
    id uuid primary key default gen_random_uuid(),
    org_id uuid references organizations(id) on delete cascade not null,
    event_type text not null check (event_type in ('decision', 'task_completed', 'feedback', 'milestone', 'correction')),
    summary text not null,
    context jsonb default '{}',
    created_at timestamptz default now()
);

-- Pre-rendered prompt blocks for injection
create table memory_context (
    id uuid primary key default gen_random_uuid(),
    org_id uuid references organizations(id) on delete cascade not null,
    scope text not null,
    context_block text not null,
    is_stale boolean default true,
    last_computed timestamptz,
    unique(org_id, scope)
);

-- Indexes
create index idx_memory_facts_org_active on memory_facts(org_id) where is_archived = false;
create index idx_memory_facts_org_category on memory_facts(org_id, category) where is_archived = false;
create index idx_memory_events_org_created on memory_events(org_id, created_at desc);

-- RLS
alter table memory_facts enable row level security;
alter table memory_events enable row level security;
alter table memory_context enable row level security;
