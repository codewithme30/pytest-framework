"""
Module  : tests/unit/test_ci_info.py
Author  : Anil Kalisetti
Purpose : CI provider detection and build metadata extraction.
"""

from __future__ import annotations

import pytest

from framework.core.ci_info import detect_build_info

GITHUB = {
    "GITHUB_ACTIONS": "true", "GITHUB_RUN_NUMBER": "482", "GITHUB_REF_NAME": "main",
    "GITHUB_SHA": "a1b2c3d4e5f6", "GITHUB_SERVER_URL": "https://github.com",
    "GITHUB_REPOSITORY": "acme/shop", "GITHUB_RUN_ID": "9001",
}  # fmt: skip
JENKINS = {
    "JENKINS_URL": "https://ci.acme.com/", "BUILD_NUMBER": "77", "GIT_BRANCH": "origin/release",
    "GIT_COMMIT": "ffeeddccbbaa", "BUILD_URL": "https://ci.acme.com/job/shop/77/",
}  # fmt: skip
GITLAB = {
    "GITLAB_CI": "true", "CI_PIPELINE_IID": "31", "CI_COMMIT_REF_NAME": "develop",
    "CI_COMMIT_SHORT_SHA": "1234abcd", "CI_PIPELINE_URL": "https://gitlab.acme.com/p/1",
}  # fmt: skip
AZURE = {
    "TF_BUILD": "True", "BUILD_BUILDNUMBER": "20261026.3", "BUILD_SOURCEBRANCHNAME": "main",
    "BUILD_SOURCEVERSION": "99887766aabb", "SYSTEM_TEAMFOUNDATIONCOLLECTIONURI": "https://dev.azure.com/acme/",
    "SYSTEM_TEAMPROJECT": "Shop", "BUILD_BUILDID": "555",
}  # fmt: skip


@pytest.mark.parametrize(
    ("env", "provider", "number", "branch", "commit"),
    [
        (GITHUB, "github-actions", "482", "main", "a1b2c3d4"),
        (JENKINS, "jenkins", "77", "origin/release", "ffeeddcc"),
        (GITLAB, "gitlab-ci", "31", "develop", "1234abcd"),
        (AZURE, "azure-devops", "20261026.3", "main", "99887766"),
    ],
    ids=["github", "jenkins", "gitlab", "azure"],
)
def test_provider_detection(env, provider, number, branch, commit):
    info = detect_build_info(env)
    assert (info.provider, info.build_number, info.branch, info.commit) == (provider, number, branch, commit)


def test_github_build_url_points_to_the_run():
    assert detect_build_info(GITHUB).build_url == "https://github.com/acme/shop/actions/runs/9001"


def test_azure_build_url_points_to_the_build():
    assert detect_build_info(AZURE).build_url.endswith("/Shop/_build/results?buildId=555")


def test_unknown_environment_is_reported_as_local():
    info = detect_build_info({})
    assert (info.provider, info.build_number) == ("local", "local")
