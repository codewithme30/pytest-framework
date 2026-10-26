"""
Module  : tests/unit/test_parallel_and_tags.py
Author  : Anil Kalisetti
Purpose : Parallel-run helpers (per-worker files) and tag selection helpers/plugin.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from framework.core.parallel import (
    MAIN_PROCESS,
    current_db_url,
    worker_db_url,
    worker_id,
    worker_log_path,
)
from framework.core.tags import STANDARD_TAGS, combine_expressions, count_tags, unknown_tags
from framework.plugins import tags_plugin


# --- parallel ----------------------------------------------------------------------------------------
def test_worker_id_is_main_without_xdist():
    assert worker_id({}) == MAIN_PROCESS
    assert worker_id({"PYTEST_XDIST_WORKER": "gw3"}) == "gw3"


@pytest.mark.parametrize(
    ("url", "worker", "expected"),
    [
        ("sqlite:///reports/sample_test.db", "gw1", "sqlite:///reports/sample_test_gw1.db"),
        ("sqlite:////var/data/qa.sqlite", "gw0", "sqlite:////var/data/qa_gw0.sqlite"),
        ("sqlite:///reports/sample_test.db", MAIN_PROCESS, "sqlite:///reports/sample_test.db"),
        ("sqlite://", "gw1", "sqlite://"),  # in-memory: already private to the process
        ("sqlite:///:memory:", "gw1", "sqlite:///:memory:"),
        ("postgresql://qa@db/qa", "gw1", "postgresql://qa@db/qa"),  # shared server is left alone
    ],
)
def test_worker_db_url(url, worker, expected):
    assert worker_db_url(url, worker) == expected


def test_two_workers_never_share_a_database_file():
    urls = {worker_db_url("sqlite:///reports/t.db", f"gw{i}") for i in range(8)}
    assert len(urls) == 8


def test_current_db_url_follows_the_environment(monkeypatch):
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw2")
    assert current_db_url("sqlite:///reports/t.db") == "sqlite:///reports/t_gw2.db"
    monkeypatch.delenv("PYTEST_XDIST_WORKER")
    assert current_db_url("sqlite:///reports/t.db") == "sqlite:///reports/t.db"


def test_each_worker_gets_its_own_log_file():
    assert worker_log_path(Path("reports"), "gw1") == Path("reports/logs/pytest-gw1.log")
    assert worker_log_path(Path("reports"), "gw1") != worker_log_path(Path("reports"), "gw2")


# --- tags --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("markexpr", "tags", "expected"),
    [
        ("", "smoke", "smoke"),
        ("not slow", "", "not slow"),
        ("", "", ""),
        ("not slow", "smoke or uat", "(not slow) and (smoke or uat)"),  # parentheses keep precedence right
    ],
)
def test_combine_expressions(markexpr, tags, expected):
    assert combine_expressions(markexpr, tags) == expected


def test_unknown_tags_finds_typos_but_ignores_operators():
    registered = ["smoke", "uat", "slow"]
    assert unknown_tags("smoke or (uat and not slow)", registered) == []
    assert unknown_tags("smok or uat and not slw", registered) == ["slw", "smok"]


def test_count_tags_counts_each_test_once_per_tag():
    tests = [{"smoke", "critical"}, {"smoke", "regression"}, {"regression"}, set()]
    assert count_tags(tests, STANDARD_TAGS) == {
        "smoke": 2, "sanity": 0, "regression": 2, "uat": 0, "e2e": 0, "critical": 1,
    }  # fmt: skip


def _fake_config(tags, markexpr=""):
    markers = ["smoke: fast checks", "uat: sign-off", "slow: long tests", "known_defect(jira_key): tracked bug"]
    return types.SimpleNamespace(
        getoption=lambda name: {"tags": tags}[name],
        getini=lambda name: markers,
        option=types.SimpleNamespace(markexpr=markexpr),
    )


def test_tags_option_sets_the_marker_expression():
    config = _fake_config("smoke or uat", markexpr="not slow")
    tags_plugin.pytest_configure(config)
    assert config.option.markexpr == "(not slow) and (smoke or uat)"


def test_no_tags_leaves_marker_expression_alone():
    config = _fake_config(None, markexpr="not slow")
    tags_plugin.pytest_configure(config)
    assert config.option.markexpr == "not slow"


def test_misspelled_tag_is_an_error_not_a_silently_empty_run():
    with pytest.raises(pytest.UsageError, match="smok"):
        tags_plugin.pytest_configure(_fake_config("smok"))
