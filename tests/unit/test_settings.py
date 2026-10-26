"""
Module  : tests/unit/test_settings.py
Author  : Anil Kalisetti
Purpose : Configuration precedence, validation and secret handling.
"""

from __future__ import annotations

import pytest

import framework.config.settings as settings_module
from framework.config.settings import load_settings
from framework.core.exceptions import ConfigurationError


def test_defaults_apply_when_nothing_is_configured():
    s = load_settings(environ={})
    assert (s.env, s.browser, s.execution_mode, s.headless) == ("qa", "chrome", "local", True)


def test_environment_variable_overrides_yaml_default():
    # qa.yaml says api_timeout: 15; a CI variable must win.
    assert load_settings(environ={"API_TIMEOUT": "42"}).api_timeout == 42


def test_cli_override_beats_environment_variable():
    s = load_settings({"browser": "firefox"}, environ={"BROWSER": "edge"})
    assert s.browser == "firefox"


def test_none_override_is_ignored():
    assert load_settings({"browser": None}, environ={"BROWSER": "edge"}).browser == "edge"


@pytest.mark.parametrize(
    ("variable", "expected"),
    [("SAUCE_USERNAME", "sauce-user"), ("BROWSERSTACK_USERNAME", "bs-user"), ("LT_USERNAME", "lt-user")],
)
def test_vendor_standard_credential_names_are_accepted(variable, expected):
    assert load_settings(environ={variable: expected}).grid_username == expected


@pytest.mark.parametrize("raw", ["true", "1", "YES", "on"])
def test_boolean_truthy_spellings(raw):
    assert load_settings(environ={"HEADLESS": raw}).headless is True


@pytest.mark.parametrize("raw", ["false", "0", "No", "off"])
def test_boolean_falsy_spellings(raw):
    assert load_settings(environ={"HEADLESS": raw}).headless is False


@pytest.mark.parametrize(
    ("environ", "fragment"),
    [
        ({"BROWSER": "netscape"}, "browser"),
        ({"EXECUTION_MODE": "mainframe"}, "execution_mode"),
        ({"SCREENSHOT_POLICY": "sometimes"}, "screenshot_policy"),
        ({"HEADLESS": "maybe"}, "boolean"),
        ({"API_TIMEOUT": "soon"}, "api_timeout"),
        ({"PASS_RATE_GREEN": "50", "PASS_RATE_AMBER": "90"}, "Thresholds"),
    ],
)
def test_invalid_values_fail_fast_with_helpful_message(environ, fragment):
    with pytest.raises(ConfigurationError, match=fragment):
        load_settings(environ=environ)


def test_unknown_override_is_rejected():
    with pytest.raises(ConfigurationError, match="Unknown override"):
        load_settings({"brwoser": "chrome"}, environ={})


def test_secrets_never_appear_in_repr():
    s = load_settings(environ={"GRID_ACCESS_KEY": "super-secret", "JIRA_API_TOKEN": "tok-123"})
    assert "super-secret" not in repr(s)
    assert "tok-123" not in repr(s)


def test_secret_in_yaml_is_rejected(tmp_path, monkeypatch):
    (tmp_path / "config" / "environments").mkdir(parents=True)
    (tmp_path / "config" / "environments" / "leaky.yaml").write_text("grid_access_key: abc123\n")
    monkeypatch.setattr(settings_module, "PROJECT_ROOT", tmp_path)
    with pytest.raises(ConfigurationError, match="Secret"):
        load_settings(environ={"TEST_ENV": "leaky"})


def test_unknown_yaml_key_is_rejected(tmp_path, monkeypatch):
    (tmp_path / "config" / "environments").mkdir(parents=True)
    (tmp_path / "config" / "environments" / "typo.yaml").write_text("browzer: chrome\n")
    monkeypatch.setattr(settings_module, "PROJECT_ROOT", tmp_path)
    with pytest.raises(ConfigurationError, match="Unknown key"):
        load_settings(environ={"TEST_ENV": "typo"})


def test_jira_configured_requires_all_four_fields():
    partial = load_settings(environ={"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_PROJECT_KEY": "QA"})
    full = load_settings(
        environ={
            "JIRA_BASE_URL": "https://x.atlassian.net",
            "JIRA_USER_EMAIL": "a@b.com",
            "JIRA_API_TOKEN": "t",
            "JIRA_PROJECT_KEY": "QA",
        }
    )
    assert not partial.jira_configured
    assert full.jira_configured
