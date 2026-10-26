"""
Module  : tests/unit/test_core_helpers.py
Author  : Anil Kalisetti
Purpose : Polling, data loading and secret masking helpers.
"""

from __future__ import annotations

import pytest

from framework.core.data_loader import load_data
from framework.core.logger import mask_secret
from framework.core.waits import poll_until


def test_poll_until_returns_value_as_soon_as_condition_is_met():
    attempts = iter([0, 0, 42])
    assert poll_until(lambda: next(attempts), timeout=2, interval=0.01) == 42


def test_poll_until_survives_transient_errors():
    calls = {"n": 0}

    def flaky_check():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("not ready")  # e.g. target table not created yet
        return True

    assert poll_until(flaky_check, timeout=2, interval=0.01) is True


def test_poll_until_times_out_and_chains_last_error():
    with pytest.raises(TimeoutError, match="row count") as excinfo:
        poll_until(lambda: (_ for _ in ()).throw(ValueError("still loading")), timeout=0.1, interval=0.02, message="row count")
    assert isinstance(excinfo.value.__cause__, ValueError)


def test_load_data_reads_json_and_yaml(tmp_path):
    (tmp_path / "a.json").write_text('{"user": "standard_user"}')
    (tmp_path / "b.yaml").write_text("regions:\n  - ON\n  - AB\n")
    assert load_data(tmp_path / "a.json") == {"user": "standard_user"}
    assert load_data(tmp_path / "b.yaml") == {"regions": ["ON", "AB"]}


@pytest.mark.parametrize("code", ["ON", "NO", "on", "yes", "No"])
def test_yaml_codes_that_look_like_booleans_stay_strings(tmp_path, code):
    # Real-life trap: Ontario ("ON") and Norway ("NO") become True/False under YAML 1.1.
    (tmp_path / "codes.yaml").write_text(f"province: {code}\n")
    assert load_data(tmp_path / "codes.yaml") == {"province": code}


def test_yaml_true_and_false_are_still_booleans(tmp_path):
    (tmp_path / "flags.yaml").write_text("a: true\nb: False\nc: FALSE\n")
    assert load_data(tmp_path / "flags.yaml") == {"a": True, "b": False, "c": False}


def test_load_data_rejects_unknown_format(tmp_path):
    (tmp_path / "c.xml").write_text("<a/>")
    with pytest.raises(ValueError, match="Unsupported"):
        load_data(tmp_path / "c.xml")


@pytest.mark.parametrize(("secret", "masked"), [("abcdef", "ab****"), ("", ""), ("x", "x****")])
def test_mask_secret(secret, masked):
    assert mask_secret(secret) == masked
