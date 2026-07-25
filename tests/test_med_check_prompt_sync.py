"""Byte-compare the three in-repo copies of the med-check system prompt: the
SQL literal in migration 027, MED_CHECK_PROMPT in evals/tasks/med_check.py,
and the fenced "deployed system prompt" block in docs/med-check-agent.md.

No API, no network — pure text extraction and comparison. Catches drift
between the three copies; it cannot catch drift against the live DB row
(that still needs a manual read-back, see docs/med-check-agent.md).
"""

from __future__ import annotations

import re
from pathlib import Path

from evals.tasks.med_check import MED_CHECK_PROMPT

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = REPO_ROOT / "supabase/migrations/027_med_check_prompt_v3.sql"
DOC_PATH = REPO_ROOT / "docs/med-check-agent.md"

# Matches the system_prompt string literal in the UPDATE statement. SQL ''
# is the escaped single quote and gets unescaped to '.
_SQL_PROMPT_RE = re.compile(r"UPDATE agents SET system_prompt = '(.*?)'\nWHERE slug", re.DOTALL)

# The doc has exactly one fenced block: the "Deployed system prompt" section.
_DOC_FENCE_RE = re.compile(r"```\n(.*?)\n```", re.DOTALL)


def _extract_sql_prompt() -> str:
    sql = MIGRATION_PATH.read_text()
    match = _SQL_PROMPT_RE.search(sql)
    assert match, "could not locate system_prompt literal in migration 027 SQL"
    return match.group(1).replace("''", "'")


def _extract_doc_prompt() -> str:
    doc = DOC_PATH.read_text()
    match = _DOC_FENCE_RE.search(doc)
    assert match, "could not locate fenced prompt block in docs/med-check-agent.md"
    return match.group(1)


def test_sql_and_eval_prompts_match():
    assert _extract_sql_prompt() == MED_CHECK_PROMPT


def test_sql_and_doc_prompts_match():
    assert _extract_sql_prompt() == _extract_doc_prompt()


def test_eval_and_doc_prompts_match():
    assert _extract_doc_prompt() == MED_CHECK_PROMPT
