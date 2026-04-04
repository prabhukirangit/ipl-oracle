"""
Windows asyncio subprocess fix for Playwright.

On Windows, Playwright needs ProactorEventLoop for async subprocess support,
but uvicorn forces SelectorEventLoop which raises NotImplementedError on
asyncio.create_subprocess_exec.

Solution: run entire Playwright sessions in a dedicated thread that uses
ProactorEventLoop. The caller awaits the result via run_in_executor.
"""

from __future__ import annotations

import asyncio
import functools
import platform
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Coroutine, TypeVar

T = TypeVar("T")

_IS_WINDOWS = platform.system() == "Windows"

# Dedicated thread pool for Playwright operations (max 3 concurrent)
_pw_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="playwright")


def _run_in_proactor(async_fn: Callable[..., Coroutine[Any, Any, Any]], args: tuple) -> Any:
    """Run an async function in a fresh ProactorEventLoop (called from thread)."""
    loop = asyncio.ProactorEventLoop()  # type: ignore[attr-defined]
    try:
        return loop.run_until_complete(async_fn(*args))
    finally:
        loop.close()


async def run_playwright(async_fn: Callable[..., Coroutine[Any, Any, T]], *args: Any) -> T:
    """
    Run a Playwright async function, working around Windows SelectorEventLoop.

    If on Windows, dispatches to a thread with ProactorEventLoop.
    Otherwise runs directly in the current loop.

    Usage:
        result = await run_playwright(_scrape_iplt20, team1, team2)

    where _scrape_iplt20 is an async function containing the full
    Playwright session (open browser, scrape, close browser).
    """
    if _IS_WINDOWS:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _pw_executor,
            functools.partial(_run_in_proactor, async_fn, args),
        )
    return await async_fn(*args)
