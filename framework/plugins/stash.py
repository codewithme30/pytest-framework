"""
Module  : framework.plugins.stash
Author  : Anil Kalisetti
Purpose : Build ``Settings`` once per process (from CLI flags + env) and share via pytest's stash.

pytest does not guarantee the order of ``pytest_configure`` between plugins, so every plugin
calls ``ensure_settings(config)`` and gets the same object regardless of who ran first.
"""

from __future__ import annotations

import pytest

from framework.config.settings import Settings, load_settings
from framework.core.ci_info import detect_build_info

SETTINGS_KEY = pytest.StashKey[Settings]()


def ensure_settings(config: pytest.Config) -> Settings:
    if SETTINGS_KEY not in config.stash:
        build = detect_build_info()
        overrides = {
            "env": config.getoption("test_env"),
            "browser": config.getoption("ui_browser"),
            "execution_mode": config.getoption("execution_mode"),
            "grid_url": config.getoption("grid_url"),
            "screenshot_policy": config.getoption("screenshots"),
            "build_name": config.getoption("build_name") or f"{build.provider}-{build.build_number}",
            "headless": False if config.getoption("headed") else None,
            "locator_healing": False if config.getoption("no_healing") else None,
            "record_locators": True if config.getoption("record_locators") else None,
            "fail_on_heal": True if config.getoption("fail_on_heal") else None,
        }
        config.stash[SETTINGS_KEY] = load_settings(overrides)
    return config.stash[SETTINGS_KEY]
