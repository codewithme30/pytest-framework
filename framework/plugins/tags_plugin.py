"""
Module  : framework.plugins.tags_plugin
Author  : Anil Kalisetti
Purpose : ``--tags`` selection (typo-safe) and ``--list-tags`` inventory.

    pytest --tags smoke                      # same as -m smoke, but a typo is an error
    pytest --tags "smoke or uat" -m "not ui" # combined with -m using AND
    pytest --list-tags                       # how many tests carry each tag, then exit

Why not just ``-m``? pytest silently selects ZERO tests for ``-m smok``; in a pipeline that
looks like a green build. ``--tags`` rejects names that are not registered markers.
"""

from __future__ import annotations

import pytest

from framework.core.tags import STANDARD_TAGS, combine_expressions, count_tags, unknown_tags


def _registered_markers(config: pytest.Config) -> list[str]:
    return [line.split(":", 1)[0].split("(", 1)[0].strip() for line in config.getini("markers")]


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    tags = config.getoption("tags")
    if not tags:
        return
    unknown = unknown_tags(tags, _registered_markers(config))
    if unknown:
        raise pytest.UsageError(
            f"--tags: unknown tag(s) {', '.join(unknown)}. Registered: {', '.join(_registered_markers(config))}"
        )
    config.option.markexpr = combine_expressions(config.option.markexpr, tags)


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("list_tags"):
        return
    counts = count_tags(({m.name for m in item.iter_markers()} for item in items), STANDARD_TAGS)
    lines = ["", f"Tests per tag ({len(items)} collected):"]
    lines += [f"  {tag:<12}{count:>5}" for tag, count in counts.items()]
    print("\n".join(lines))  # noqa: T201 - deliberate CLI output
    pytest.exit("tag listing complete", returncode=0)
