"""
Module  : framework.ui.screenshot
Author  : Anil Kalisetti
Purpose : Capture screenshots and page source as failure evidence.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from framework.core.logger import get_logger

log = get_logger("ui.screenshot")

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_stem(test_id: str) -> str:
    """tests/ui/test_login.py::test_x[a b] -> tests_ui_test_login.py_test_x_a_b_ (bounded length)."""
    return _UNSAFE.sub("_", test_id)[-120:]


def capture_evidence(driver: WebDriver, directory: Path, test_id: str) -> Path | None:
    """Save ``<name>.png`` and ``<name>.html``; return the PNG path or ``None`` on failure."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        stem = f"{_safe_stem(test_id)}_{datetime.now():%H%M%S%f}"
        png = directory / f"{stem}.png"
        if not driver.save_screenshot(str(png)):
            return None
        (directory / f"{stem}.html").write_text(driver.page_source, encoding="utf-8")
        return png
    except (WebDriverException, OSError) as exc:
        # Evidence capture is best-effort: a dead browser must not hide the real failure.
        log.warning("Evidence capture failed for %s: %s", test_id, exc)
        return None
