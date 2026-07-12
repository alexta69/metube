"""Tests for the ``bg_tasks.create_task`` strong-reference/logging helper."""

from __future__ import annotations

import asyncio
import logging

import pytest

import bg_tasks


@pytest.mark.asyncio
async def test_create_task_removes_itself_from_registry_on_success():
    async def _ok():
        return 42

    task = bg_tasks.create_task(_ok(), name="ok_task")
    assert task in bg_tasks._TASKS
    result = await task
    assert result == 42
    assert task not in bg_tasks._TASKS


@pytest.mark.asyncio
async def test_create_task_logs_unhandled_exception(caplog):
    async def _boom():
        raise ValueError("kaboom")

    with caplog.at_level(logging.ERROR, logger="bg_tasks"):
        task = bg_tasks.create_task(_boom(), name="boom_task")
        with pytest.raises(ValueError):
            await task
        # Let the done-callback (scheduled via call_soon) run.
        await asyncio.sleep(0)

    assert task not in bg_tasks._TASKS
    assert any("boom_task" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_create_task_does_not_log_on_cancellation(caplog):
    async def _sleep_forever():
        await asyncio.sleep(10)

    with caplog.at_level(logging.ERROR, logger="bg_tasks"):
        task = bg_tasks.create_task(_sleep_forever(), name="cancel_task")
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)

    assert task not in bg_tasks._TASKS
    assert not any("cancel_task" in record.message for record in caplog.records)
