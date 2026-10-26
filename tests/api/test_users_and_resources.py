"""
Module  : tests/api/test_users_and_resources.py
Author  : Anil Kalisetti
Purpose : Users, todos, albums, photos and comments: schemas, relationships, filters and data rules.

Real-life analogy: these are the entities of a customer portal (people, their task lists, their
photo albums). The checks mirror what a consumer app relies on: stable shapes and valid links.
"""

from __future__ import annotations

import pytest

from framework.api.assertions import array_of, assert_json_schema, assert_status

pytestmark = pytest.mark.network


# --- users ----------------------------------------------------------------------------------------------------
@pytest.mark.smoke
def test_users_list_matches_schema(api_client, schemas):
    response = api_client.get("/users")
    assert_status(response, 200)
    assert len(response.json()) == 10
    assert_json_schema(response.json(), array_of(schemas["user"]))


def test_user_ids_and_emails_are_unique(api_client):
    users = api_client.get("/users").json()
    assert len({u["id"] for u in users}) == len(users)
    assert len({u["email"].lower() for u in users}) == len(users)


def test_known_user_details(api_client):
    user = api_client.get("/users/1").json()
    assert (user["name"], user["username"]) == ("Leanne Graham", "Bret")


def test_geo_coordinates_are_valid_numbers_in_range(api_client):
    for user in api_client.get("/users").json():
        geo = user["address"]["geo"]
        assert -90 <= float(geo["lat"]) <= 90, f"user {user['id']} latitude"
        assert -180 <= float(geo["lng"]) <= 180, f"user {user['id']} longitude"


def test_unknown_user_returns_404(api_client):
    assert_status(api_client.get("/users/11"), 404)


@pytest.mark.parametrize(
    ("child", "expected_count"),
    [("posts", 10), ("todos", 20), ("albums", 10)],
)
def test_user_relationships(api_client, child, expected_count):
    items = api_client.get(f"/users/1/{child}").json()
    assert len(items) == expected_count
    assert {item["userId"] for item in items} == {1}


# --- todos ----------------------------------------------------------------------------------------------------------
def test_todos_match_schema(api_client, schemas):
    todos = api_client.get("/todos", params={"_limit": 50}).json()
    assert len(todos) == 50
    assert_json_schema(todos, array_of(schemas["todo"]))


@pytest.mark.parametrize("completed", ["true", "false"])
def test_todo_filter_by_completion(api_client, completed):
    todos = api_client.get("/todos", params={"completed": completed}).json()
    assert todos, "expected at least one todo"
    assert {t["completed"] for t in todos} == {completed == "true"}


def test_todo_filters_can_be_combined(api_client):
    todos = api_client.get("/todos", params={"userId": 1, "completed": "false"}).json()
    assert todos
    assert all(t["userId"] == 1 and t["completed"] is False for t in todos)


# --- albums & photos ------------------------------------------------------------------------------------------------------
def test_albums_match_schema(api_client, schemas):
    albums = api_client.get("/albums").json()
    assert len(albums) == 100
    assert_json_schema(albums, array_of(schemas["album"]))


def test_album_contains_fifty_photos(api_client, schemas):
    photos = api_client.get("/albums/1/photos").json()
    assert len(photos) == 50
    assert {p["albumId"] for p in photos} == {1}
    assert_json_schema(photos, array_of(schemas["photo"]))


@pytest.mark.parametrize("limit", [1, 5, 25])
def test_photo_page_size_is_respected(api_client, limit):
    assert len(api_client.get("/photos", params={"_limit": limit}).json()) == limit


# --- comments ---------------------------------------------------------------------------------------------------------------
def test_comments_match_schema(api_client, schemas):
    comments = api_client.get("/comments", params={"_limit": 100}).json()
    assert len(comments) == 100
    assert_json_schema(comments, array_of(schemas["comment"]))


def test_every_comment_references_an_existing_post(api_client):
    comments = api_client.get("/comments", params={"_limit": 100}).json()
    assert all(1 <= c["postId"] <= 100 for c in comments)


@pytest.mark.parametrize("resource", ["posts", "comments", "albums", "photos", "todos", "users"])
def test_every_resource_collection_is_reachable(api_client, resource):
    assert_status(api_client.get(f"/{resource}", params={"_limit": 1}), 200)
