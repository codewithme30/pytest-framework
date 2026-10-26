"""
Module  : tests/unit/test_documentation.py
Author  : Anil Kalisetti
Purpose : Keep the documentation honest: options, settings and links cannot drift from the code.

Real-life example: a teammate adds ``--retry-budget`` but forgets the README; this test fails
in the pull request and names the option, so users never meet an undocumented switch.
"""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

import pytest

from framework.config.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
DOC_FILES = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").glob("*.md"))]
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _all_docs_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOC_FILES)


def test_every_command_line_option_is_documented():
    source = (ROOT / "framework" / "plugins" / "options.py").read_text(encoding="utf-8")
    options = re.findall(r'"(--[a-z][a-z-]+)"', source)
    assert options, "no options found: has options.py changed shape?"
    text = _all_docs_text()
    missing = [option for option in options if option not in text]
    assert not missing, f"document these options in README/docs: {missing}"


def test_every_setting_is_documented_in_the_user_guide():
    guide = (ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
    missing = [f.name.upper() for f in fields(Settings) if f.name.upper() not in guide]
    assert not missing, f"add these settings to the table in docs/USER_GUIDE.md: {missing}"


def test_every_documentation_file_is_linked_from_the_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    unlinked = [p.name for p in DOC_FILES if p.name != "README.md" and p.name not in readme]
    assert not unlinked, f"link these from README.md: {unlinked}"


@pytest.mark.parametrize("doc", DOC_FILES, ids=lambda p: p.name)
def test_relative_links_point_at_existing_files(doc):
    broken = []
    for target in _LINK.findall(doc.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = target.split("#", 1)[0]
        if path and not (doc.parent / path).exists():
            broken.append(target)
    assert not broken, f"{doc.name} has broken links: {broken}"


def test_every_make_target_is_listed_in_the_user_guide_or_readme():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    targets = re.findall(r"^([a-z][a-z-]*):.*?##", makefile, flags=re.MULTILINE)
    text = _all_docs_text()
    missing = [t for t in targets if f"make {t}" not in text and t not in ("help",)]
    assert not missing, f"mention these make targets in the docs: {missing}"
