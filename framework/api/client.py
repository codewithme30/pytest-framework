"""
Module  : framework.api.client
Author  : Anil Kalisetti
Purpose : Thin, observable wrapper around ``requests.Session`` for API tests.

Why a wrapper instead of bare ``requests``?
    * One place for base URL, default timeout and transient-failure retries.
    * Every call is logged with method, URL, status and latency (secrets redacted).
    * Request/response pairs are attached to the Allure report automatically.
    * A ``Session`` reuses TCP connections, which is much faster for hundreds of calls.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from types import TracebackType
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from framework.core.logger import get_logger

try:  # Allure is optional so the client also works in plain scripts.
    import allure
except ImportError:  # pragma: no cover
    allure = None

log = get_logger("api.client")

_REDACTED_HEADERS = frozenset({"authorization", "cookie", "set-cookie", "x-api-key"})
_MAX_ATTACHMENT_CHARS = 5_000  # keeps reports small and memory flat for large payloads

# Only idempotent verbs are retried automatically: retrying POST could create duplicates
# (two orders, two payments). Retry POST explicitly in a test if the API supports idempotency keys.
_RETRY_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})


class ApiClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 15,
        retries: int = 3,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", **(headers or {})})

        if retries > 0:
            retry = Retry(
                total=retries,
                backoff_factor=0.5,  # waits 0.5s, 1s, 2s ... between attempts
                status_forcelist=(502, 503, 504),
                allowed_methods=_RETRY_METHODS,
                raise_on_status=False,  # hand the final 5xx back so the test can assert on it
            )
            adapter = HTTPAdapter(max_retries=retry)
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)

    # --- authentication helpers ------------------------------------------------
    def set_bearer_token(self, token: str) -> None:
        self.session.headers["Authorization"] = f"Bearer {token}"

    def set_basic_auth(self, username: str, password: str) -> None:
        self.session.auth = (username, password)

    # --- core request ---------------------------------------------------------------
    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}/{path.lstrip('/')}"
        kwargs.setdefault("timeout", self.timeout)

        started = time.perf_counter()
        response = self.session.request(method.upper(), url, **kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000

        log.info("%s %s -> %s (%.0f ms)", method.upper(), url, response.status_code, elapsed_ms)
        self._attach(method, url, kwargs, response)
        return response

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("DELETE", path, **kwargs)

    def head(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("HEAD", path, **kwargs)

    def options(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("OPTIONS", path, **kwargs)

    # --- lifecycle -------------------------------------------------------------------------
    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # --- reporting ----------------------------------------------------------------------------
    @staticmethod
    def _redact(headers: Mapping[str, Any]) -> dict[str, Any]:
        return {k: ("***" if k.lower() in _REDACTED_HEADERS else v) for k, v in headers.items()}

    def _attach(
        self, method: str, url: str, kwargs: Mapping[str, Any], response: requests.Response
    ) -> None:
        if allure is None:
            return
        try:
            request_text = (
                f"{method.upper()} {url}\n"
                f"Headers: {self._redact(response.request.headers)}\n"
                f"Params: {kwargs.get('params')}\n"
                f"Body: {str(response.request.body)[:_MAX_ATTACHMENT_CHARS]}"
            )
            response_text = (
                f"Status: {response.status_code} {response.reason}\n"
                f"Time: {response.elapsed.total_seconds():.3f}s\n"
                f"Headers: {self._redact(response.headers)}\n"
                f"Body: {response.text[:_MAX_ATTACHMENT_CHARS]}"
            )
            allure.attach(request_text, "request", allure.attachment_type.TEXT)
            allure.attach(response_text, "response", allure.attachment_type.TEXT)
        except Exception as exc:  # noqa: BLE001 - reporting must never break a test
            log.debug("Skipping Allure attachment: %s", exc)
