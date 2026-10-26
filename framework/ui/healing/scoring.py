"""
Module  : framework.ui.healing.scoring
Author  : Anil Kalisetti
Purpose : Decide how alike two elements are, in a way a person can read and argue with.

Rules of the default scorer
    * Different tag => 0. A button is never healed into a link.
    * Only attributes the ORIGINAL element had are compared. An id the old element never had
      cannot count against a candidate (and a new id on the candidate cannot count for it).
    * Each attribute has a weight; stable, meaningful ones (test attribute, visible text) weigh
      most. Result = weighted similarity / total weight, from 0.0 to 1.0.

Real-life example: the login button's id changes from ``login-button`` to ``signin-btn`` but it
still says "Login", is still a submit input with the same test attribute and classes. Almost
every weighted field still matches, so the score stays high (about 0.9). The password box
shares only its parent tag, so it scores near 0.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from difflib import SequenceMatcher

from framework.ui.healing.fingerprint import ElementFingerprint


class SimilarityScorer(ABC):
    @abstractmethod
    def score(self, baseline: ElementFingerprint, candidate: ElementFingerprint) -> float:
        """0.0 (nothing alike) to 1.0 (identical)."""


class WeightedAttributeScorer(SimilarityScorer):
    WEIGHTS: dict[str, float] = {
        "data_test": 3.0,
        "text": 3.0,
        "id": 2.0,
        "name": 2.0,
        "aria_label": 2.0,
        "placeholder": 1.5,
        "classes": 1.5,
        "type": 1.0,
        "role": 1.0,
        "parent_tag": 0.5,
    }
    _EXACT = frozenset({"data_test", "type", "role", "parent_tag"})  # must match exactly

    def score(self, baseline: ElementFingerprint, candidate: ElementFingerprint) -> float:
        if baseline.tag != candidate.tag:
            return 0.0
        total = earned = 0.0
        for attribute, weight in self.WEIGHTS.items():
            original = getattr(baseline, attribute)
            if not original:
                continue  # the old element did not have it: nothing to compare
            total += weight
            earned += weight * self._similarity(attribute, original, getattr(candidate, attribute))
        return earned / total if total else 0.0  # tag-only baseline carries no evidence

    def _similarity(self, attribute: str, original: object, other: object) -> float:
        if attribute == "classes":
            a, b = set(original), set(other)  # type: ignore[call-overload]
            return len(a & b) / len(a | b) if a | b else 0.0
        if attribute in self._EXACT:
            return 1.0 if original == other else 0.0
        if not other:
            return 0.0
        return SequenceMatcher(None, str(original).lower(), str(other).lower()).ratio()
