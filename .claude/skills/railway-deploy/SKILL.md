---
name: railway-deploy
description: Use when deploying jb_homebase, touching Railway services or env vars, debugging production after a deploy, configuring healthchecks or the evals cron, or anything CLI/infra-related for the Claw stack on Railway.
---

# Railway deploy — jb_homebase

Project **JB-HomeBase**, environment `production`, TWO services from one
Dockerfile (no railway.toml, no Procfile, no nixpacks, no worker service):

| Service | What | Key facts |
|---|---|---|
| `jb_homebase` | web: uvicorn `jordan_claw.main:app` on 8000 | auto-deploys on push to main; healthcheck `GET /health`; needs `PORT=8000` set as a variable — Railway probes the PORT var, not the Dockerfile EXPOSE. Prod URL `https://jbhomebase-production.up.railway.app` |
| `evals-cron` | cron `0 3 * * *`, start command `uv run claw-eval run --all` | same image; healthcheck disabled; restart Never; env vars are REFERENCES: `${{ jb_homebase.VAR }}` — set real values only on `jb_homebase` |

One process serves everything: web routes, both Telegram bots (long-polling
asyncio tasks), the proactive scheduler. There is no second runtime to scale.

## The three rules that have caused or prevented outages

1. **Always pass `-s <service>`** to every `railway` command (`variables`,
   `logs`, `redeploy`, ...). The CLI's sticky default service once landed vars
   on `evals-cron`; the workout bot died on the next redeploy (2026-07-05).
   After setting a var, read it back on the intended service.
2. **`/health` gates deploys.** It cross-checks every active DB agent: bot
   running for the slug + model actually served by the Anthropic API. 503 =
   old deploy stays live. If a deploy "won't go live", curl /health and read
   the body — it names the failing agent/model. Known blind spot: a present-
   but-revoked bot token still reports healthy (polling task dies silently).
3. **Build success ≠ deploy success.** After push: confirm the active deploy
   is your SHA, curl /health, then exercise the changed surface (real Telegram
   message or `/app/messages` curl). Use the `deploy-verify` skill.

## Secrets & config

- Source of truth is **Infisical**, not Railway's CLI vars flow. Local runs:
  `infisical run --env=dev -- <cmd>`. Long unattended runs: service tokens.
- Never run interactive auth (`railway login`, `railway ssh`, `infisical
  login`) — ask Jordan to run it with the `!` prefix and paste output.
- Full env-var catalogue: `docs/architecture.md`. Empty string = feature
  disabled by design (workout bot, webhooks, app endpoints, fastmail watcher) —
  a "missing" optional var may be intentional.
- Adding a var the evals also need? Set it on `jb_homebase`, then add the
  `${{ jb_homebase.VAR }}` reference on `evals-cron`. The evals-cron service
  requires ALL required Settings fields even for features evals don't use —
  `get_settings()` fails fast otherwise (that's deliberate; see docs/evals.md).

## Debugging production

```bash
railway logs -s jb_homebase | grep -Ei "workout_bot_started|polling|Traceback|health"
railway status -s jb_homebase        # active deploy = your SHA? exactly one replica?
curl -s https://jbhomebase-production.up.railway.app/health | jq
```

- Edge replays: Railway's edge re-sends requests that get no response in ~20s.
  Slow endpoints (/voice, /app/messages: 30–60s agent runs) must converge on a
  client-stable idempotency key — never treat a replay as a new request.
  Pattern lives in `gateway/voice.py` / `gateway/app_chat.py`.
- One bot down, other up → the process is fine; suspect the bot's token var on
  the service or its DB agent row (model/is_active). Both bots, one process.
- Never point a local gateway at prod Telegram tokens — it steals `getUpdates`
  polling (409) from prod.

## Deploy sequencing with DB changes

Railway deploys the instant main moves. Schema-expanding migrations run in the
Supabase SQL Editor BEFORE the merge; code-dependent data migrations (e.g.
capability grants) after. Migration headers state their ordering — read them.
