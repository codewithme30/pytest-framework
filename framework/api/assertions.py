"""
Module  : framework.api.assertions
Author  : Anil Kalisetti
Purpose : Reusable, descriptive API assertions (clear failure messages beat bare ``assert``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests
from jsonschema import Draft7Validator

_MAX_SCHEMA_ERRORS = 5


def array_of(item_schema: Mapping[str, Any]) -> dict[str, Any]:
    """Wrap an item schema so a whole list response is validated in one call."""
    return {"type": "array", "items": item_schema}


def assert_status(response: requests.Response, expected: int | tuple[int, ...]) -> None:
    allowed = (expected,) if isinstance(expected, int) else expected
    assert response.status_code in allowed, (
        f"Expected status {allowed}, got {response.status_code} for "
        f"{response.request.method} {response.url}. Body: {response.text[:300]}"
    )


def assert_json_schema(data: Any, schema: Mapping[str, Any]) -> None:
    """Validate ``data`` against a JSON Schema (draft 7) and list the first few violations."""
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        details = "; ".join(
            f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in errors[:_MAX_SCHEMA_ERRORS]
        )
        raise AssertionError(f"{len(errors)} schema violation(s): {details}")


def assert_response_time(response: requests.Response, max_seconds: float) -> None:
    actual = response.elapsed.total_seconds()
    assert actual <= max_seconds, f"Response took {actual:.2f}s, budget is {max_seconds}s"


def assert_header_contains(response: requests.Response, name: str, fragment: str) -> None:
    actual = response.headers.get(name)
    assert actual is not None, f"Header '{name}' missing. Present: {sorted(response.headers)}"
    assert fragment.lower() in actual.lower(), f"Header {name}='{actual}' lacks '{fragment}'"


def assert_json_subset(actual: Any, expected: Any, path: str = "$") -> None:
    """Assert every key/value in ``expected`` is present in ``actual`` (extra keys allowed).

    Useful when a response has volatile fields (ids, timestamps) you do not want to pin.
    """
    if isinstance(expected, Mapping):
        assert isinstance(actual, Mapping), f"{path}: expected object, got {type(actual).__name__}"
        for key, value in expected.items():
            assert key in actual, f"{path}.{key}: key missing"
            assert_json_subset(actual[key], value, f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected list, got {type(actual).__name__}"
        assert len(actual) == len(expected), f"{path}: length {len(actual)} != {len(expected)}"
        for index, (a, e) in enumerate(zip(actual, expected, strict=True)):
            assert_json_subset(a, e, f"{path}[{index}]")
    else:
        assert actual == expected, f"{path}: expected {expected!r}, got {actual!r}"
