"""Byte-compare the two in-repo copies of the agent_inbox_review email-triage
prompt: the SQL literal in migration 031 and TRIAGE_PROMPT_TEMPLATE in
evals/tasks/email_triage.py.

No API, no network — pure text extraction and comparison. Catches drift
between the two copies; it cannot catch drift against the live DB row (that
still needs a manual read-back).
"""

from __future__ import annotations

import re
from pathlib import Path

from evals.tasks.email_triage import TRIAGE_PROMPT_TEMPLATE

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = REPO_ROOT / "supabase/migrations/031_fence_agentmail_trigger.sql"

# Matches the prompt_template string literal in the UPDATE statement. SQL ''
# is the escaped single quote and gets unescaped to '.
_SQL_PROMPT_RE = re.compile(r"SET prompt_template = '(.*?)'\nWHERE source", re.DOTALL)


def _extract_sql_prompt() -> str:
    sql = MIGRATION_PATH.read_text()
    match = _SQL_PROMPT_RE.search(sql)
    assert match, "could not locate prompt_template literal in migration 031 SQL"
    return match.group(1).replace("''", "'")


def test_sql_and_eval_prompts_match():
    assert _extract_sql_prompt() == TRIAGE_PROMPT_TEMPLATE
