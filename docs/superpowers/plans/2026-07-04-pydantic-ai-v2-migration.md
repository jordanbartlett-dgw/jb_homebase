# Pydantic AI v2 Migration (PR1: Compat) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move jb_homebase from pydantic-ai-slim 1.75.0 to 2.0.x with zero behavior change, keeping the current agent architecture intact.

**Architecture:** Mechanical compat migration only. The v1 `history_processors=` constructor arg becomes a `ProcessHistory` capability, `result.usage()` becomes a property, tests move off private toolset internals onto the public TestModel inspection API, and evals scorers adopt the v2 evaluator-name override method. `end_strategy` is pinned to `'early'` to preserve v1 tool-skipping behavior. Adopting the capabilities architecture (deferred capabilities per tool group) is a separate follow-up plan (PR2), written only after this lands.

**Tech Stack:** pydantic-ai-slim[anthropic] 2.0.x, pydantic-evals 2.0.x, logfire, pytest via `uv run pytest`.

**Decisions taken (Jordan was AFK; both were the recommended options — flag if you disagree):**
1. Two-PR approach: this plan is PR1 (compat only). PR2 (capabilities architecture) gets its own plan after PR1 merges.
2. `end_strategy='early'` pinned on the main agent to preserve exact v1 behavior. Evaluating v2's `'graceful'` default is deferred to PR2 with eval coverage.

**Reference:** `~/.claude/skills/pydantic-ai/references/v2-migration.md` has the full breaking-change list. Upstream: https://pydantic.dev/docs/ai/project/changelog/

**API-signature caution:** Code below for v2-new APIs (`ProcessHistory`, `TestModel.last_model_request_parameters`, `get_default_evaluation_name`) was written from official docs, not against the installed package. Task 2 Step 3 verifies the real signatures; adjust call sites if they differ, and note the difference in the commit message.

---

### Task 1: Branch off main and step up to latest v1

The upstream-recommended path is latest v1 → clear deprecation warnings → v2. The repo is already clean on 1.x names (`output_type`, `.output`, `RunUsage`), so expect few warnings, but look anyway.

**Files:**
- Modify: `pyproject.toml:9` and `:24`

- [ ] **Step 1: Create the branch from main**

```bash
cd /home/jb/Developer/jb_homebase
git checkout main && git pull
git checkout -b feature/pydantic-ai-v2
```

Note: `feature/flutter-app` has two uncommitted untracked paths (`.github/`, `docs/newsletter-case-study.md`). They are untracked, so they survive the checkout; leave them alone.

- [ ] **Step 2: Bump to latest v1**

In `pyproject.toml` change:

```toml
    "pydantic-ai-slim[anthropic]>=1.75.0",
```
to
```toml
    "pydantic-ai-slim[anthropic]>=1.100.0,<2",
```
and
```toml
    "pydantic-evals>=1.75.0",
```
to
```toml
    "pydantic-evals>=1.100.0,<2",
```

Then: `uv sync` (if 1.100.0 doesn't exist, `uv` will say so — use the highest 1.x it reports; check with `uv run python -c "import pydantic_ai; print(pydantic_ai.__version__)"`).

- [ ] **Step 3: Run the pydantic-ai-touching tests with deprecation warnings visible**

```bash
uv run pytest tests/test_agents.py tests/test_agent_runner.py tests/test_evals_smoke.py tests/test_memory_extractor.py tests/test_obsidian_tools.py -W always::DeprecationWarning 2>&1 | grep -iE "deprecat|PASS|FAIL|passed|failed"
```

Expected: all pass; DeprecationWarnings likely for `history_processors=` (factory.py:49), `evaluation_name` class attr (both scorers), possibly `result.usage()` and `system_prompt=` (extractor.py:49).

- [ ] **Step 4: Fix ONLY what warns, nothing else.** If a warning names a v2 API that doesn't exist in v1 (unlikely), leave it for the v2 tasks below. Re-run Step 3 until warning-free.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: bump pydantic-ai to latest v1, clear deprecation warnings"
```
(Include any warning fixes in this commit.)

---

### Task 2: Upgrade dependencies to v2

**Files:**
- Modify: `pyproject.toml:9`, `:24`

- [ ] **Step 1: Bump pins**

```toml
    "pydantic-ai-slim[anthropic]>=2.0.0,<3",
```
```toml
    "pydantic-evals>=2.0.0,<3",
```

Run `uv sync`. If `logfire` pins an incompatible pydantic-ai, bump `logfire[fastapi,httpx]>=3.0.0` to whatever floor `uv` needs — but ask before adding any NEW dependency.

- [ ] **Step 2: Confirm versions**

```bash
uv run python -c "import pydantic_ai, pydantic_evals; print(pydantic_ai.__version__, pydantic_evals.__version__)"
```
Expected: `2.0.x 2.0.x`

- [ ] **Step 3: Verify the v2 API surface this plan relies on**

```bash
uv run python - <<'EOF'
import inspect
from pydantic_ai.capabilities import ProcessHistory
print("ProcessHistory:", inspect.signature(ProcessHistory.__init__))
from pydantic_ai.models.test import TestModel
print("TestModel fields:", [f for f in dir(TestModel) if "last_model" in f])
from pydantic_evals.evaluators import Evaluator
print("name methods:", [m for m in dir(Evaluator) if "name" in m.lower()])
from pydantic_ai import Agent
print("Agent params:", [p for p in inspect.signature(Agent.__init__).parameters if p in ("capabilities", "end_strategy", "toolsets", "history_processors")])
EOF
```

Expected: `ProcessHistory` takes a processor callable; `last_model_request_parameters` exists; `get_default_evaluation_name` exists; Agent has `capabilities`, `end_strategy`, `toolsets` and NOT `history_processors`. If any differ from the code in Tasks 3–7, adapt those tasks to the real signature.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: upgrade pydantic-ai-slim and pydantic-evals to v2"
```

Tests are expected to be BROKEN at this commit; the next tasks fix them file by file. That's fine on a feature branch.

---

### Task 3: factory.py — ProcessHistory capability + pin end_strategy

**Files:**
- Modify: `src/jordan_claw/agents/factory.py:45-51`
- Test: `tests/test_agents.py`

- [ ] **Step 1: Update the import block** (factory.py:4-5)

```python
from pydantic_ai import Agent, ModelRequest, ModelResponse, TextPart, ToolReturnPart, UserPromptPart
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.tools import RunContext, ToolDefinition
```

- [ ] **Step 2: Update the Agent construction** (factory.py:45-51)

```python
    agent = Agent(
        config.model,
        instructions=system_prompt,
        toolsets=[filtered],
        capabilities=[ProcessHistory(trim_history_processor)],
        deps_type=AgentDeps,
        # v2 default flipped to 'graceful' (function tools called alongside a
        # final output now execute). Pin v1 behavior; revisit in PR2 with evals.
        end_strategy="early",
    )
```

`trim_history_processor` itself is unchanged — it's a plain `list -> list` function and stays defined in this file.

- [ ] **Step 3: Run the factory/history tests**

```bash
uv run pytest tests/test_agents.py -x -q
```

Expected: `test_build_agent_uses_db_config` still FAILS (private `_user_toolsets` access — fixed in Task 5). History-trimming tests (`test_history_budget_truncates_oldest_messages` etc.) PASS. If ProcessHistory's signature differs from Step 1 of Task 2's findings, adapt.

- [ ] **Step 4: Commit**

```bash
git add src/jordan_claw/agents/factory.py
git commit -m "refactor: migrate history_processors to ProcessHistory capability, pin end_strategy=early"
```

---

### Task 4: agent_runner.py + extractor.py — v2 result/annotation surface

**Files:**
- Modify: `src/jordan_claw/utils/agent_runner.py:181`
- Modify: `src/jordan_claw/memory/extractor.py:45`
- Test: `tests/test_agent_runner.py`, `tests/test_memory_extractor.py`

- [ ] **Step 1: usage() method → usage property** (agent_runner.py:181)

```python
        usage = extract_usage(result.usage)
```

`extract_usage` (token_counting.py) already reads `input_tokens` / `output_tokens` / `requests` off `RunUsage` — no change there.

- [ ] **Step 2: extractor annotation for v2 type-param defaults** (extractor.py:45)

v2 changed the unparameterized deps default from `None` to `object`, so `Agent[None, ExtractionResult]` no longer matches an agent built without `deps_type`. Change:

```python
def create_extraction_agent() -> Agent[object, ExtractionResult]:
```

Leave `system_prompt=` as-is unless Task 1 Step 3 flagged it deprecated; if it did, it was already switched to `instructions=` there.

- [ ] **Step 3: Run both test files**

```bash
uv run pytest tests/test_agent_runner.py tests/test_memory_extractor.py -q
```

Expected: PASS. If `test_agent_runner.py` mocks stub `result.usage` as a method (`.usage()`), update the mocks to attributes in the same edit.

- [ ] **Step 4: Commit**

```bash
git add src/jordan_claw/utils/agent_runner.py src/jordan_claw/memory/extractor.py tests/test_agent_runner.py
git commit -m "refactor: v2 usage property and Agent type-param default in extractor"
```

---

### Task 5: test_agents.py — replace private-toolset assertions with public TestModel inspection

The current test reaches into `agent._user_toolsets[0]` and `FilteredToolset.filter_func` (test_agents.py:135-147). Those are private and break in v2. The public pattern: run the agent against a `TestModel` that calls no tools, then read which tool definitions were sent to the model.

**Files:**
- Modify: `tests/test_agents.py:116-147`

- [ ] **Step 1: Rewrite the test**

```python
@pytest.mark.asyncio
async def test_build_agent_uses_db_config():
    fake_config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="test",
        tools=["current_datetime", "search_web"],
        is_active=True,
    )

    mock_db = AsyncMock()

    with patch("jordan_claw.agents.factory.get_agent_config", return_value=fake_config):
        agent, model_name = await build_agent(mock_db, "org-001", "test-agent")

    assert model_name == "test"

    from pydantic_ai.models.test import TestModel

    from jordan_claw.agents.deps import AgentDeps

    test_model = TestModel(call_tools=[])  # send tool defs, invoke none
    deps = AgentDeps(
        org_id="org-001",
        tavily_api_key="test-key",
        fastmail_username="test@example.com",
        fastmail_app_password="test-pass",
    )
    await agent.run("hi", deps=deps, model=test_model)

    sent_tools = {t.name for t in test_model.last_model_request_parameters.function_tools}
    assert sent_tools == {"current_datetime", "search_web"}  # check_calendar filtered out
```

- [ ] **Step 2: Run it**

```bash
uv run pytest tests/test_agents.py -q
```

Expected: PASS, whole file. (If `last_model_request_parameters` was named differently in Task 2 Step 3's probe, use that name.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_agents.py
git commit -m "test: inspect filtered tools via TestModel public API instead of _user_toolsets"
```

- [ ] **Step 4: Update the stale memory file.** `~/.claude/projects/-home-jb-Developer-jb-homebase/memory/feedback_pydantic_ai_testing.md` recommends FilteredToolset inspection; edit it to record the TestModel `call_tools=[]` + `last_model_request_parameters` pattern as the v2 way (keep the "test" model and API-key-avoidance notes).

---

### Task 6: Evals — v2 evaluator naming + Dataset name

**Files:**
- Modify: `evals/scorers/memory_recall.py:17`
- Modify: `evals/scorers/obsidian_retrieval.py:20`
- Verify: `evals/run_eval.py:101-106`, `evals/datasets/memory_recall.yaml:265`
- Test: `tests/test_evals_smoke.py`

- [ ] **Step 1: Migrate `evaluation_name` class attrs to the override method**

`evals/scorers/memory_recall.py` — delete line 17 (`evaluation_name: str = "required_facts"`) and add inside the class:

```python
    def get_default_evaluation_name(self) -> str:
        return "required_facts"
```

`evals/scorers/obsidian_retrieval.py` — same change with `"top_k_membership"`.

- [ ] **Step 2: Run the smoke test**

```bash
uv run pytest tests/test_evals_smoke.py -q
```

Expected: PASS — it asserts `scores["required_facts"]`, which proves the rename took. (`Dataset(name="smoke", ...)` is already present at tests/test_evals_smoke.py:51-52, satisfying the new required arg.)

- [ ] **Step 3: Verify `Dataset.from_file` under v2** (run_eval.py:101-106 — v2 requires Dataset `name`; from_file may derive it from the YAML/filename or require a kwarg):

```bash
uv run python - <<'EOF'
import inspect
from pydantic_evals import Dataset
print(inspect.signature(Dataset.from_file))
EOF
```

If `from_file` needs `name`, change run_eval.py:101-106 to:

```python
    ds: Dataset[Any, Any, Any] = Dataset[
        spec.inputs_type, spec.expected_type, dict
    ].from_file(
        spec.yaml_path,
        name=spec.name,
        custom_evaluator_types=spec.custom_evaluators,
    )
```
If not, leave it untouched.

- [ ] **Step 4: Check the YAML LLMJudge config still loads.** `evals/datasets/memory_recall.yaml:265` sets `evaluation_name: llm_judge` on the built-in LLMJudge (an instance field, which v2 kept — the removal was for class-attr overrides). Confirm by loading the dataset without running it:

```bash
uv run python - <<'EOF'
from evals.registry import REGISTRY
from pydantic_evals import Dataset
spec = REGISTRY["memory_recall"]
ds = Dataset[spec.inputs_type, spec.expected_type, dict].from_file(
    spec.yaml_path, custom_evaluator_types=spec.custom_evaluators)
print("loaded", len(ds.cases), "cases")
EOF
```
(Add `name=spec.name` if Step 3 required it.) Expected: `loaded N cases` with no validation error. If LLMJudge rejects `evaluation_name`, move that key per the error message and re-run.

- [ ] **Step 5: Commit**

```bash
git add evals/ tests/test_evals_smoke.py
git commit -m "refactor: pydantic-evals v2 evaluator naming and dataset loading"
```

---

### Task 7: Instrumentation check (Logfire + dashboards)

v2 defaults to instrumentation format 5: run-span usage moves to `gen_ai.aggregated_usage.*`. Our own `agent_run` span writes custom `usage.*` attributes (agent_runner.py:238-242) — those are ours and unaffected. The risk is only in things reading pydantic-ai's own spans.

**Files:**
- Verify: `src/jordan_claw/main.py:57-65`

- [ ] **Step 1: Confirm `logfire.instrument_pydantic_ai()` works against v2**

```bash
uv run python - <<'EOF'
import logfire
logfire.configure(send_to_logfire=False)
logfire.instrument_pydantic_ai()
print("instrumented OK")
EOF
```

Expected: `instrumented OK`. If it raises, bump `logfire` (Task 2 Step 1 note) — current pin is `logfire[fastapi,httpx]>=3.0.0` (pyproject.toml:22).

- [ ] **Step 2: Repo-side dashboard check** — already verified during planning: `grep -rn "gen_ai" src/ evals/` returns nothing, so no code reads pydantic-ai span attributes. FLAG FOR JORDAN in the PR description: any hand-built Logfire dashboard querying `gen_ai.usage.*` on pydantic-ai run spans needs re-pointing to `gen_ai.aggregated_usage.*` after this deploys. (The PostHog analytics events come from our emitter, not spans — unaffected.)

- [ ] **Step 3: Commit** (only if Step 1 forced a logfire bump)

```bash
git add pyproject.toml uv.lock
git commit -m "chore: bump logfire for pydantic-ai v2 instrumentation"
```

---

### Task 8: Full verification and PR

A dependency major-version migration is the one case where the full suite earns its cost.

- [ ] **Step 1: Full test suite** (deliberate exception to the single-tests default)

```bash
uv run pytest -q
```

Expected: all pass. Fix any straggler the file-by-file tasks missed (most likely: another mock stubbing `.usage()` as a method).

- [ ] **Step 2: Ruff**

```bash
uv run ruff check src/ tests/ evals/ && uv run ruff format --check src/ tests/ evals/
```

- [ ] **Step 3: Eval harness dry check** — the nightly evals-cron on Railway pins its own model and spends money, so do NOT run production datasets locally. The smoke test (Task 6 Step 2) plus dataset-load check (Task 6 Step 4) is the local evidence. After deploy, watch the first nightly run per the evals memory.

- [ ] **Step 4: Push and open PR against main**

```bash
git push -u origin feature/pydantic-ai-v2
gh pr create --base main --title "chore: migrate to pydantic-ai v2 (compat pass)" --body "$(cat <<'EOF'
## Summary
- pydantic-ai-slim 1.75 → 2.0.x, pydantic-evals → 2.0.x (via latest-v1 deprecation pass first)
- history_processors → ProcessHistory capability; end_strategy pinned to 'early' (v1 behavior; 'graceful' evaluated in PR2)
- result.usage() → property; Agent[None,...] → Agent[object,...]
- tests off private _user_toolsets onto TestModel public API
- evals: evaluator name override methods; Dataset name handling

## Flag for Jordan
- Any Logfire dashboard reading gen_ai.usage.* on pydantic-ai spans must move to gen_ai.aggregated_usage.* (format v5). Our custom agent_run span attrs are unchanged.
- Watch the first nightly evals-cron run after deploy.

## Not in this PR
- Capabilities architecture adoption (deferred capabilities per tool group) — PR2, separate plan.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 5: After merge → Railway deploy watch.** Push to main triggers Railway deploy of "JB-HomeBase". Use the deploy-verify skill: hit the health endpoint, send a Telegram message end-to-end, and confirm a `usage_events` row lands (query it, per verification rules). Both bots (Claw main + workout coach) must respond — the model-retirement incident showed silent both-bot failure is possible.

---

## PR2 (separate plan, do not start): capabilities architecture

Written after PR1 merges and Jordan approves scope. Candidate shape, for context only: convert tool groups (calendar, obsidian, memory, workout, web) into `Capability` bundles with per-group instructions; replace `_make_tool_filter` org-config filtering by selecting capability lists per agent config; evaluate `defer_loading=True` for infrequently used groups (token savings on every Telegram turn); reconsider `end_strategy='graceful'` with eval coverage for tool-alongside-output; consider `Hooks`/`wrap_run` to replace parts of the manual `agent_run` span in `run_agent_instrumented`.
