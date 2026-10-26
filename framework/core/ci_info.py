"""
Module  : framework.core.ci_info
Author  : Anil Kalisetti
Purpose : Detect which CI/CD system is running the tests and expose build metadata.

The same suite runs on a laptop, GitHub Actions, Jenkins, GitLab CI or Azure DevOps. Reports
and Jira defects include these details so stakeholders can trace a result to an exact build.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class BuildInfo:
    provider: str
    build_number: str
    branch: str
    commit: str
    build_url: str


def detect_build_info(env: Mapping[str, str] | None = None) -> BuildInfo:
    """Inspect well-known CI environment variables; fall back to ``local``."""
    e = os.environ if env is None else env

    if e.get("GITHUB_ACTIONS") == "true":
        server = e.get("GITHUB_SERVER_URL", "https://github.com")
        url = f"{server}/{e.get('GITHUB_REPOSITORY', '')}/actions/runs/{e.get('GITHUB_RUN_ID', '')}"
        return BuildInfo(
            "github-actions",
            e.get("GITHUB_RUN_NUMBER", ""),
            e.get("GITHUB_REF_NAME", ""),
            e.get("GITHUB_SHA", "")[:8],
            url,
        )
    if e.get("JENKINS_URL"):
        return BuildInfo(
            "jenkins",
            e.get("BUILD_NUMBER", ""),
            e.get("GIT_BRANCH", ""),
            e.get("GIT_COMMIT", "")[:8],
            e.get("BUILD_URL", ""),
        )
    if e.get("GITLAB_CI") == "true":
        return BuildInfo(
            "gitlab-ci",
            e.get("CI_PIPELINE_IID", ""),
            e.get("CI_COMMIT_REF_NAME", ""),
            e.get("CI_COMMIT_SHORT_SHA", ""),
            e.get("CI_PIPELINE_URL", ""),
        )
    if e.get("TF_BUILD"):
        url = (
            f"{e.get('SYSTEM_TEAMFOUNDATIONCOLLECTIONURI', '')}{e.get('SYSTEM_TEAMPROJECT', '')}"
            f"/_build/results?buildId={e.get('BUILD_BUILDID', '')}"
        )
        return BuildInfo(
            "azure-devops",
            e.get("BUILD_BUILDNUMBER", ""),
            e.get("BUILD_SOURCEBRANCHNAME", ""),
            e.get("BUILD_SOURCEVERSION", "")[:8],
            url,
        )
    # TODO(future): Bitbucket Pipelines (BITBUCKET_BUILD_NUMBER), CircleCI (CIRCLE_BUILD_NUM),
    # TeamCity (TEAMCITY_VERSION). Add a branch above following the same pattern.
    return BuildInfo("local", "local", "", "", "")
