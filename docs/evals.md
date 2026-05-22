# Evals

Pydantic Evals against Jordan Claw, run via the `claw-eval` CLI.

## What it covers

| Dataset | Cases | Scoring | Cost / run |
|---|---|---|---|
| `memory_recall` | 20 | `required_facts` (substring match) + `llm_judge` (Sonnet 4.5 rubric) | ~$0.10 |
| `obsidian_retrieval` | 20 | `top_k_membership` (set membership in top-3) | ~$0.001 (embeddings only) |

A run produces:
- A console summary (per-evaluator score, prev_score, regression flag)
- A JSON report under `evals/reports/{dataset}_{ts}.json` (gitignored)
- A PostHog `eval_run_completed` event (`distinct_id = system:eval`)
- An optional baseline write to `evals/baselines/{dataset}.json` (committed)

## Running locally

```bash
infisical run --env=dev -- uv run claw-eval run obsidian_retrieval
infisical run --env=dev -- uv run claw-eval run memory_recall
infisical run --env=dev -- uv run claw-eval run --all

# Save the current score as the new baseline (single dataset only)
infisical run --env=dev -- uv run claw-eval run memory_recall --save-baseline
```

## Seeding the eval corpus

The `obsidian_retrieval` dataset reads from a synthetic corpus seeded into the
shared dev Supabase project under a dedicated org id. Re-seed any time
`evals/fixtures/corpus.yaml` changes:

```bash
infisical run --env=dev -- uv run python -m evals.seed_corpus
```

Idempotent — keyed on `(org_id, vault_path)` and skips unchanged content via a
hash check.

## Isolation

| Layer | Mechanism |
|---|---|
| Org-scoped reads | All Obsidian reads filter by `org_id` in app code (`db/obsidian.py`) |
| RLS deny-all | Migration 003 enables RLS on `obsidian_notes` / `obsidian_note_chunks` with no policies — anon-key returns zero rows |
| Verification gate | `tests/test_evals_isolation.py` — blocks merge if anon-key ever returns rows |

The eval-only org id is `eaa1eaa1-eaa1-eaa1-eaa1-eaa1eaa1eaa1` (set as
`Settings.eval_test_org_id`). All fixture notes use `vault_path = evals/{slug}.md`
to prevent collision with real notes if the eval org id ever shifted.

## Regression detection

Baselines live at `evals/baselines/{dataset}.json`. A run is flagged as a
regression when `current_score < baseline.score - 0.05` (5pp tolerance). The
flag rides on the `eval_run_completed` PostHog event as `regression: bool`;
configure a PostHog action on `regression = true` for alerting.

The CLI exits with code 2 on regression so a Railway cron job will report
non-zero on quality drops.

## Adding a dataset

1. Add typed `Inputs`/`Expected`/`Output` to `evals/types.py`.
2. Implement the task fn under `evals/tasks/{name}.py`.
3. Add a custom scorer to `evals/scorers/{name}.py` if needed; export from `evals/scorers/__init__.py`.
4. Author the YAML at `evals/datasets/{name}.yaml`.
5. Register in `evals/registry.py:REGISTRY`.
6. Run `claw-eval run {name} --save-baseline` and commit the baseline.

## Railway cron

Eval runs take minutes and are not safe to put on the in-process 60s scheduler.
Run as a separate Railway cron service against the same image:

- Schedule: `0 3 * * *` (nightly 03:00 UTC)
- Start command: `uv run claw-eval run --all`
- Env: same as the FastAPI service (Anthropic + OpenAI + Supabase + PostHog keys)

Cron exits non-zero on regression, surfacing as a failed run in Railway and a
`regression: true` event in PostHog.

## Why this exists

Demo-quality observability (PR1–PR4) tells you what happened. Evals tell you
whether it was any good. Catching a regression here is cheap; catching it from
a degraded user experience is not.
