# Jordan Claw — Flutter App PRD v1

## Overview

Jordan Claw is shifting from Telegram-only personal agent OS to a Flutter app as primary channel. The app is a thin client over the existing FastAPI gateway and Pydantic AI agents. Server is the source of truth; multi-device sync is by re-reading from server, not local persistence.

This is the v1 PRD for the MVP that replaces Telegram and earns daily use.

## North Star

**"I keep coming back."** The app earns daily use by being where Jordan's context compounds over time — memory, skills, Obsidian, ratings, evals. The bar is not "better than Claude.ai on day one." The bar is "the place I open at 6:47am, on a run, at 10pm." Polish budget goes into the context loop (skill discovery, memory recall, Obsidian retrieval, the feedback that improves them), not chat-surface chrome.

## Goals (v1)

- Replace Telegram as the primary channel on cutover day
- Make voice dump the dominant input mode
- Surface proactive messages on a curated Today feed
- Chat with Claw Main as the deep-thinking partner surface
- Room abstraction built right from day one (Training and Jessie come later but plug in cleanly)

## Non-goals (v1)

- Training and Jessie specialized UIs (rooms exist as chat-only placeholders)
- Audio summaries (NotebookLM-style; phase 2)
- Voice output
- Offline mode
- Visible thinking traces
- Custom in-app analytics dashboards (PostHog is the dashboard)
- Telegram (rip out on cutover)

## User

Single user (Jordan). Solo founder, parent, ultramarathon trainee. Phone is checked 30+ times a day; laptop is the daily workbench. Voice-dumps on runs, drives, and walks. Reads morning briefing at 6:47am. Wants the app to be the surface he opens instead of Claude.ai, ChatGPT, or Telegram.

## Reference apps

- **Granola** — top-left folder drawer, date-grouped chronological list, prominent bottom-center "Chat with X" CTA, warm off-white background, minimal chrome
- **NotebookLM** — clean card list, persistent header showing context, "Ask N sources..." input pattern, three-tab inside-notebook structure (Sources / Chat / Studio)
- **Things 3** — Today as a curated, time-aware surface (not chronological)

## Information architecture

```
App
├── Today (default landing)
│   └── Curated cards (server-driven, time-of-day rules, TTLs)
│
├── Drawer (top-left icon) (Granola pattern)
│   ├── Rooms
│   │   ├── Claw Main (v1, only fully built room)
│   │   ├── Training (coming soon, disabled card)
│   │   └── Jessie (coming soon, disabled card)
│   ├── Settings
│   └── Sign out
│
└── Room (entered from drawer)
    ├── Chat (default tab inside a room)
    ├── Context (skills, memory scope, tools loaded)
    └── History (past conversations, date-grouped)
```

**Persistent bottom action bar** (Granola pattern, surfaces vary by screen):
- **On Today**: mic (left) · "Chat with Claw Main" (center, jumps into active room) · pencil (right, new conversation in active room)
- **Inside a Room**: mic (left) · message composer (center) · send/pencil (right)
- Mic is always reachable, regardless of surface

## Surfaces

### Today (default landing)

- Server-driven cards via `/api/today/cards` — curation rules live server-side, app renders what it's told
- Time-of-day TTLs:
  - Morning briefing card: 7am–12pm
  - Weekly review card: Sun 7pm – Mon 11am
  - Eval regression alert: 24h from fire
  - Low-rating alert (agent avg < 3 over 7d): persists until rating recovers
- Max 3 always-visible cards (curation discipline)
- Pull-to-refresh re-fetches from server
- Card actions: tap to expand, swipe to dismiss (sets server-side `dismissed_at`)

### Room (Claw Main is the only fully built room in v1)

- **Header**: agent name + small icon + context subline ("12 skills · memory on · Obsidian indexed")
- **Three tabs**: Chat / Context / History

**Chat tab** (default):
- Streaming responses with tool-call chips that appear mid-response and resolve ("Searching notes... ✓ 3 found", "Checking calendar... ✓")
- No thinking traces, ever
- Markdown rendering, code blocks with syntax highlighting, copy button
- Long-press a message: rate (1–5 thumbs), copy, jump to source if cited
- Compose: text input + voice dump button + send. Voice button is always reachable.
- Conversation auto-archives after 30 min idle (server-side, already implemented); new message after that starts a new conversation

**Context tab**:
- What's loaded for this room: skills list (read-only in v1), memory scope (on/off + summary), tools (chips), Obsidian status
- Tap a skill/tool to see its description
- Editing scope is v1.1

**History tab**:
- Past conversations grouped by date sections: Today / Yesterday / This Week / earlier sections by date (Granola pattern)
- Each row: first user message preview, message count, time
- Tap to enter conversation in read-only mode + button to "Continue this thread"

### Voice capture (primary input mode)

- Mic button reachable from anywhere
- Tap to start recording → recording overlay (Granola-style state, waveform)
- Tap again to stop → transcript preview screen
- Preview screen: transcribed text + audio scrubber + Send / Discard / Re-record buttons
- On Send: audio file + transcript posted to server, attached as a message in the active room (defaults to Claw Main if no active room)
- Server-side: Whisper transcribes (existing infrastructure from delivery-coach pipeline), message saved, agent run kicks off
- Preview-before-send is the v1 default; auto-send-on-stop is a settings toggle for v1.1

### Auth

- **Passkey** is primary across all devices (phone, laptop, iPad — register all three before Telegram cutover)
- **Magic link via Fastmail email** is the recovery path, surfaced behind a "Having trouble?" link on the passkey screen, NOT as a co-equal option
- Sessions persist across app launches via secure token storage (iOS Keychain / Android Keystore)
- Sign-out is in the drawer, explicit

### Push notifications

- Delivered for proactive messages (morning briefing, weekly review, eval regression alert)
- Tapping notification deep-links to the relevant Today card or room
- Notification copy: server-generated (agent writes the briefing, notification is its first line + truncation)
- Per-channel preferences (per-room mute, etc.) deferred to v1.1

## Visual design direction

Pull from Granola, not NotebookLM, where they diverge:

- Background: warm off-white (`#F7F5F0` direction, not pure white)
- Text: near-black, generous line-height (1.5+)
- Cards: rounded (12–16pt radius), subtle shadow, generous padding
- Accent: single color (sample from Granola's olive-green direction, or pick a custom Jordan Claw hue — decide in design phase)
- Typography: system fonts (SF on iOS, Roboto on Android — Flutter default)
- Touch targets: 44pt minimum
- Chrome: minimal — no top app bar gradients, no unnecessary borders
- Empty states: text + small illustration, never blank

## Technical constraints

- **Thin client.** No agent logic, no Pydantic AI, no memory state. Server is truth.
- **Multi-device sync** via re-reading from server. No local DB. Cache for snappiness only.
- **All agent runs** go through the existing FastAPI gateway via a new HTTP channel adapter
- **Streaming**: SSE or chunked HTTP (decided in backend build plan)
- **Voice upload**: multipart POST, server-side Whisper, message creation in same request
- **Push notifications**: APNs/FCM (backend work required — does not exist today)
- **Analytics**: emitted through `/api/analytics/event` proxy (PR3 of analytics plan)
- **Auth**: passkey via WebAuthn, magic link via signed-URL email

## Phasing

**v1 (MVP, 6–7 weeks):**
- Today feed (Claw-Main-fed cards)
- Claw Main room (Chat / Context / History)
- Voice dump (preview-before-send)
- Passkey + magic-link recovery
- Multi-device
- Push notifications for proactive
- Telegram cutover

**v1.1 (after MVP feels right):**
- Training room with specialized UI (workout schedule, mileage chart)
- Jessie room (chat-only first iteration)
- Editable context scope
- Voice dump auto-send toggle
- Per-room notification preferences

**v2:**
- Audio summaries (NotebookLM-style, server-generated)
- Desktop optimization (Flutter desktop, larger layouts)
- Search across all rooms and conversations

## Open questions

1. Today cards: dismissible by user, or auto-expire on TTL only?
2. Context tab: show every skill/tool loaded, or only those relevant to current conversation?
3. Voice dump: preview-before-send always, or auto-send-on-stop as a setting?
4. Drawer: surface "Recent conversations" shortcut at top, or only rooms + settings?
5. Push notification copy: agent-generated per message, or templated with first-line preview?
6. Accent color: borrow from Granola (warm olive/green), or pick a custom hue?
7. Voice dump on lock screen: support iOS Action Button / Android quick-tile, or app-only for v1?

## Success metrics

The app is succeeding when:
- Telegram is uninstalled and not missed
- Voice dumps per day > text messages per day
- Jordan opens the app at 6:47am, 12pm, and 9pm without prompting
- Average rating across rooms trends up over 4-week windows
- Time spent in Claude.ai / ChatGPT decreases
