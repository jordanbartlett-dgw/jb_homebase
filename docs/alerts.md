# Alerts

Logfire alerts on top of the tracing already in place (see `docs/observability.md`).
The system is quiet-nightly by design: evals run once a day, dashboards are pull,
not push. Alerts are the push layer. Each one below closes a specific incident
class we've already hit or specifically want to catch before it repeats, not a
generic "something might be wrong" tripwire.

Logfire alerts are SQL queries over the `records` table, evaluated on a
schedule, firing to a notification channel (email or Slack). The UI has no
separate threshold field: the threshold lives in the SQL as a `having` clause,
the alert is set to fire when the query HAS RESULTS, and the "Look at rows
from" window must be at least as wide as the query's own interval or the data
is silently truncated. Span/log attributes live in the `attributes` JSON
column: `attributes->>'agent_slug'` style. Column
names below (`start_timestamp`, `span_name`, `attributes`) are Logfire's standard
`records` schema as of this writing. **Test-run every query in the Logfire SQL
editor before wiring it to an alert.** A drifted column name usually errors
immediately, an easy one-line fix. But a filter that is syntactically valid and
semantically wrong (wrong span name, wrong attribute key) returns zero rows
silently instead of erroring. That's why each alert's test step below requires
a positive control, not just "run it and see if it errors."

## 1. Agent error rate

Closes: repeated tool/model failures going unnoticed between nightly eval runs.

```sql
select count(*) as failure_count
from records
where span_name = 'agent_run'
  and attributes->>'outcome.success' = 'false'
  and start_timestamp > now() - interval '15 minutes'
having count(*) > 3
```

- Fire when: has results. Look at rows from: the last hour. Check every: 5 min.
- Healthy preview: no rows.
- Channel: email to Jordan's Fastmail. Slack webhook is the alternative if email gets noisy.

## 2. Daily cost ceiling

Closes: a runaway loop or pricing bug burning spend silently until someone checks the dashboard.

```sql
select sum((attributes->>'usage.cost_usd')::float8) as total_cost_usd
from records
where span_name = 'agent_run'
  and start_timestamp > now() - interval '24 hours'
having sum((attributes->>'usage.cost_usd')::float8) > 10
```

- Fire when: has results. Look at rows from: the last day (must cover the 24h sum). Check every: hour.
- Healthy preview: no rows.
- Channel: email to Jordan's Fastmail.

## 3. Trace-silence heartbeat

Closes: the polling-liveness blind spot from the sonnet-4 retirement incident
(both bots down ~3 weeks, evals stayed green because they pin their own model).

The scheduler's own 60s check loop (`CHECK_INTERVAL_SECONDS` in
`proactive/scheduler.py`) does not emit a span, it only calls `dispatch_task`
(which opens the `proactive.dispatch` span) when a schedule is actually due.
The cadence guarantee comes from the `fastmail_watch` and `agentmail_watch`
schedules, both seeded `*/5 * * * *` (migrations 013 and 029), so
`proactive.dispatch` spans fire roughly every 5 minutes as long as those
watchers are enabled. 45 minutes with zero `agent_run` or `proactive.dispatch`
spans means the process is wedged, not that traffic is quiet. If those watcher
schedules are ever disabled or their cadence slowed, revisit this alert's
45-minute window, it stops being a valid heartbeat.

```sql
select count(*) as span_count
from records
where span_name in ('agent_run', 'proactive.dispatch')
  and start_timestamp > now() - interval '45 minutes'
having count(*) = 0
```

An aggregate query over zero matching rows still returns one row (count = 0),
so `having count(*) = 0` yields a row exactly when everything is silent, which
is when the alert should fire.

- Fire when: has results. Look at rows from: the last hour. Check every: 15 min.
- Healthy preview: no rows (watchers dispatch every ~5 min).
- Channel: email to Jordan's Fastmail. This one earns Slack too if/when Slack is wired up. Silence alerts are the ones you want redundant.

## 4. Online-eval failures

Closes: quality regressions in live traffic that would otherwise sit unseen until
the next nightly offline eval run picks them up (or doesn't, since offline evals
score fixed datasets, not live traffic).

Online-eval results are emitted as raw OTel LOG records (`pydantic_evals/_otel_emit.py`
calls the OTel Logs API, not the tracing API), not spans. Whether Logfire
populates `span_name` for a log event's `event_name` is unverified. Try the
span_name filter first; if the positive-control test below comes back zero,
fall back to filtering on `kind = 'log'` plus an attribute-existence check.

Attempt 1 (span_name filter):

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
having count(*) > 2
```

Fallback (if attempt 1's positive control returns zero): filter on record kind
instead of span name, and gate on the attribute existing at all rather than
assuming it lands on `span_name`:

```sql
select count(*) as failure_count
from records
where kind = 'log'
  and attributes ? 'gen_ai.evaluation.name'
  and start_timestamp > now() - interval '1 hour'
  and (
    attributes->>'error.type' is not null
    or (
      attributes->>'gen_ai.evaluation.name' = 'OutputSanity'
      and (attributes->>'gen_ai.evaluation.score.value')::float8 = 0
    )
  )
having count(*) > 2
```

- Fire when: has results. Look at rows from: the last hour. Check every: 15 min.
- Channel: email to Jordan's Fastmail.
- Note: online eval judge sampling defaults to `0.0` (see `docs/observability.md`
  "Online evaluation"). `OutputSanity` runs at `sample_rate=1.0` regardless, so
  this alert is live even with the judge off. If the judge gets enabled later,
  this query can be widened to include `groundedness` failures.
- **Test requirement before saving this alert (positive control, required, not
  optional):** trigger one real run first (a single `/app/messages` round-trip
  is enough, the deterministic `OutputSanity`/`MaxToolCalls` evaluators fire on
  every run) so at least one `gen_ai.evaluation.result` record exists in the
  window, then run the query and confirm it returns a nonzero count for the
  success case (adjust the WHERE to count all results, not just failures, for
  this check). A zero result here means the filter shape is wrong, not that
  there are no failures. Do not wire this alert to a schedule until the
  positive control confirms the query actually sees the records.

## Logfire MCP

Connects Claude Code sessions directly to Logfire so traces, exceptions,
dashboards, and alerts can be queried without Jordan pasting screenshots.

Setup:

```bash
claude mcp add logfire --transport http https://logfire-us.pydantic.dev/mcp
```

Then run `/mcp` in Claude Code and authenticate (interactive, OAuth, Jordan runs
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
3. Paste alert 1's query, run it, adjust column names if the editor errors, confirm it returns a sane count (a zero here is plausible if no runs have failed recently, that's fine).
4. Repeat step 3 for alerts 2 and 3.
5. For alert 4: send one `/app/messages` round-trip first (the positive control), then run attempt 1's query (count all results, not just failures) and confirm it returns nonzero. If it returns zero, switch to the fallback query and repeat the check. Do not proceed to alert creation until one of the two returns nonzero on the positive control.
6. For each of the 4 queries: create an alert from it. Fire when = has results (never "results change"), with the look-at-rows-from window and check interval listed above. The having clause IS the threshold.
7. Add an email notification channel pointed at Jordan's Fastmail address (if not already configured) and attach it to all 4 alerts.
8. Run `claude mcp add logfire --transport http https://logfire-us.pydantic.dev/mcp` in a terminal.
9. Run `/mcp` in Claude Code, complete the OAuth flow.
10. Sanity check: ask Claude to query the Logfire MCP for the last hour of `agent_run` spans and confirm it gets real data back.
