"""
Module  : framework.core.tags
Author  : Anil Kalisetti
Purpose : Pure helpers behind ``--tags`` (friendly test grouping by marker).

A tag is a pytest marker. Teams group tests by purpose, then pick a group per pipeline stage:
    smoke        every commit        (minutes)
    sanity       after each deploy
    regression   nightly
    uat          before business sign-off
    e2e          full customer journeys
    critical     failure forces the build RED
Combine freely:  --tags "smoke or uat"   --tags "regression and not slow"
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence

STANDARD_TAGS: tuple[str, ...] = ("smoke", "sanity", "regression", "uat", "e2e", "critical")
_OPERATORS = frozenset({"and", "or", "not"})
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def combine_expressions(markexpr: str, tags: str) -> str:
    """Join an existing ``-m`` expression and ``--tags`` with AND (both must hold)."""
    markexpr, tags = (markexpr or "").strip(), (tags or "").strip()
    if markexpr and tags:
        return f"({markexpr}) and ({tags})"
    return markexpr or tags


def unknown_tags(expression: str, registered: Iterable[str]) -> list[str]:
    """Names used in ``expression`` that are not registered markers (usually typos)."""
    known = set(registered)
    used = {n for n in _NAME.findall(expression) if n not in _OPERATORS}
    return sorted(used - known)


def count_tags(marker_sets: Iterable[Iterable[str]], tags: Sequence[str]) -> dict[str, int]:
    """How many tests carry each tag (one test counts once per tag)."""
    counter: Counter[str] = Counter()
    for markers in marker_sets:
        present = set(markers)
        counter.update(tag for tag in tags if tag in present)
    return {tag: counter[tag] for tag in tags}
