"""
Module  : framework.ui.healing.transport
Author  : Anil Kalisetti
Purpose : Move heal events and recorded fingerprints from a test (maybe in an xdist worker)
          to the reporting plugins in the controller process, as JSON in ``user_properties``.

pytest-xdist forwards ``user_properties`` with each test report, so no shared file or lock is
needed and parallel runs cannot corrupt the results.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from framework.ui.healing.fingerprint import ElementFingerprint
from framework.ui.healing.healer import HealEvent, LocatorHealer

HEALS_KEY = "locator_heals"
FINGERPRINTS_KEY = "locator_fingerprints"


def export_properties(healer: LocatorHealer) -> list[tuple[str, str]]:
    """``user_properties`` entries describing what this healer did (empty when nothing happened)."""
    props: list[tuple[str, str]] = []
    if healer.events:
        props.append((HEALS_KEY, json.dumps([e.to_dict() for e in healer.events])))
    if healer.recorded:
        props.append((FINGERPRINTS_KEY, json.dumps({k: v.to_dict() for k, v in healer.recorded.items()})))
    return props


def parse_heals(properties: Iterable[tuple[str, Any]] | Mapping[str, Any]) -> list[HealEvent]:
    props = dict(properties)
    raw = props.get(HEALS_KEY)
    return [HealEvent.from_dict(item) for item in json.loads(raw)] if raw else []


def parse_fingerprints(properties: Iterable[tuple[str, Any]] | Mapping[str, Any]) -> dict[str, ElementFingerprint]:
    raw = dict(properties).get(FINGERPRINTS_KEY)
    return {k: ElementFingerprint.from_dict(v) for k, v in json.loads(raw).items()} if raw else {}
