"""
Module  : tests/unit/test_api_services.py
Author  : Anil Kalisetti
Purpose : Resource service classes build the right URLs, verbs and payloads (stub server, no internet).
"""

from __future__ import annotations

import json

import pytest

from framework.api import ApiClient
from framework.api.services import CommentsService, PostsService, ResourceService, UsersService


@pytest.fixture
def client(stub_server):
    with ApiClient(stub_server.url, retries=0) as api:
        yield api


def test_crud_methods_use_the_right_verb_and_url(stub_server, client):
    for method, path in [("GET", "/posts"), ("GET", "/posts/7"), ("POST", "/posts"), ("PUT", "/posts/7"),
                         ("PATCH", "/posts/7"), ("DELETE", "/posts/7"), ("HEAD", "/posts/7")]:  # fmt: skip
        stub_server.add(method, path, body={"ok": True})
    posts = PostsService(client)

    posts.list(), posts.get(7), posts.create({"title": "t"}), posts.replace(7, {"title": "r"})
    posts.update(7, {"title": "p"}), posts.delete(7), posts.head(7)

    assert [(c.method, c.path) for c in stub_server.calls] == [
        ("GET", "/posts"), ("GET", "/posts/7"), ("POST", "/posts"), ("PUT", "/posts/7"),
        ("PATCH", "/posts/7"), ("DELETE", "/posts/7"), ("HEAD", "/posts/7"),
    ]  # fmt: skip
    assert json.loads(stub_server.calls[2].body) == {"title": "t"}
    assert json.loads(stub_server.calls[4].body) == {"title": "p"}


def test_list_sends_filters_as_query_string(stub_server, client):
    stub_server.add("GET", "/posts", body=[])
    PostsService(client).list(userId=3, _limit=5)
    assert stub_server.calls[0].query == {"userId": ["3"], "_limit": ["5"]}


def test_list_without_filters_sends_no_query(stub_server, client):
    stub_server.add("GET", "/posts", body=[])
    PostsService(client).list()
    assert stub_server.calls[0].query == {}


def test_specialised_services_add_their_own_endpoints(stub_server, client):
    for path in ("/posts/2/comments", "/comments", "/users/1/todos", "/users/1/posts", "/users/1/albums"):
        stub_server.add("GET", path, body=[])
    PostsService(client).comments_of(2)
    CommentsService(client).for_post(2)
    users = UsersService(client)
    users.todos_of(1), users.posts_of(1), users.albums_of(1)

    assert [c.path for c in stub_server.calls] == [
        "/posts/2/comments", "/comments", "/users/1/todos", "/users/1/posts", "/users/1/albums",
    ]  # fmt: skip
    assert stub_server.calls[1].query == {"postId": ["2"]}


def test_services_share_one_client_so_retries_and_auth_apply_to_all(client):
    client.set_bearer_token("abc")
    assert PostsService(client)._client is UsersService(client)._client


def test_a_service_without_a_resource_is_a_programming_error(client):
    with pytest.raises(TypeError, match="resource"):
        ResourceService(client)
