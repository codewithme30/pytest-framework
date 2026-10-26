"""
Module  : framework.core.waits
Author  : Anil Kalisetti
Purpose : Polling helper for asynchronous conditions that are not browser elements.

Real-life use: after a nightly ETL job is triggered, poll the target table until the
expected row count appears instead of using a fixed ``time.sleep``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def poll_until(
    condition: Callable[[], T],
    timeout: float = 30.0,
    interval: float = 0.5,
    message: str = "condition",
) -> T:
    """Call ``condition`` until it returns a truthy value or ``timeout`` seconds pass.

    Returns the truthy value so callers can use it directly. Raises ``TimeoutError``
    with the last exception (if any) attached for easier debugging.
    """
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = condition()
            if result:
                return result
        except Exception as exc:  # noqa: BLE001 - polling must survive transient failures
            last_error = exc
        time.sleep(interval)
    raise TimeoutError(f"Timed out after {timeout}s waiting for {message}") from last_error
