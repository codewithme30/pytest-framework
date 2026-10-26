"""
Module  : framework.integrations.jira_client
Author  : Anil Kalisetti
Purpose : Create and de-duplicate Jira Cloud defects from failed tests.

Authentication : Jira Cloud API token (https://id.atlassian.com/manage-profile/security/api-tokens)
                 sent as HTTP Basic ``email:token``. Never log or commit the token.
API version    : REST v3 (descriptions use Atlassian Document Format, ADF).

De-duplication (important in real life):
    A flaky test that fails 30 nights in a row must not create 30 bugs. Each failure gets a
    stable fingerprint label (``auto-<sha1(test id)>``). Before creating a bug we search for an
    open issue carrying that label; if one exists we add a comment instead.

Jira Server / Data Center note:
    Those editions use REST v2 and plain-text descriptions. See TODO at ``create_defect``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import requests

from framework.core.exceptions import IntegrationError
from framework.core.logger import get_logger

log = get_logger("integrations.jira")

_SUMMARY_LIMIT = 255  # Jira rejects longer summaries


def fingerprint(test_id: str) -> str:
    """Stable label for a test, e.g. ``auto-3f2b9c4d1a7e``."""
    return "auto-" + hashlib.sha1(test_id.encode("utf-8")).hexdigest()[:12]  # noqa: S324 - not security


def to_adf(lines: Sequence[str]) -> dict[str, Any]:
    """Convert plain lines to a minimal ADF document (one paragraph per non-empty line)."""
    content = [
        {"type": "paragraph", "content": [{"type": "text", "text": line}]}
        for line in lines
        if line.strip()
    ]
    return {"type": "doc", "version": 1, "content": content or [{"type": "paragraph", "content": []}]}


class JiraClient:
    def __init__(
        self,
        base_url: str,
        user_email: str,
        api_token: str,
        project_key: str,
        issue_type: str = "Bug",
        timeout: float = 20,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.project_key = project_key
        self.issue_type = issue_type
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.auth = (user_email, api_token)
        self.session.headers.update({"Accept": "application/json"})

    # --- low level -------------------------------------------------------------------------
    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.session.request(
            method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs
        )
        if not response.ok:
            # Body is included for diagnosis; Jira never echoes credentials back.
            raise IntegrationError(
                f"Jira {method} {path} failed: {response.status_code} {response.text[:300]}"
            )
        return response.json() if response.content else {}

    # --- operations ------------------------------------------------------------------------------
    def find_open_defect(self, label: str) -> str | None:
        """Return the key of an unresolved issue carrying ``label``, or ``None``."""
        jql = f'project = "{self.project_key}" AND labels = "{label}" AND statusCategory != Done'
        data = self._call(
            "GET", "/rest/api/3/search/jql", params={"jql": jql, "fields": "key", "maxResults": 1}
        )
        issues = data.get("issues", [])
        return issues[0]["key"] if issues else None

    def create_defect(
        self,
        summary: str,
        description_lines: Sequence[str],
        labels: Sequence[str] = (),
        priority: str | None = None,
        extra_fields: Mapping[str, Any] | None = None,
    ) -> str:
        """Create a bug and return its key (e.g. ``QA-142``).

        ``extra_fields`` carries project specific fields, e.g.
        ``{"components": [{"name": "Checkout"}], "customfield_10020": 42}``.
        TODO(future): Jira Server/Data Center: switch to ``/rest/api/2/issue`` and send the
        description as a plain string instead of ADF.
        """
        fields: dict[str, Any] = {
            "project": {"key": self.project_key},
            "summary": summary[:_SUMMARY_LIMIT],
            "issuetype": {"name": self.issue_type},
            "description": to_adf(description_lines),
            "labels": list(labels),
        }
        if priority:
            fields["priority"] = {"name": priority}
        fields.update(extra_fields or {})
        key = self._call("POST", "/rest/api/3/issue", json={"fields": fields})["key"]
        log.info("Created Jira defect %s", key)
        return str(key)

    def add_comment(self, issue_key: str, lines: Sequence[str]) -> None:
        self._call("POST", f"/rest/api/3/issue/{issue_key}/comment", json={"body": to_adf(lines)})

    def attach_file(self, issue_key: str, path: Path) -> None:
        """Upload evidence (screenshot, log). Jira requires the no-check XSRF header."""
        with path.open("rb") as handle:
            self._call(
                "POST",
                f"/rest/api/3/issue/{issue_key}/attachments",
                headers={"X-Atlassian-Token": "no-check"},
                files={"file": (path.name, handle)},
            )
