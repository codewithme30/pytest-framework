"""
Module  : tests/api/test_posts_crud.py
Author  : Anil Kalisetti
Purpose : Complete REST coverage of one resource: list, read, filter, paginate, create,
          replace, partially update, delete, head, plus boundary and negative inputs.

API under test: JSONPlaceholder /posts (a free fake REST API). It accepts writes and
returns realistic responses but does NOT persist them, so a created post gets id 101 and
cannot be fetched afterwards; the tests assert the response contract, not persistence.
"""

from __future__ import annotations

import pytest

from framework.api.assertions import (
    array_of,
    assert_header_contains,
    assert_json_schema,
    assert_json_subset,
    assert_response_time,
    assert_status,
)
from framework.core.data_factory import build_post_payload

pytestmark = pytest.mark.network

TOTAL_POSTS = 100
POSTS_PER_USER = 10


# --- READ ---------------------------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.critical
def test_list_posts_returns_the_full_collection(posts_api, schemas):
    response = posts_api.list()
    assert_status(response, 200)
    posts = response.json()
    assert len(posts) == TOTAL_POSTS
    assert_json_schema(posts, array_of(schemas["post"]))


@pytest.mark.smoke
@pytest.mark.parametrize("post_id", [1, 50, 100], ids=["first", "middle", "last"])
def test_get_post_by_id(posts_api, schemas, post_id):
    response = posts_api.get(post_id)
    assert_status(response, 200)
    assert response.json()["id"] == post_id
    assert_json_schema(response.json(), schemas["post"])


@pytest.mark.parametrize("bad_id", [0, 101, 99999, -1, "abc"], ids=["zero", "just-past-last", "huge", "negative", "non-numeric"])
def test_unknown_post_returns_404(posts_api, bad_id):
    assert_status(posts_api.get(bad_id), 404)


def test_response_headers_describe_json_content(posts_api):
    assert_header_contains(posts_api.get(1), "Content-Type", "application/json")


def test_response_time_is_within_budget(posts_api):
    # Generous budget: this guards against order-of-magnitude regressions, not network jitter.
    assert_response_time(posts_api.get(1), 5)


def test_head_returns_headers_without_body(posts_api):
    response = posts_api.head(1)
    assert_status(response, 200)
    assert response.text == ""


# --- FILTER / PAGINATE / NESTED -----------------------------------------------------------------------------
def test_filter_by_user_returns_only_that_users_posts(posts_api):
    posts = posts_api.list(userId=3).json()
    assert len(posts) == POSTS_PER_USER
    assert {p["userId"] for p in posts} == {3}


def test_filter_with_no_match_returns_empty_list_not_404(posts_api):
    response = posts_api.list(userId=9999)
    assert_status(response, 200)
    assert response.json() == []


@pytest.mark.parametrize(
    ("page", "expected_ids"),
    [(1, list(range(1, 11))), (2, list(range(11, 21))), (10, list(range(91, 101))), (11, [])],
    ids=["first-page", "second-page", "last-page", "past-the-end"],
)
def test_pagination(posts_api, page, expected_ids):
    response = posts_api.list(_page=page, _limit=10)
    assert_status(response, 200)
    assert [p["id"] for p in response.json()] == expected_ids


def test_pagination_reports_total_count_header(posts_api):
    response = posts_api.list(_page=1, _limit=5)
    assert response.headers.get("x-total-count") == str(TOTAL_POSTS)


def test_nested_comments_belong_to_the_post(posts_api, schemas):
    comments = posts_api.comments_of(1).json()
    assert len(comments) == 5
    assert {c["postId"] for c in comments} == {1}
    assert_json_schema(comments, array_of(schemas["comment"]))


def test_nested_route_matches_query_filter(comments_api, posts_api):
    nested = posts_api.comments_of(2).json()
    filtered = comments_api.for_post(2).json()
    assert [c["id"] for c in nested] == [c["id"] for c in filtered]


# --- CREATE / UPDATE / DELETE -----------------------------------------------------------------------------------
@pytest.mark.smoke
def test_create_post_echoes_payload_and_assigns_id(posts_api, schemas):
    payload = build_post_payload()
    response = posts_api.create(payload)
    assert_status(response, 201)
    assert_json_subset(response.json(), payload)
    assert response.json()["id"] == TOTAL_POSTS + 1
    assert_json_schema(response.json(), schemas["post"])


def test_create_with_empty_object_still_assigns_id(posts_api):
    response = posts_api.create({})
    assert_status(response, 201)
    assert response.json() == {"id": TOTAL_POSTS + 1}


def test_create_with_unicode_text_round_trips(posts_api):
    payload = {"title": "Café ☕ 张伟", "body": "naïve résumé", "userId": 1}
    assert_json_subset(posts_api.create(payload).json(), payload)


def test_replace_post_with_put(posts_api):
    payload = {"id": 1, "title": "replaced", "body": "new body", "userId": 1}
    response = posts_api.replace(1, payload)
    assert_status(response, 200)
    assert_json_subset(response.json(), payload)


def test_put_is_idempotent(posts_api):
    payload = {"id": 1, "title": "same", "body": "same", "userId": 1}
    first, second = posts_api.replace(1, payload), posts_api.replace(1, payload)
    assert first.json() == second.json()


def test_patch_changes_only_the_sent_field(posts_api):
    response = posts_api.update(1, {"title": "patched title"})
    assert_status(response, 200)
    body = response.json()
    assert body["title"] == "patched title"
    assert body["body"]  # untouched fields are preserved
    assert body["userId"] == 1


def test_delete_post(posts_api):
    response = posts_api.delete(1)
    assert_status(response, 200)
    assert response.json() == {}
