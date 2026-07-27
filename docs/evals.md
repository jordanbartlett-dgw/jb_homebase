# Evals

Pydantic Evals against Jordan Claw, run via the `claw-eval` CLI.

## What it covers

| Dataset | Cases | Scoring | Target model | Cost / run |
|---|---|---|---|---|
| `memory_recall` | 20 | `required_facts` (substring match) + `llm_judge` (LLMJudge rubric, central judge model) | `anthropic:claude-sonnet-4-5-20250929` | ~$0.09 (`--repeat 3`) |
| `obsidian_retrieval` | 20 | `top_k_membership` (set membership in top-3) | `openai:text-embedding-3-small` (embeddings only, no chat call) | ~$0.001 |
| `med_check` | 12 | `phrase_assertion` (custom scorer) + `MaxToolCalls` (agentic guard against runaway tool loops) | `anthropic:claude-sonnet-5` | ~$0.76 |
| `email_triage` | 10 | `triage_phrase` (custom scorer, incl. injection resistance) + `MaxToolCalls` | `anthropic:claude-sonnet-5` | ~$0.04 |
| `tool_routing` | 10 | Agentic evaluators only, no custom scorer: `ToolCorrectness`/`TrajectoryMatch` (per-case) + `MaxToolCalls` (dataset-level runaway guard) | `anthropic:claude-sonnet-5` | ~$0.18 |
| `code_mode` | 6 | Agentic evaluators only, no custom scorer: `ToolCorrectness` (per-case) + `MaxToolCalls` (dataset-level) + built-in `Contains` | `anthropic:claude-sonnet-5` | ~$0.10 |

Costs are actuals pulled from the reports each dataset's current baseline was saved
from (`evals/reports/{dataset}_{ts}.json`, `cost_usd`), not estimates. They will drift
as case counts or models change. `claw-eval list` always shows the live case count and
target model, and `evals/reports/` holds the ground truth per-run cost.

A run produces:
- A console summary (per-evaluator score, prev_score, regression flag)
- A JSON report under `evals/reports/{dataset}_{ts}.json` (gitignored, full-fidelity:
  every case's inputs/output/scores/reasons/trace_id, plus token/cost totals)
- A Logfire experiment (see below)
- A `usage_events` row (`agent_slug = eval:{dataset}`, `channel = eval`) so eval spend
  shows up in the same cost accounting as production traffic
- A PostHog `eval_run_completed` event (`distinct_id = system:eval`)
- An optional baseline write to `evals/baselines/{dataset}.json` (committed)

## Running locally

```bash
infisical run --env=dev -- uv run claw-eval run obsidian_retrieval
infisical run --env=dev -- uv run claw-eval run memory_recall
infisical run --env=dev -- uv run claw-eval run --all

# Judge-bearing datasets: repeat each case to smooth judge variance before
# trusting a score (3x is the convention used for baseline saves).
infisical run --env=dev -- uv run claw-eval run memory_recall --repeat 3

# Cap concurrent case evaluations (default 4). Lower it if a target agent's
# tools are rate-limited.
infisical run --env=dev -- uv run claw-eval run med_check --concurrency 2

# Save the current score as the new regression baseline (single dataset only)
infisical run --env=dev -- uv run claw-eval run memory_recall --repeat 3 --save-baseline

# Machine-readable output: one JSON summary line per dataset on stdout, all
# human-readable output (progress, logfire console spans, log lines) on stderr.
infisical run --env=dev -- uv run claw-eval run --all --json > summaries.jsonl

# List every registered dataset: cases, evaluators, target model, baseline.
# No API keys needed, this does not call get_settings().
uv run claw-eval list

# Diff the two most recent reports for a dataset (per-evaluator delta table).
# Also no API keys needed.
uv run claw-eval compare med_check
```

`claw-eval compare` errors with a clear message and exit code 1 if fewer than two
reports exist for that dataset yet. Run it twice first.

## Seeding the eval corpus

The `obsidian_retrieval` dataset reads from a synthetic corpus seeded into the
shared dev Supabase project under a dedicated org id. Re-seed any time
`evals/fixtures/corpus.yaml` changes:

```bash
infisical run --env=dev -- uv run python -m evals.seed_corpus
```

Idempotent. Keyed on `(org_id, vault_path)` and skips unchanged content via a
hash check.

## Isolation

| Layer | Mechanism |
|---|---|
| Org-scoped reads | All Obsidian reads filter by `org_id` in app code (`db/obsidian.py`) |
| RLS deny-all | Migration 003 enables RLS on `obsidian_notes` / `obsidian_note_chunks` with no policies. Anon-key returns zero rows |
| Verification gate | `tests/test_evals_isolation.py` blocks merge if anon-key ever returns rows |

The eval-only org id is `eaa1eaa1-eaa1-eaa1-eaa1-eaa1eaa1eaa1` (set as
`Settings.eval_test_org_id`). All fixture notes use `vault_path = evals/{slug}.md`
to prevent collision with real notes if the eval org id ever shifted.

## Baselines and regression detection

Baselines live at `evals/baselines/{dataset}.json`, schema v2:

```json
{
  "schema": 2,
  "dataset": "memory_recall",
  "ran_at": "...",
  "git_sha": "...",
  "composite": 0.967,
  "evaluators": {"required_facts": 0.983, "llm_judge": 0.95},
  "cases_total": 20,
  "cases_passed": 20
}
```

`evaluators` holds the per-evaluator average alongside the composite (the mean across
evaluators). A run is flagged as a regression when **either**:

- the composite drops more than 5pp vs the baseline composite, or
- any evaluator present in both the current run and the baseline drops more than
  `max(5pp, 1.5 / cases_total)`, even if the composite barely moves. The threshold
  scales down as the dataset grows: on a 12-case dataset it takes roughly two flipped
  cases to flag, not one, because per-run judge noise alone has been measured at up to
  7.5pp; on datasets past ~30 cases the flat 5pp floor applies as before.

`TrajectoryMatch` is informational only: it never flags a regression, but a drop past
its threshold still appends an `"info: TrajectoryMatch ..."` reason so the CLI surfaces
it. An evaluator only on one side (added or removed since the baseline) is reported as
informational, `new evaluator: X` / `missing evaluator: X`, and never flags on its
own. That's a code change, not a quality drop. v1 baselines (pre-per-evaluator, just a
`score` field) still load and compare on composite only.

The regression flag rides on the `eval_run_completed` PostHog event as `regression:
bool`, alongside `cost_usd`. Configure a PostHog action on `regression = true` for
alerting, and on cost if you want a spend ceiling alert.

Exit codes:
- **2**: any dataset in the run regressed. Takes precedence.
- **1**: no regression, but at least one case's task_fn raised (`report.failures`
  non-empty).
- **0**: clean.

A Railway cron job reports non-zero on either condition.

## Logfire experiments

Every `claw-eval run` names its Pydantic Evals run as a Logfire **experiment**:
`{dataset}@{git_sha}` (e.g. `memory_recall@a9849ae`, or `@local` outside a git repo).
Logfire UI, Evals section, shows the experiment list. Open one to see per-case spans,
scores, and reasons (LLMJudge reasons included). To compare two runs, open both
experiments' Evals views side by side, or diff `evals/reports/` locally with
`claw-eval compare`.

`console=False` is set on `logfire.configure()` when `--json` is passed, so the console
span printer (which writes to stdout by default) doesn't interleave with the JSON
summary lines.

## Adding a dataset

1. Add typed `Inputs`/`Expected`/`Output` to `evals/types.py`.
2. Implement the task fn under `evals/tasks/{name}.py`. Export a `TARGET_MODEL`
   constant from the module if the task calls a chat model. The registry entry and
   `claw-eval list` both read it.
3. Add a custom scorer to `evals/scorers/{name}.py` if the built-in evaluators
   (`LLMJudge`, `Contains`, `ToolCorrectness`, `TrajectoryMatch`, `MaxToolCalls`, ...)
   don't cover it; export from `evals/scorers/__init__.py`.
   If the task fn needs to stub tools for an agentic evaluator (`ToolCorrectness`,
   `TrajectoryMatch`), don't hand-write new docstrings on the stubs. Clone `__doc__`
   from the real tool functions (`stub.__doc__ = real_tools.stub.__doc__`), as
   `evals/tasks/tool_routing.py`, `code_mode.py`, and `email_triage.py` do. Tool
   docstrings are the LLM's actual routing signal in prod (repo discipline, see
   `CLAUDE.md`). A stub with an eval-only docstring would score against a routing
   signal the model never sees for real.
4. Author the YAML at `evals/datasets/{name}.yaml`. Agentic evaluators
   (`ToolCorrectness`, `TrajectoryMatch`, `MaxToolCalls`) are usually per-case
   (`cases[].evaluators`) since expected tools differ per case; dataset-wide guards
   (e.g. a global `MaxToolCalls` ceiling) go in the top-level `evaluators:` key.
   `LLMJudge` entries must never carry a `model:` key. The judge model is centralized
   via `set_default_judge_model()` in the CLI (`tests/test_evals_smoke.py` enforces this).
5. Register in `evals/registry.py:REGISTRY` with an `EvalSpec`, including `target_model`.
6. Run `claw-eval run {name} --save-baseline` (add `--repeat 3` if the dataset has an
   LLMJudge, to smooth judge variance) and commit the baseline.
7. Run `claw-eval list` to sanity-check the new row: case count, evaluator names,
   target model, baseline all show up as expected.

## Railway cron

Eval runs take minutes and are not safe to put on the in-process 60s scheduler.
Run as a separate Railway cron service against the same image.

**Live as of 2026-05-22**: service `evals-cron` in `JB-HomeBase/production`.

- Schedule: `0 3 * * *` (nightly 03:00 UTC)
- Start command: `uv run claw-eval run --all`
- Restart policy: `Never`
- Healthcheck: disabled

**Required env vars** (all referenced from the `jb_homebase` service via
`${{ jb_homebase.VAR }}` so secrets are not duplicated):

```
ANTHROPIC_API_KEY, OPENAI_API_KEY, TAVILY_API_KEY,
SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY,
LOGFIRE_TOKEN, POSTHOG_API_KEY, DEFAULT_ORG_ID,
FASTMAIL_USERNAME, FASTMAIL_APP_PASSWORD
```

`TELEGRAM_BOT_TOKEN` is **not** required. Telegram was removed from the stack and
`telegram_bot_token` is no longer a `Settings` field. The Fastmail keys aren't *used* by
any eval task directly, but `get_settings()` still requires them since `Settings` is
shared with the main gateway process. The CLI calls `get_settings()` at startup (for
`run`, not for `list`/`compare`) and exits with a clear error if any required var is
missing. Without this guard, pydantic-evals silently drops every case whose task fn
raises a settings `ValidationError`, producing a phantom regression (see commit
`20d622f` for the fix).

Each nightly run writes one `usage_events` row per dataset (`agent_slug =
eval:{dataset}`, `channel = eval`) and one `eval_run_completed` PostHog event per
dataset, carrying `cost_usd` and `regression`. Cron exits non-zero on regression
(exit 2) or bare failures (exit 1), surfacing as a failed run in Railway.

## Why this exists

Demo-quality observability (PR1-PR4) tells you what happened. Evals tell you
whether it was any good. Catching a regression here is cheap. Catching it from
a degraded user experience is not.
