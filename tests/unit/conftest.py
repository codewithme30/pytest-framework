"""
Module  : tests/unit/conftest.py
Author  : Anil Kalisetti
Purpose : Offline fixtures for the framework's own tests: a tiny local HTTP stub server and
          protection of the global settings cache.

The stub uses only the standard library, so unit tests need no mocking package and exercise
the REAL ``requests`` stack (retries, headers, multipart) instead of a simulation of it.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import types
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

import framework.config.settings as settings_module


@dataclass
class RecordedCall:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: bytes


@dataclass
class StubServer:
    url: str = ""
    calls: list[RecordedCall] = field(default_factory=list)
    _routes: dict[tuple[str, str], list[tuple[int, Any, float]]] = field(default_factory=dict)

    def add(self, method: str, path: str, status: int = 200, body: Any = None, delay: float = 0) -> None:
        """Register a response. Call twice for the same route to script a sequence
        (e.g. 503 then 200); the last response repeats once the sequence is exhausted."""
        self._routes.setdefault((method.upper(), path), []).append((status, body, delay))

    def replace(self, method: str, path: str, status: int = 200, body: Any = None, delay: float = 0) -> None:
        """Discard any scripted responses for the route and register a single new one."""
        self._routes[(method.upper(), path)] = [(status, body, delay)]

    def next_response(self, method: str, path: str) -> tuple[int, Any, float]:
        queue = self._routes.get((method, path))
        if not queue:
            return 404, {"error": "no route"}, 0
        return queue.pop(0) if len(queue) > 1 else queue[0]


def _make_handler(stub: StubServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # keep test output quiet
            pass

        def _handle(self) -> None:
            parts = urlsplit(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            stub.calls.append(
                RecordedCall(
                    self.command, parts.path, parse_qs(parts.query),
                    {k.lower(): v for k, v in self.headers.items()}, body,
                )
            )  # fmt: skip
            status, payload, delay = stub.next_response(self.command, parts.path)
            if delay:
                time.sleep(delay)
            data = b"" if payload is None else json.dumps(payload).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):  # client timed out: expected in tests
                pass

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _handle  # noqa: N815

    return Handler


@pytest.fixture
def stub_server() -> Iterator[StubServer]:
    stub = StubServer()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(stub))
    stub.url = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield stub
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def _restore_settings_cache() -> Iterator[None]:
    """``load_settings`` caches globally; undo that so tests cannot affect each other."""
    saved = settings_module._cached
    yield
    settings_module._cached = saved


# --- fake Selenium ------------------------------------------------------------------------------------
class FakeOptions:
    """Records what the framework asks of a Selenium options object."""

    def __init__(self) -> None:
        self.arguments: list[str] = []
        self.capabilities: dict[str, Any] = {}
        self.binary_location: str | None = None

    def add_argument(self, argument: str) -> None:
        self.arguments.append(argument)

    def set_capability(self, key: str, value: Any) -> None:
        self.capabilities[key] = value


class FakeDriver:
    """Stands in for a WebDriver: remembers how it was created and what was done to it."""

    def __init__(self, kind: str, **kwargs: Any) -> None:
        self.kind, self.kwargs = kind, kwargs
        self.window_size: tuple[int, int] | None = None
        self.page_load_timeout: float | None = None
        self.scripts: list[str] = []

    def set_page_load_timeout(self, seconds: float) -> None:
        self.page_load_timeout = seconds

    def set_window_size(self, width: int, height: int) -> None:
        self.window_size = (width, height)

    def execute_script(self, script: str) -> None:
        self.scripts.append(script)


@dataclass
class FakeSelenium:
    drivers: list[FakeDriver] = field(default_factory=list)


@pytest.fixture
def fake_selenium(monkeypatch: pytest.MonkeyPatch) -> FakeSelenium:
    """Replace the ``selenium`` package so browser/target/page code runs with no browser installed.

    Real-life use: verify "Firefox headless gets -headless" in milliseconds on any laptop or CI
    runner, instead of launching Firefox just to read back its command line.
    """
    fake = FakeSelenium()

    def launcher(kind: str):
        def start(**kwargs: Any) -> FakeDriver:
            driver = FakeDriver(kind, **kwargs)
            fake.drivers.append(driver)
            return driver

        return start

    def module(name: str, **attrs: Any) -> types.ModuleType:
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    selenium = module("selenium")
    webdriver = module(
        "selenium.webdriver",
        Chrome=launcher("chrome"),
        Firefox=launcher("firefox"),
        Edge=launcher("edge"),
        Safari=launcher("safari"),
        Remote=launcher("remote"),
    )
    selenium.webdriver = webdriver  # type: ignore[attr-defined]
    for browser in ("chrome", "firefox", "edge", "safari"):
        module(f"selenium.webdriver.{browser}")
        module(f"selenium.webdriver.{browser}.options", Options=type(f"{browser.title()}Options", (FakeOptions,), {}))

    # Names imported at the top of framework.ui.base_page
    class TimeoutException(Exception):
        pass

    module("selenium.common")
    module("selenium.common.exceptions", TimeoutException=TimeoutException)
    module("selenium.webdriver.common")
    module("selenium.webdriver.common.action_chains", ActionChains=object)
    module("selenium.webdriver.common.by", By=types.SimpleNamespace(CSS_SELECTOR="css selector"))
    module("selenium.webdriver.remote")
    module("selenium.webdriver.remote.webdriver", WebDriver=object)
    module("selenium.webdriver.remote.webelement", WebElement=object)
    support = module("selenium.webdriver.support")
    support.expected_conditions = module("selenium.webdriver.support.expected_conditions")  # type: ignore[attr-defined]
    module("selenium.webdriver.support.ui", Select=object, WebDriverWait=lambda driver, timeout: None)
    return fake
