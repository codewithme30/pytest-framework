"""
Module  : framework.core.logger
Author  : Anil Kalisetti
Purpose : Consistent logger naming plus a helper to keep secrets out of logs.

Handlers/levels are owned by pytest (see ``log_file*`` in pyproject.toml), so library
code only asks for a named logger and never configures handlers itself.
"""

from __future__ import annotations

import logging

_ROOT = "fw"


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the ``fw`` namespace, e.g. ``fw.api.client``."""
    logger = logging.getLogger(f"{_ROOT}.{name}")
    if not logging.getLogger(_ROOT).handlers:
        # Prevents "No handler found" noise when the library is used outside pytest.
        logging.getLogger(_ROOT).addHandler(logging.NullHandler())
    return logger


def mask_secret(value: str, visible: int = 2) -> str:
    """Mask a secret for logs: ``abcdef`` -> ``ab****``. Empty values stay empty."""
    if not value:
        return ""
    return value[:visible] + "*" * max(len(value) - visible, 4)
