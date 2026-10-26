"""
Module  : framework.api.services
Author  : Anil Kalisetti
Purpose : One class per REST resource, so tests read like the business ("posts.create(...)")
          instead of repeating URLs and HTTP verbs.

OOP concepts used here
    Abstraction    ``ResourceService`` captures the generic CRUD contract once.
    Inheritance    ``PostsService`` and friends inherit it and add only what is special.
    Encapsulation  URL building and the HTTP client are private; tests never format paths.
    Composition    a service HAS an ``ApiClient`` (it does not extend it), so one client,
                   with its retries, logging and reporting, is shared by every service.

Real-life example: a banking test says ``accounts.get(42)`` and ``accounts.transactions_of(42)``.
When the API moves from /v1 to /v2 only the service class changes, not 300 tests.

Every method returns the raw ``requests.Response`` so each test still decides what to assert.
"""

from __future__ import annotations

from typing import Any, ClassVar

import requests

from framework.api.client import ApiClient

ResourceId = int | str


class ResourceService:
    """Generic CRUD over ``/<resource>``. Subclasses only set ``resource``."""

    resource: ClassVar[str]

    def __init__(self, client: ApiClient) -> None:
        if not getattr(type(self), "resource", ""):
            raise TypeError(f"{type(self).__name__} must define the class attribute 'resource'")
        self._client = client

    # --- URL building (private: one place to change when the API changes) -------------
    def _path(self, resource_id: ResourceId | None = None, *sub_resources: str) -> str:
        parts = [self.resource] if resource_id is None else [self.resource, str(resource_id)]
        return "/" + "/".join([*parts, *sub_resources])

    # --- CRUD ----------------------------------------------------------------------------------
    def list(self, **query: Any) -> requests.Response:
        """GET /resource, optionally filtered/paginated: ``list(userId=3, _limit=5)``."""
        return self._client.get(self._path(), params=query or None)

    def get(self, resource_id: ResourceId) -> requests.Response:
        return self._client.get(self._path(resource_id))

    def head(self, resource_id: ResourceId) -> requests.Response:
        return self._client.head(self._path(resource_id))

    def create(self, payload: dict[str, Any]) -> requests.Response:
        return self._client.post(self._path(), json=payload)

    def replace(self, resource_id: ResourceId, payload: dict[str, Any]) -> requests.Response:
        """PUT: full replacement."""
        return self._client.put(self._path(resource_id), json=payload)

    def update(self, resource_id: ResourceId, changes: dict[str, Any]) -> requests.Response:
        """PATCH: partial update."""
        return self._client.patch(self._path(resource_id), json=changes)

    def delete(self, resource_id: ResourceId) -> requests.Response:
        return self._client.delete(self._path(resource_id))

    def children(self, resource_id: ResourceId, child: str) -> requests.Response:
        """GET /resource/{id}/{child}: nested collections such as /users/1/todos."""
        return self._client.get(self._path(resource_id, child))


class PostsService(ResourceService):
    resource = "posts"

    def comments_of(self, post_id: ResourceId) -> requests.Response:
        return self.children(post_id, "comments")


class CommentsService(ResourceService):
    resource = "comments"

    def for_post(self, post_id: ResourceId) -> requests.Response:
        return self.list(postId=post_id)


class UsersService(ResourceService):
    resource = "users"

    def posts_of(self, user_id: ResourceId) -> requests.Response:
        return self.children(user_id, "posts")

    def todos_of(self, user_id: ResourceId) -> requests.Response:
        return self.children(user_id, "todos")

    def albums_of(self, user_id: ResourceId) -> requests.Response:
        return self.children(user_id, "albums")


class TodosService(ResourceService):
    resource = "todos"


class AlbumsService(ResourceService):
    resource = "albums"

    def photos_of(self, album_id: ResourceId) -> requests.Response:
        return self.children(album_id, "photos")


class PhotosService(ResourceService):
    resource = "photos"


# TODO(future): add AuthService / OrdersService for your own API. Pattern: subclass
# ResourceService, set ``resource``, then add one method per business-specific endpoint
# (for example ``def cancel(self, order_id): return self._client.post(self._path(order_id, "cancel"))``).
