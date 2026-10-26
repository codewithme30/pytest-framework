"""
Module  : framework.ui.healing.store
Author  : Anil Kalisetti
Purpose : The committed baseline: one fingerprint per named locator, stored as readable JSON.

Workflow
    1. On a known-good build:  pytest -m "ui and smoke" --record-locators
    2. Review the diff of config/locator_fingerprints.json in a pull request and commit it.
    3. Normal runs only READ it, so a broken page can never poison the baseline and parallel
       workers cannot race on it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from framework.core.exceptions import ConfigurationError
from framework.ui.healing.fingerprint import ElementFingerprint

_META = {
    "note": "Recorded with `pytest --record-locators` on a known-good build. Review diffs before committing.",
}


class FingerprintStore:
    def __init__(self, path: Path, entries: Mapping[str, ElementFingerprint] | None = None) -> None:
        self._path = path
        self._entries: dict[str, ElementFingerprint] = dict(entries or {})

    @classmethod
    def load(cls, path: Path) -> FingerprintStore:
        if not path.exists():
            return cls(path)  # no baseline yet: only declared fallbacks can heal
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            entries = {k: ElementFingerprint.from_dict(v) for k, v in raw.get("fingerprints", {}).items()}
        except (ValueError, AttributeError, TypeError) as exc:
            raise ConfigurationError(f"Locator baseline {path} is not valid: {exc}") from exc
        return cls(path, entries)

    def get(self, name: str) -> ElementFingerprint | None:
        return self._entries.get(name)

    def merge(self, recorded: Mapping[str, ElementFingerprint]) -> None:
        self._entries.update(recorded)

    def __len__(self) -> int:
        return len(self._entries)

    def save(self) -> None:
        """Sorted keys and indentation keep pull-request diffs small and reviewable."""
        payload = {
            "_meta": _META,
            "fingerprints": {k: self._entries[k].to_dict() for k in sorted(self._entries)},
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
