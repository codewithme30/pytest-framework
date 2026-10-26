"""
Package : framework.ui.healing
Author  : Anil Kalisetti
Purpose : Self-healing locators: repair a broken selector at run time, and report every repair.

See docs/SELF_HEALING.md for the design, the safety rules and how to review a heal.
"""

from framework.ui.healing.fingerprint import Candidate, ElementFingerprint, JsPageReader, PageReader
from framework.ui.healing.healer import HealEvent, LocatorHealer
from framework.ui.healing.locator import Locator
from framework.ui.healing.scoring import SimilarityScorer, WeightedAttributeScorer
from framework.ui.healing.store import FingerprintStore
from framework.ui.healing.strategies import (
    FallbackStrategy,
    FingerprintStrategy,
    HealingStrategy,
    HealResult,
    LlmStrategy,
)

__all__ = [
    "Candidate", "ElementFingerprint", "FallbackStrategy", "FingerprintStore", "FingerprintStrategy",
    "HealEvent", "HealResult", "HealingStrategy", "JsPageReader", "LlmStrategy", "Locator",
    "LocatorHealer", "PageReader", "SimilarityScorer", "WeightedAttributeScorer",
]  # fmt: skip
