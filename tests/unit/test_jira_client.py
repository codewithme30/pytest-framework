"""
Module  : tests/unit/test_jira_client.py
Author  : Anil Kalisetti
Purpose : Jira defect creation, de-duplication labels, attachments and error handling.
"""

from __future__ import annotations

import json

import pytest

from framework.core.exceptions import IntegrationError
from framework.integrations.jira_client import JiraClient, fingerprint, to_adf


@pytest.fixture
def jira(stub_server):
    return JiraClient(stub_server.url, "qa@acme.com", "api-token", "QA")


def test_fingerprint_is_stable_and_unique_per_test():
    a = fingerprint("tests/ui/test_cart.py::test_badge")
    assert a == fingerprint("tests/ui/test_cart.py::test_badge")
    assert a != fingerprint("tests/ui/test_cart.py::test_remove")
    assert a.startswith("auto-")
    assert len(a) == len("auto-") + 12


def test_adf_skips_blank_lines_and_never_returns_empty_document():
    doc = to_adf(["first", "", "  ", "second"])
    assert [p["content"][0]["text"] for p in doc["content"]] == ["first", "second"]
    assert to_adf([])["content"]  # Jira rejects documents without any block


def test_create_defect_sends_expected_payload_and_returns_key(jira, stub_server):
    stub_server.add("POST", "/rest/api/3/issue", status=201, body={"id": "1", "key": "QA-142"})
    key = jira.create_defect(
        "Checkout total wrong", ["Expected 32.39", "Got 32.40"], labels=["automation", "auto-abc"], priority="High"
    )
    assert key == "QA-142"
    call = stub_server.calls[0]
    fields = json.loads(call.body)["fields"]
    assert fields["project"] == {"key": "QA"}
    assert fields["issuetype"] == {"name": "Bug"}
    assert fields["labels"] == ["automation", "auto-abc"]
    assert fields["priority"] == {"name": "High"}
    assert call.headers["authorization"].startswith("Basic ")


def test_summary_is_truncated_to_jira_limit(jira, stub_server):
    stub_server.add("POST", "/rest/api/3/issue", status=201, body={"key": "QA-1"})
    jira.create_defect("x" * 400, ["d"])
    assert len(json.loads(stub_server.calls[0].body)["fields"]["summary"]) == 255


def test_extra_fields_are_merged_for_project_specific_configuration(jira, stub_server):
    stub_server.add("POST", "/rest/api/3/issue", status=201, body={"key": "QA-2"})
    jira.create_defect("s", ["d"], extra_fields={"components": [{"name": "Checkout"}]})
    assert json.loads(stub_server.calls[0].body)["fields"]["components"] == [{"name": "Checkout"}]


def test_find_open_defect_returns_key_or_none(jira, stub_server):
    stub_server.add("GET", "/rest/api/3/search/jql", body={"issues": [{"key": "QA-9"}]})
    assert jira.find_open_defect("auto-abc") == "QA-9"
    jql = stub_server.calls[0].query["jql"][0]
    assert 'labels = "auto-abc"' in jql
    assert "statusCategory != Done" in jql  # closed bugs must not suppress a regression report

    stub_server.replace("GET", "/rest/api/3/search/jql", body={"issues": []})
    assert jira.find_open_defect("auto-zzz") is None


def test_comment_is_posted_to_existing_issue(jira, stub_server):
    stub_server.add("POST", "/rest/api/3/issue/QA-9/comment", status=201, body={"id": "5"})
    jira.add_comment("QA-9", ["Failed again in build 483"])
    body = json.loads(stub_server.calls[0].body)["body"]
    assert body["content"][0]["content"][0]["text"] == "Failed again in build 483"


def test_attachment_is_uploaded_as_multipart_with_xsrf_header(jira, stub_server, tmp_path):
    shot = tmp_path / "failure.png"
    shot.write_bytes(b"\x89PNG fake image bytes")
    stub_server.add("POST", "/rest/api/3/issue/QA-9/attachments", body=[{"id": "1"}])
    jira.attach_file("QA-9", shot)
    call = stub_server.calls[0]
    assert call.headers["x-atlassian-token"] == "no-check"
    assert call.headers["content-type"].startswith("multipart/form-data")
    assert b"failure.png" in call.body


def test_http_error_becomes_integration_error_without_leaking_token(jira, stub_server):
    stub_server.add("POST", "/rest/api/3/issue", status=400, body={"errors": {"project": "invalid"}})
    with pytest.raises(IntegrationError, match="400") as excinfo:
        jira.create_defect("s", ["d"])
    assert "api-token" not in str(excinfo.value)
