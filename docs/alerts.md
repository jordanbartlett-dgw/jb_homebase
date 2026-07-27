# Alerts

Logfire alerts on top of the tracing already in place (see `docs/observability.md`).
The system is quiet-nightly by design: evals run once a day, dashboards are pull,
not push. Alerts are the push layer. Each one below closes a specific incident
class we've already hit or specifically want to catch before it repeats, not a
generic "something might be wrong" tripwire.

Logfire alerts are SQL conditions over the `records` table, evaluated on a
schedule, firing to a notification channel (email or Slack). Span/log attributes
live in the `attributes` JSON column: `attributes->>'agent_slug'` style. Column
names below (`start_timestamp`, `span_name`, `attributes`) are Logfire's standard
`records` schema as of this writing — **test-run every query in the Logfire SQL
editor before wiring it to an alert.** If a column name has drifted, the query
will error immediately and the fix is a one-line adjustment, not a redesign.

## 1. Agent error rate

Closes: repeated tool/model failures going unnoticed between nightly eval runs.

```sql
select count(*) as failure_count
from records
where span_name = 'agent_run'
  and attributes->>'outcome.success' = 'false'
  and start_timestamp > now() - interval '15 minutes'
```

- Schedule: every 5 min.
- Threshold: fire when `failure_count > 3` (more than 3 failed `agent_run` spans in 15 min).
- Channel: email to Jordan's Fastmail. Slack webhook is the alternative if email gets noisy.

## 2. Daily cost ceiling

Closes: a runaway loop or pricing bug burning spend silently until someone checks the dashboard.

```sql
select sum((attributes->>'usage.cost_usd')::float8) as total_cost_usd
from records
where span_name = 'agent_run'
  and start_timestamp > now() - interval '24 hours'
```

- Schedule: hourly.
- Threshold: fire when `total_cost_usd > 10` (24h rolling spend over $10).
- Channel: email to Jordan's Fastmail.

## 3. Trace-silence heartbeat

Closes: the polling-liveness blind spot from the sonnet-4 retirement incident
(both bots down ~3 weeks, evals stayed green because they pin their own model).
The scheduler ticks every 60s, so 45 minutes with zero `agent_run` or
`proactive.dispatch` spans means the process is wedged, not that traffic is
quiet.

```sql
select count(*) as span_count
from records
where span_name in ('agent_run', 'proactive.dispatch')
  and start_timestamp > now() - interval '45 minutes'
```

- Schedule: every 15 min.
- Threshold: fire when `span_count = 0`.
- Channel: email to Jordan's Fastmail. This one earns Slack too if/when Slack is wired up — silence alerts are the ones you want redundant.

## 4. Online-eval failures

Closes: quality regressions in live traffic that would otherwise sit unseen until
the next nightly offline eval run picks them up (or doesn't, since offline evals
score fixed datasets, not live traffic).

```sql
select count(*) as failure_count
from records
where span_name = 'gen_ai.evaluation.result'
  and start_timestamp > now() - interval '1 hour'
  and (
    attributes->>'error.type' is not null
    or (
      attributes->>'gen_ai.evaluation.name' = 'OutputSanity'
      and (attributes->>'gen_ai.evaluation.score.value')::float8 = 0
    )
  )
```

- Schedule: every 15 min.
- Threshold: fire when `failure_count > 2` (more than 2 in 1h).
- Channel: email to Jordan's Fastmail.
- Note: online eval judge sampling defaults to `0.0` (see `docs/observability.md`
  "Online evaluation"). `OutputSanity` runs at `sample_rate=1.0` regardless, so
  this alert is live even with the judge off. If the judge gets enabled later,
  this query can be widened to include `groundedness` failures.

## Logfire MCP

Connects Claude Code sessions directly to Logfire so traces, exceptions,
dashboards, and alerts can be queried without Jordan pasting screenshots.

Setup:

```bash
claude mcp add logfire --transport http https://logfire-us.pydantic.dev/mcp
```

Then run `/mcp` in Claude Code and authenticate (interactive, OAuth — Jordan runs
this step). Headless/CI alternative: a Logfire `project:read` API token, sent as
a Bearer header, no interactive auth needed.

What it unlocks:

- Querying traces, exceptions, and the alert queries above directly from a
  session, instead of Jordan relaying them.
- Claude can finally verify the phase-0 med-check content-absence check itself
  (confirm no prompt/completion content is exported for `med-check` traces,
  per the `private_content` capability in `docs/observability.md`) without
  Jordan's eyes on the Logfire UI.
- Same for Live Evals: Claude can pull `gen_ai.evaluation.result` events
  directly and confirm `groundedness` results are scoped to `claw-main` only,
  not present for `med-check`.

## 10-minute execution checklist (Jordan)

1. Open Logfire (`https://logfire-us.pydantic.dev`), select the `jb_homebase` project.
2. Open the SQL editor.
3. Paste alert 1's query, run it, adjust column names if the editor errors, confirm it returns a sane count.
4. Repeat step 3 for alerts 2, 3, 4.
5. For each of the 4 queries: create an alert from it with the schedule, threshold, and channel listed above.
6. Add an email notification channel pointed at Jordan's Fastmail address (if not already configured) and attach it to all 4 alerts.
7. Run `claude mcp add logfire --transport http https://logfire-us.pydantic.dev/mcp` in a terminal.
8. Run `/mcp` in Claude Code, complete the OAuth flow.
9. Sanity check: ask Claude to query the Logfire MCP for the last hour of `agent_run` spans and confirm it gets real data back.
