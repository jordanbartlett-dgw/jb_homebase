"""Polling-task liveness must be reflected in the running-bots set.

The /health blind spot: bots were added to the running set as soon as their
token was non-empty, before start_polling was confirmed alive, and a dying
polling task (revoked token, auth failure) was silently swallowed — health
kept reporting the bot as running. watch_polling_liveness closes that gap.
"""

from __future__ import annotations

import asyncio

import pytest

from jordan_claw.channels.telegram import watch_polling_liveness


async def _boom() -> None:
    raise RuntimeError("Unauthorized: bot token revoked")


async def _returns_cleanly() -> None:
    return None


async def _sleeps_forever() -> None:
    await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_crashed_polling_task_evicts_bot_from_running_set():
    bots = {"workout-coach": object()}
    task = asyncio.create_task(_boom())
    watch_polling_liveness(task, agent_slug="workout-coach", bots=bots)

    with pytest.raises(RuntimeError):
        await task
    await asyncio.sleep(0)  # let the done-callback run

    assert "workout-coach" not in bots


@pytest.mark.asyncio
async def test_unexpected_clean_return_also_evicts_bot():
    # start_polling only returns via cancellation in normal operation; a clean
    # return means the bot is no longer polling and must not report healthy.
    bots = {"workout-coach": object()}
    task = asyncio.create_task(_returns_cleanly())
    watch_polling_liveness(task, agent_slug="workout-coach", bots=bots)

    await task
    await asyncio.sleep(0)

    assert "workout-coach" not in bots


@pytest.mark.asyncio
async def test_shutdown_cancellation_does_not_evict_bot():
    bots = {"claw-main": object()}
    task = asyncio.create_task(_sleeps_forever())
    watch_polling_liveness(task, agent_slug="claw-main", bots=bots)

    await asyncio.sleep(0)  # let the task start
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    assert "claw-main" in bots


@pytest.mark.asyncio
async def test_eviction_only_touches_own_slug():
    bots = {"claw-main": object(), "workout-coach": object()}
    task = asyncio.create_task(_boom())
    watch_polling_liveness(task, agent_slug="workout-coach", bots=bots)

    with pytest.raises(RuntimeError):
        await task
    await asyncio.sleep(0)

    assert "claw-main" in bots
    assert "workout-coach" not in bots
