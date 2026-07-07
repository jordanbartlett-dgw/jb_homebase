---
name: channel-adapter
description: Use when adding a new channel to the jb_homebase gateway, changing how messages enter or leave the system, handling channel payloads, routing agent replies back to a channel, or reasoning about message normalization and the gateway message flow.
---

# Channels in the Claw gateway

How it actually works in this repo (not a generic adapter framework — there are
no Adapter classes, no `UnifiedMessage`, no `channel_mappings` table, no Slack).
Ground truth: `src/jordan_claw/gateway/` and `src/jordan_claw/channels/`.

## The contract

Every channel does exactly three things:

1. **Normalize** its payload into `IncomingMessage` (`gateway/models.py`):
   `channel`, `channel_thread_id`, `channel_message_id`, `content`, `org_id`,
   `metadata`. Plain strings — no enum, no attachment model.
2. **Call** `gateway/router.py::handle_message(msg, db, settings-ish args...)`.
   That one function owns dedup, conversation, memory, agent run, persistence.
3. **Deliver** the returned `GatewayResponse.content` back out — skipping
   delivery when content is empty (the dedup/suppression sentinel).

Existing channels to copy from:
- `telegram` — `channels/telegram.py`: aiogram Dispatcher, long-polling (NOT
  webhooks), catch-all `handle_text`, Markdown reply with plain-text fallback.
- `app` — `main.py::app_text_message` + `gateway/app_chat.py`: HTTP
  request/reply, bearer `CLAW_APP_TOKEN`, explicit agent_slug.
- `voice`/`app` — `main.py::voice_message` + `gateway/voice.py`: transcribe →
  classify (`gateway/classifier.py`, always falls back to claw-main) → same core.

## Dedup key convention (load-bearing)

`channel_message_id` must be globally unique and stable across retries — prefix
with the channel at creation time:
- `telegram:{chat_id}:{message_id}`
- `app-{agent_slug}-{idempotency_key}`
- `app-voice-{idempotency_key}`

For HTTP channels the key comes from the client (or a payload hash) so Railway
edge replays (~20s no-response → re-send) converge: look up the existing
message first (`get_message_by_channel_id`), and if found, poll for the
original run's reply (`gateway/voice.py::await_original_reply`) instead of
running the agent twice. Never generate a per-request UUID server-side.

## Thread identity and rotation

`(org_id, channel, channel_thread_id)` identifies a thread;
`get_or_create_conversation` rotates the conversation after 30 idle minutes.
Pick `channel_thread_id` so that rotation semantics make sense (Telegram: chat
id; app: agent slug = one thread per agent). Any state you hang on a
conversation must survive rotation intentionally.

## Adding a channel — checklist

1. Normalizer → `IncomingMessage` with a prefixed, replay-stable
   `channel_message_id`.
2. Auth: bearer or shared secret via `secrets.compare_digest`; empty-string
   config = endpoint disabled with 503 (never open). See `main.py::_require_app_token`.
3. Call `handle_message`; treat empty content as "don't deliver".
4. Long-running channel (>20s)? Add the replay-convergence path.
5. Outbound formatting is the channel's job (Telegram does Markdown-with-
   fallback; app returns raw text and the Flutter client renders).
6. Tests: normalize/dedup/replay unit tests + one wiring test through
   `handle_message` with mocked DB (see `tests/test_gateway.py`,
   `tests/test_voice_endpoint.py`).
7. If the channel serves a new agent surface, update `/health` expectations —
   active agents must have their runtime present or deploys gate.

## Anti-patterns (each has bitten this repo or nearly did)

- Building an Adapter/registry abstraction for a second channel that doesn't
  exist yet — two concrete channels beat one framework.
- Webhook-mode Telegram — this repo polls; a second `getUpdates` consumer
  (e.g. running the gateway locally with prod tokens) 409s the prod bot.
- Server-generated per-request idempotency keys — replays stop converging.
- `maybe_single()` anywhere in the lookup path — use `.limit(1)`.
