-- Jordan Claw Phase 1 Schema
-- Run this in the Supabase SQL Editor

-- Organizations (tenants)
create table organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    slug text unique not null,
    settings jsonb default '{}',
    created_at timestamptz default now()
);

-- Agent definitions per organization (read by Phase 2 code, exists for schema readiness)
create table agents (
    id uuid primary key default gen_random_uuid(),
    org_id uuid references organizations(id) on delete cascade,
    name text not null,
    slug text not null,
    system_prompt text not null,
    model text default 'claude-sonnet-4-20250514',
    tools jsonb default '[]',
    settings jsonb default '{}',
    is_default boolean default false,
    is_active boolean default true,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique(org_id, slug)
);

-- Conversations track a thread across any channel
create table conversations (
    id uuid primary key default gen_random_uuid(),
    org_id uuid references organizations(id) on delete cascade,
    agent_id uuid references agents(id),
    channel text not null,
    channel_thread_id text,
    user_id uuid,
    metadata jsonb default '{}',
    status text default 'active' check (status in ('active', 'archived', 'error')),
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- Messages within a conversation
create table messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid references conversations(id) on delete cascade,
    role text not null check (role in ('user', 'assistant', 'system', 'tool')),
    content text not null,
    channel_message_id text,
    token_count int,
    cost_usd numeric(10, 6),
    model text,
    metadata jsonb default '{}',
    created_at timestamptz default now()
);

-- Indexes
create index idx_messages_conversation_created on messages(conversation_id, created_at);
create index idx_messages_channel_dedup on messages(channel_message_id) where channel_message_id is not null;
create index idx_conversations_channel on conversations(org_id, channel, channel_thread_id);
create index idx_agents_org on agents(org_id) where is_active = true;

-- RLS (enabled on all tables, service role key bypasses)
alter table organizations enable row level security;
alter table agents enable row level security;
alter table conversations enable row level security;
alter table messages enable row level security;

-- Seed data: Jordan's org
insert into organizations (id, name, slug)
values ('1408252a-fd36-4fd3-b527-3b2f495d7b9c', 'Jordan Bartlett', 'jb');
