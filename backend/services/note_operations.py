"""Serialize mutations of a note and finish commits before honouring cancellation."""
import asyncio
import logging
from collections.abc import Awaitable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TypeVar
from weakref import WeakValueDictionary

_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
_T = TypeVar("_T")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def note_operation(short_id: str):
    lock = _locks.setdefault(short_id, asyncio.Lock())
    async with lock:
        yield


async def finish_commit(operation: Awaitable[_T]) -> _T:
    """Keep the note lock until a commit or its rollback finishes, even on disconnect."""
    task = asyncio.ensure_future(operation)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


def cleanup_staging(paths) -> None:
    """Cleanup after the commit must not turn a committed DB change into a failure."""
    for path in paths:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            logger.warning("笔记暂存文件清理失败，将保留供后续清理")
