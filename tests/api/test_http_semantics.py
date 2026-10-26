"""
Module  : tests/api/test_http_semantics.py
Author  : Anil Kalisetti
Purpose : Protocol-level behaviour every API client must survive: status codes, auth schemes,
          redirects, cookies, compression, binary payloads, slow servers and timeouts.

Target: httpbingo.org, a service built to echo HTTP behaviour. Real-life mapping: these are
the situations a mobile app meets daily: expired tokens (401), maintenance (503), slow
networks (timeouts), CDN redirects (302) and gzip responses.

Note: echo services differ in body shape (e.g. header values as lists). Helpers below accept
both shapes, so the suite also works against the older httpbin.org by changing HTTPBIN_URL.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import requests

from framework.api.assertions import assert_json_subset, assert_response_time, assert_status

pytestmark = pytest.mark.network


def first(value: Any) -> Any:
    """Echo services return either 'x' or ['x']; normalise to the scalar."""
    return value[0] if isinstance(value, list) else value


# --- status codes -----------------------------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.parametrize(
    "code",
    [200, 201, 202, 204, 400, 401, 403, 404, 405, 409, 418, 422, 429, 500, 502, 503],
)
def test_server_status_codes_are_reported_faithfully(httpbin, code):
    assert httpbin.get(f"/status/{code}").status_code == code


@pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete"])
def test_every_method_reaches_the_server(httpbin, method):
    response = getattr(httpbin, method)("/anything")
    assert_status(response, 200)
    assert response.json()["method"] == method.upper()


def test_json_body_is_received_intact(httpbin):
    payload = {"order": {"sku": "A-100", "qty": 2}, "tags": ["gift", "rush"], "note": "café ☕"}
    assert_json_subset(httpbin.post("/anything", json=payload).json()["json"], payload)


def test_query_parameters_are_encoded_correctly(httpbin):
    args = httpbin.get("/get", params={"q": "tea & coffee", "page": 2}).json()["args"]
    assert first(args["q"]) == "tea & coffee"
    assert first(args["page"]) == "2"


def test_custom_headers_reach_the_server(httpbin):
    headers = httpbin.get("/headers", headers={"X-Request-Id": "req-42"}).json()["headers"]
    assert first(headers["X-Request-Id"]) == "req-42"


def test_multipart_file_upload(httpbin):
    response = httpbin.post("/post", files={"report": ("q3.csv", b"id,total\n1,9.99\n", "text/csv")})
    assert_status(response, 200)
    assert "report" in response.json()["files"]


def test_form_encoded_body(httpbin):
    form = httpbin.post("/post", data={"user": "priya", "role": "admin"}).json()["form"]
    assert first(form["user"]) == "priya"


# --- authentication ----------------------------------------------------------------------------------------------------
def test_basic_auth_accepts_valid_credentials(new_client, settings):
    client = new_client(settings.httpbin_url)
    client.set_basic_auth("priya", "s3cret")
    assert_status(client.get("/basic-auth/priya/s3cret"), 200)


@pytest.mark.parametrize(
    ("user", "password"),
    [("priya", "wrong"), ("wrong", "s3cret"), ("", ""), ("PRIYA", "s3cret")],
    ids=["bad-password", "bad-user", "empty", "case-sensitive"],
)
def test_basic_auth_rejects_invalid_credentials(new_client, settings, user, password):
    client = new_client(settings.httpbin_url)
    client.set_basic_auth(user, password)
    assert_status(client.get("/basic-auth/priya/s3cret"), 401)


def test_bearer_token_is_required_and_accepted(new_client, settings):
    client = new_client(settings.httpbin_url)
    assert_status(client.get("/bearer"), 401)  # no token
    client.set_bearer_token("token-123")
    assert_status(client.get("/bearer"), 200)


# --- redirects, cookies, encoding ------------------------------------------------------------------------------------------
def test_redirects_are_followed_by_default(httpbin):
    response = httpbin.get("/redirect/2")
    assert_status(response, 200)
    assert len(response.history) == 2


def test_redirect_can_be_inspected_when_following_is_disabled(httpbin):
    response = httpbin.get("/redirect/1", allow_redirects=False)
    assert response.status_code in (301, 302)
    assert "Location" in response.headers


def test_cookies_persist_within_a_session(new_client, settings):
    client = new_client(settings.httpbin_url)
    client.get("/cookies/set", params={"theme": "dark"})
    assert client.session.cookies.get("theme") == "dark"


def test_gzip_response_is_decompressed_transparently(httpbin):
    response = httpbin.get("/gzip")
    assert_status(response, 200)
    assert response.json()["gzipped"] is True


@pytest.mark.parametrize("size", [0, 1, 1024, 65536])
def test_binary_payload_sizes(httpbin, size):
    assert len(httpbin.get(f"/bytes/{size}").content) == size


def test_uuid_endpoint_returns_valid_uuid(httpbin):
    assert uuid.UUID(httpbin.get("/uuid").json()["uuid"]).version == 4


# --- latency & timeouts -----------------------------------------------------------------------------------------------------------
def test_delayed_response_arrives_after_the_delay(httpbin):
    response = httpbin.get("/delay/1")
    assert_status(response, 200)
    assert response.elapsed.total_seconds() >= 1


def test_client_timeout_raises_instead_of_hanging(new_client, settings):
    client = new_client(settings.httpbin_url, timeout=1)
    with pytest.raises(requests.exceptions.Timeout):
        client.get("/delay/5")


@pytest.mark.slow
def test_fast_endpoint_meets_latency_budget(httpbin):
    assert_response_time(httpbin.get("/get"), 3)
