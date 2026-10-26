"""
Module  : tests/api/conftest.py
Author  : Anil Kalisetti
Purpose : API fixtures: shared clients, JSON schemas and a factory for isolated clients.

Target APIs (public, free, no login needed):
    JSONPlaceholder  https://jsonplaceholder.typicode.com   fake REST data (posts, users, ...)
    httpbingo        https://httpbingo.org                  HTTP behaviour (status, auth, delay)
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from framework.api.client import ApiClient
from framework.api.services import (
    AlbumsService,
    CommentsService,
    PhotosService,
    PostsService,
    TodosService,
    UsersService,
)
from framework.config.settings import Settings
from framework.core.data_loader import load_data

SCHEMA_DIR = Path(__file__).parent / "schemas"


@pytest.fixture(scope="session")
def api_client(settings: Settings) -> Iterator[ApiClient]:
    """Shared client for read-only calls (connection reuse makes the suite much faster)."""
    client = ApiClient(settings.base_api_url, settings.api_timeout, settings.api_retries)
    yield client
    client.close()


@pytest.fixture(scope="session")
def posts_api(api_client: ApiClient) -> PostsService:
    return PostsService(api_client)


@pytest.fixture(scope="session")
def comments_api(api_client: ApiClient) -> CommentsService:
    return CommentsService(api_client)


@pytest.fixture(scope="session")
def users_api(api_client: ApiClient) -> UsersService:
    return UsersService(api_client)


@pytest.fixture(scope="session")
def todos_api(api_client: ApiClient) -> TodosService:
    return TodosService(api_client)


@pytest.fixture(scope="session")
def albums_api(api_client: ApiClient) -> AlbumsService:
    return AlbumsService(api_client)


@pytest.fixture(scope="session")
def photos_api(api_client: ApiClient) -> PhotosService:
    return PhotosService(api_client)


@pytest.fixture(scope="session")
def httpbin(settings: Settings) -> Iterator[ApiClient]:
    """HTTP-semantics client. Retries are OFF: tests assert the raw 5xx a server returns."""
    client = ApiClient(settings.httpbin_url, settings.api_timeout, retries=0)
    yield client
    client.close()


@pytest.fixture
def new_client(settings: Settings) -> Iterator[Callable[..., ApiClient]]:
    """Factory for tests that change auth/headers/timeouts, so they cannot leak into others."""
    created: list[ApiClient] = []

    def factory(base_url: str | None = None, **kwargs: Any) -> ApiClient:
        kwargs.setdefault("timeout", settings.api_timeout)
        kwargs.setdefault("retries", 0)
        client = ApiClient(base_url or settings.base_api_url, **kwargs)
        created.append(client)
        return client

    yield factory
    for client in created:
        client.close()


@pytest.fixture(scope="session")
def schemas() -> dict[str, Any]:
    """All JSON schemas keyed by file name without extension: ``schemas['post']``."""
    return {path.stem: load_data(path) for path in SCHEMA_DIR.glob("*.json")}

