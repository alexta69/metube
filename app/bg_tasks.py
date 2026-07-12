import asyncio
import logging

log = logging.getLogger("bg_tasks")
_TASKS: set[asyncio.Task] = set()


def create_task(coro, *, name: str | None = None) -> asyncio.Task:
    """create_task that keeps a strong reference and logs unexpected failures.

    A bare ``asyncio.create_task(...)`` is only weakly referenced by the event
    loop; if nothing else holds the returned Task, it can be garbage collected
    mid-flight. Keeping a module-level strong reference (removed once the task
    finishes) avoids that, and the done-callback surfaces otherwise-silent
    failures.
    """
    task = asyncio.get_running_loop().create_task(coro, name=name)
    _TASKS.add(task)

    def _done(t: asyncio.Task) -> None:
        _TASKS.discard(t)
        if not t.cancelled() and t.exception() is not None:
            log.error("Background task %s failed", t.get_name(), exc_info=t.exception())

    task.add_done_callback(_done)
    return task
