"""
Module  : framework.config.settings
Author  : Anil Kalisetti
Purpose : Layered, validated configuration shared by every test layer.

Precedence (highest wins):
    1. Explicit overrides (pytest CLI flags such as ``--browser``)
    2. Environment variables / ``.env`` file (``BROWSER=firefox``)
    3. ``config/environments/<TEST_ENV>.yaml`` (non-secret defaults)
    4. Defaults declared on ``Settings`` below

Design notes:
    * ``Settings`` is frozen, so a test cannot accidentally mutate global state.
    * Secrets are accepted ONLY from the environment; a YAML file containing one is rejected.
    * Typos in YAML keys fail fast instead of being silently ignored.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, get_type_hints

from dotenv import load_dotenv

from framework.core.exceptions import ConfigurationError
from framework.core.yaml_loader import load_yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EXECUTION_MODES = ("local", "remote", "saucelabs", "browserstack", "lambdatest")
BROWSERS = ("chrome", "firefox", "edge", "safari")
SCREENSHOT_POLICIES = ("on_failure", "always", "never")

# Fields that must never be committed to a YAML file.
_SECRET_FIELDS = frozenset({"grid_access_key", "jira_api_token"})

# Extra environment variable names accepted per field (vendor-standard names first-class).
_ENV_NAMES: dict[str, tuple[str, ...]] = {
    "env": ("TEST_ENV",),
    "grid_username": ("GRID_USERNAME", "SAUCE_USERNAME", "BROWSERSTACK_USERNAME", "LT_USERNAME"),
    "grid_access_key": (
        "GRID_ACCESS_KEY",
        "SAUCE_ACCESS_KEY",
        "BROWSERSTACK_ACCESS_KEY",
        "LT_ACCESS_KEY",
    ),
}


@dataclass(frozen=True)
class Settings:
    # --- Environment ------------------------------------------------------
    env: str = "qa"
    product_name: str = "Sample Retail Platform"
    base_ui_url: str = "https://www.saucedemo.com"
    base_api_url: str = "https://jsonplaceholder.typicode.com"
    httpbin_url: str = "https://httpbingo.org"

    # --- Browser / execution target ----------------------------------------
    browser: str = "chrome"
    headless: bool = True
    chrome_binary: str = ""  # e.g. /usr/bin/chromium inside Docker
    window_size: str = "1920,1080"
    explicit_wait: int = 10
    page_load_timeout: int = 30
    execution_mode: str = "local"
    grid_url: str = ""
    grid_username: str = ""
    grid_access_key: str = field(default="", repr=False)
    platform_name: str = "Windows 11"
    browser_version: str = "latest"
    build_name: str = ""

    # --- Self-healing locators (see docs/SELF_HEALING.md) -------------------------
    locator_healing: bool = True  # --no-healing turns it off for a run
    heal_threshold: float = 0.8  # minimum similarity (0-1) to accept a look-alike element
    heal_margin: float = 0.1  # the best look-alike must beat the runner-up by this much
    heal_after: float = 3.0  # seconds to wait for the original locator before trying to heal
    locator_baseline: str = "config/locator_fingerprints.json"
    record_locators: bool = False  # --record-locators: capture fingerprints (known-good build only)
    fail_on_heal: bool = False  # --fail-on-heal: exit non-zero when anything healed (release gates)

    # --- API ----------------------------------------------------------------
    api_timeout: int = 15
    api_retries: int = 3

    # --- Database / ETL -------------------------------------------------------
    db_url: str = "sqlite:///reports/sample_test.db"
    seed_sample_db: bool = True  # reset the sample SQLite table each session; set false for real DBs
    etl_source_db_url: str = ""  # placeholder: real source system (e.g. legacy Oracle)
    etl_target_db_url: str = ""  # placeholder: real target (e.g. Snowflake / Postgres)

    # --- Jira ----------------------------------------------------------------
    jira_enabled: bool = False
    jira_base_url: str = ""
    jira_user_email: str = ""
    jira_api_token: str = field(default="", repr=False)
    jira_project_key: str = ""
    jira_issue_type: str = "Bug"
    jira_labels: str = "automation"

    # --- Reporting -------------------------------------------------------------
    reports_dir: str = "reports"
    screenshot_policy: str = "on_failure"
    pass_rate_green: float = 95.0
    pass_rate_amber: float = 80.0

    def __post_init__(self) -> None:
        _require_in("execution_mode", self.execution_mode, EXECUTION_MODES)
        _require_in("browser", self.browser, BROWSERS)
        _require_in("screenshot_policy", self.screenshot_policy, SCREENSHOT_POLICIES)
        if not 0 < self.heal_threshold <= 1 or self.heal_margin < 0 or self.heal_after < 0:
            raise ConfigurationError("Healing needs 0 < heal_threshold <= 1, heal_margin >= 0, heal_after >= 0")
        if not 0 <= self.pass_rate_amber <= self.pass_rate_green <= 100:
            raise ConfigurationError("Thresholds must satisfy 0 <= amber <= green <= 100")

    @property
    def reports_path(self) -> Path:
        return Path(self.reports_dir)

    @property
    def locator_baseline_path(self) -> Path:
        path = Path(self.locator_baseline)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def jira_configured(self) -> bool:
        return all(
            (self.jira_base_url, self.jira_user_email, self.jira_api_token, self.jira_project_key)
        )


def _require_in(name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ConfigurationError(f"{name}='{value}' is invalid; choose one of {allowed}")


def _coerce(name: str, raw: Any, target: type) -> Any:
    """Convert strings coming from env vars / YAML to the declared field type."""
    if target is bool:
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off", ""}:
            return False
        raise ConfigurationError(f"{name}='{raw}' is not a valid boolean")
    try:
        return target(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{name}='{raw}' cannot be converted to {target.__name__}") from exc


def _read_yaml(env_name: str) -> dict[str, Any]:
    path = PROJECT_ROOT / "config" / "environments" / f"{env_name}.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = load_yaml(handle) or {}
    if not isinstance(data, dict):
        raise ConfigurationError(f"{path} must contain a mapping of key: value pairs")
    return data


def _env_lookup(name: str, environ: Mapping[str, str]) -> str | None:
    for var in _ENV_NAMES.get(name, (name.upper(),)):
        value = environ.get(var)
        if value not in (None, ""):
            return value
    return None


def load_settings(
    overrides: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Build and cache ``Settings``. ``overrides`` entries that are ``None`` are ignored."""
    global _cached
    if environ is None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        environ = os.environ
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}

    hints = get_type_hints(Settings)
    known = {f.name for f in fields(Settings)}

    env_name = overrides.get("env") or _env_lookup("env", environ) or "qa"
    values: dict[str, Any] = {}

    for key, raw in _read_yaml(str(env_name)).items():
        if key not in known:
            raise ConfigurationError(f"Unknown key '{key}' in {env_name}.yaml")
        if key in _SECRET_FIELDS:
            raise ConfigurationError(
                f"Secret '{key}' found in {env_name}.yaml; provide it via environment variable"
            )
        values[key] = _coerce(key, raw, hints[key])

    for name in known:
        raw = _env_lookup(name, environ)
        if raw is not None:
            values[name] = _coerce(name, raw, hints[name])

    for name, raw in overrides.items():
        if name not in known:
            raise ConfigurationError(f"Unknown override '{name}'")
        values[name] = _coerce(name, raw, hints[name])

    values["env"] = str(env_name)
    _cached = replace(Settings(), **values)
    return _cached


_cached: Settings | None = None


def get_settings() -> Settings:
    """Return the active settings, loading defaults on first use."""
    return _cached if _cached is not None else load_settings()
