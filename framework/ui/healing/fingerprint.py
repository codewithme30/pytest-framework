"""
Module  : framework.ui.healing.fingerprint
Author  : Anil Kalisetti
Purpose : A compact, comparable description of a page element, and how to read it from a page.

A fingerprint is what a person would use to recognise a button even if its id changed: what
it says, what kind of control it is, its test attribute, its neighbours. It is stored once on
a known-good build and compared against the page when a locator stops matching.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True)
class ElementFingerprint:
    tag: str
    id: str = ""
    name: str = ""
    type: str = ""
    role: str = ""
    aria_label: str = ""
    data_test: str = ""
    placeholder: str = ""
    classes: tuple[str, ...] = ()
    text: str = ""
    parent_tag: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Only non-empty fields, so the committed baseline file stays small and readable."""
        data: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value:
                data[f.name] = list(value) if f.name == "classes" else value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ElementFingerprint:
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}  # ignore keys from newer versions
        clean["classes"] = tuple(clean.get("classes", ()))
        clean.setdefault("tag", "")
        return cls(**clean)


@dataclass(frozen=True)
class Candidate:
    """An element currently on the page that might be the one we lost."""

    fingerprint: ElementFingerprint
    selector: str  # a CSS selector that finds it


class PageReader(ABC):
    """Reads fingerprints from a page. Abstract so tests (and other engines) can swap it."""

    @abstractmethod
    def describe(self, element: Any) -> ElementFingerprint:
        """Fingerprint of one element."""

    @abstractmethod
    def candidates(self, tag: str) -> list[Candidate]:
        """Visible elements of ``tag`` on the current page, each with a CSS selector."""


# One JavaScript helper shared by both reads. It runs inside the browser, so a page with
# 300 inputs costs ONE round trip instead of 300 WebDriver calls.
_DESCRIBE_JS = """
const describe = (el) => ({
  tag: el.tagName.toLowerCase(),
  id: el.id || '',
  name: el.getAttribute('name') || '',
  type: el.getAttribute('type') || '',
  role: el.getAttribute('role') || '',
  aria_label: el.getAttribute('aria-label') || '',
  data_test: el.getAttribute('data-test') || el.getAttribute('data-testid') || '',
  placeholder: el.getAttribute('placeholder') || '',
  classes: Array.from(el.classList),
  text: (el.innerText || el.textContent || el.value || '').trim().replace(/\\s+/g, ' ').slice(0, 80),
  parent_tag: el.parentElement ? el.parentElement.tagName.toLowerCase() : ''
});
"""

_SELECTOR_JS = """
const esc = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/([^a-zA-Z0-9_-])/g, '\\\\$1');
const selectorFor = (el) => {
  // Prefer the most stable handle; fall back to a structural path as the last resort.
  const dt = el.getAttribute('data-test');
  if (dt) return '[data-test="' + dt.replace(/"/g, '\\\\"') + '"]';
  if (el.id) return '#' + esc(el.id);
  const parts = [];
  for (let node = el; node && node.nodeType === 1 && node !== document.body; node = node.parentElement) {
    const tag = node.tagName.toLowerCase();
    const same = Array.from(node.parentElement.children).filter((c) => c.tagName === node.tagName);
    parts.unshift(same.length > 1 ? tag + ':nth-of-type(' + (same.indexOf(node) + 1) + ')' : tag);
  }
  return 'body > ' + parts.join(' > ');
};
const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
"""

DESCRIBE_SCRIPT = _DESCRIBE_JS + "return describe(arguments[0]);"
CANDIDATES_SCRIPT = (
    _DESCRIBE_JS
    + _SELECTOR_JS
    + """
return Array.from(document.getElementsByTagName(arguments[0]))
  .filter(visible)
  .slice(0, 300)
  .map((el) => ({fingerprint: describe(el), selector: selectorFor(el)}));
"""
)


class JsPageReader(PageReader):
    """Reads the live page through ``driver.execute_script`` (works with any Selenium driver)."""

    def __init__(self, driver: Any) -> None:
        self._driver = driver

    def describe(self, element: Any) -> ElementFingerprint:
        return ElementFingerprint.from_dict(self._driver.execute_script(DESCRIBE_SCRIPT, element))

    def candidates(self, tag: str) -> list[Candidate]:
        rows = self._driver.execute_script(CANDIDATES_SCRIPT, tag) or []
        return [Candidate(ElementFingerprint.from_dict(r["fingerprint"]), r["selector"]) for r in rows]
