"""Helper to run a coroutine from a sync LangGraph node, regardless of whether
the caller already has a running event loop (FastAPI / TestClient / Jupyter).

Tries `asyncio.run` first. If a loop is already running, falls back to running
the coroutine in a dedicated worker thread with its own loop.
"""
from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # A loop is already running in this thread — run the coroutine in a
    # fresh thread with its own loop so we don't deadlock.
    result: dict[str, Any] = {}

    def _runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result["value"] = loop.run_until_complete(coro)
        except BaseException as e:  # noqa: BLE001
            result["error"] = e
        finally:
            loop.close()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if "error" in result:
        raise result["error"]
    return result["value"]
