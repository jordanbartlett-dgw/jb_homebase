"""Pydantic Evals harness for Jordan Claw.

Top-level package — NOT under tests/ — because eval runs spend money on LLM
judges and OpenAI embeddings. Run via the `claw-eval` CLI; nightly Railway
cron emits `eval_run_completed` to PostHog.
"""
