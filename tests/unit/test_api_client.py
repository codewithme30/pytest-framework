"""
Module  : tests/unit/test_api_client.py
Author  : Anil Kalisetti
Purpose : Behaviour of the HTTP client: URL building, auth, retries, timeouts, redaction.
"""

from __future__ import annotations

import json

import pytest
import requests

from framework.api import ApiClient
from framework.api.assertions import (
    assert_header_contains,
    assert_json_schema,
    assert_json_subset,
    assert_response_time,
    assert_status,
)


def test_base_url_and_path_are_joined_with_single_slash(stub_server):
    stub_server.add("GET", "/posts/1", body={"id": 1})
    with ApiClient(stub_server.url + "/", retries=0) as client:
        assert client.get("posts/1").json() == {"id": 1}
        assert client.get("/posts/1").json() == {"id": 1}


def test_absolute_url_bypasses_base_url(stub_server):
    stub_server.add("GET", "/ping", body={"ok": True})
    with ApiClient("http://unused.invalid", retries=0) as client:
        assert client.get(stub_server.url + "/ping").json() == {"ok": True}


def test_default_accept_header_and_custom_headers(stub_server):
    stub_server.add("GET", "/h", body={})
    with ApiClient(stub_server.url, retries=0, headers={"X-Request-Id": "abc"}) as client:
        client.get("/h")
    sent = stub_server.calls[0].headers
    assert sent["accept"] == "application/json"
    assert sent["x-request-id"] == "abc"


def test_bearer_token_is_sent(stub_server):
    stub_server.add("GET", "/me", body={})
    with ApiClient(stub_server.url, retries=0) as client:
        client.set_bearer_token("tok-1")
        client.get("/me")
    assert stub_server.calls[0].headers["authorization"] == "Bearer tok-1"


def test_basic_auth_is_sent(stub_server):
    stub_server.add("GET", "/me", body={})
    with ApiClient(stub_server.url, retries=0) as client:
        client.set_basic_auth("user", "passwd")
        client.get("/me")
    assert stub_server.calls[0].headers["authorization"].startswith("Basic ")


def test_idempotent_get_is_retried_on_503_until_success(stub_server):
    stub_server.add("GET", "/flaky", status=503)
    stub_server.add("GET", "/flaky", status=503)
    stub_server.add("GET", "/flaky", status=200, body={"ok": True})
    with ApiClient(stub_server.url, retries=3) as client:
        response = client.get("/flaky")
    assert response.status_code == 200
    assert len(stub_server.calls) == 3


def test_retries_disabled_returns_first_503(stub_server):
    stub_server.add("GET", "/down", status=503)
    with ApiClient(stub_server.url, retries=0) as client:
        assert client.get("/down").status_code == 503
    assert len(stub_server.calls) == 1


def test_post_is_never_retried_automatically(stub_server):
    # Retrying a POST could create two orders / two payments.
    stub_server.add("POST", "/orders", status=503)
    stub_server.add("POST", "/orders", status=201, body={"id": 1})
    with ApiClient(stub_server.url, retries=3) as client:
        assert client.post("/orders", json={"sku": "A1"}).status_code == 503
    assert len(stub_server.calls) == 1


def test_json_body_round_trip(stub_server):
    stub_server.add("POST", "/posts", status=201, body={"id": 101})
    with ApiClient(stub_server.url, retries=0) as client:
        response = client.post("/posts", json={"title": "Hello"})
    assert response.status_code == 201
    assert json.loads(stub_server.calls[0].body) == {"title": "Hello"}


@pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete", "head"])
def test_every_http_verb_is_supported(stub_server, method):
    stub_server.add(method.upper(), "/x", body={})
    with ApiClient(stub_server.url, retries=0) as client:
        assert getattr(client, method)("/x").status_code == 200


def test_timeout_raises_instead_of_hanging(stub_server):
    stub_server.add("GET", "/slow", body={}, delay=1.0)
    with ApiClient(stub_server.url, timeout=0.2, retries=0) as client, pytest.raises(
        requests.exceptions.ReadTimeout
    ):
        client.get("/slow")


def test_sensitive_headers_are_redacted():
    redacted = ApiClient._redact({"Authorization": "Bearer abc", "Cookie": "s=1", "Accept": "json"})
    assert redacted == {"Authorization": "***", "Cookie": "***", "Accept": "json"}


# --- assertion helpers -------------------------------------------------------------------------
def test_assert_status_failure_message_shows_method_url_and_body(stub_server):
    stub_server.add("GET", "/nope", status=404, body={"error": "missing"})
    with ApiClient(stub_server.url, retries=0) as client:
        response = client.get("/nope")
    with pytest.raises(AssertionError, match=r"GET .*/nope.*missing"):
        assert_status(response, 200)
    assert_status(response, (404, 410))  # tuple of acceptable codes


def test_schema_violation_reports_field_path():
    schema = {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id", "title"]}
    with pytest.raises(AssertionError, match="2 schema violation"):
        assert_json_schema({"id": "one"}, schema)


def test_json_subset_allows_extra_keys_but_not_wrong_values():
    actual = {"id": 7, "name": "Priya", "meta": {"a": 1, "b": 2}}
    assert_json_subset(actual, {"name": "Priya", "meta": {"a": 1}})
    with pytest.raises(AssertionError, match=r"\$\.meta\.a"):
        assert_json_subset(actual, {"meta": {"a": 9}})
    with pytest.raises(AssertionError, match="key missing"):
        assert_json_subset(actual, {"email": "x"})


def test_header_and_timing_assertions(stub_server):
    stub_server.add("GET", "/ok", body={})
    with ApiClient(stub_server.url, retries=0) as client:
        response = client.get("/ok")
    assert_header_contains(response, "Content-Type", "JSON")
    assert_response_time(response, 5)
    with pytest.raises(AssertionError, match="missing"):
        assert_header_contains(response, "X-Not-There", "x")
    with pytest.raises(AssertionError, match="budget"):
        assert_response_time(response, 0.0)
