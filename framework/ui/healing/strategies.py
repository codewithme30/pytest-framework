"""
Module  : framework.ui.healing.strategies
Author  : Anil Kalisetti
Purpose : The ways a broken locator can be repaired. Tried in order; first success wins.

    FallbackStrategy     selectors the author listed as alternates (cheap, predictable)
    FingerprintStrategy  closest visible element to the stored fingerprint (guarded)
    LlmStrategy          PLACEHOLDER for a future model-assisted strategy (not enabled)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from framework.ui.healing.fingerprint import ElementFingerprint, PageReader
from framework.ui.healing.locator import CSS_SELECTOR, Locator
from framework.ui.healing.scoring import SimilarityScorer


@dataclass(frozen=True)
class HealResult:
    strategy: str
    by: str
    value: str
    score: float | None  # None when the strategy has no similarity score (declared fallback)
    detail: str = ""


class HealingStrategy(ABC):
    name: ClassVar[str]

    @abstractmethod
    def heal(self, locator: Locator, baseline: ElementFingerprint | None) -> HealResult | None:
        """Return a working selector, or ``None`` when this strategy cannot say confidently."""


class FallbackStrategy(HealingStrategy):
    name = "fallback"

    def __init__(self, driver: Any) -> None:
        self._driver = driver

    def heal(self, locator: Locator, baseline: ElementFingerprint | None) -> HealResult | None:
        for by, value in locator.fallbacks:
            if any(el.is_displayed() for el in self._driver.find_elements(by, value)):
                return HealResult(self.name, by, value, None, "declared fallback matched")
        return None


class FingerprintStrategy(HealingStrategy):
    """Pick the best look-alike, but only when it is clearly the best (see the two guards)."""

    name = "fingerprint"

    def __init__(self, reader: PageReader, scorer: SimilarityScorer, threshold: float, margin: float) -> None:
        self._reader, self._scorer = reader, scorer
        self._threshold, self._margin = threshold, margin

    def heal(self, locator: Locator, baseline: ElementFingerprint | None) -> HealResult | None:
        if baseline is None or not baseline.tag:
            return None  # never recorded: nothing to compare against
        ranked = sorted(
            ((self._scorer.score(baseline, c.fingerprint), c) for c in self._reader.candidates(baseline.tag)),
            key=lambda pair: pair[0],
            reverse=True,
        )
        if not ranked:
            return None
        best_score, best = ranked[0]
        if best_score < self._threshold:
            return None  # guard 1: not similar enough, so fail honestly
        if len(ranked) > 1 and best_score - ranked[1][0] < self._margin:
            return None  # guard 2: two near-identical candidates, we would be guessing
        runner_up = f"{ranked[1][0]:.2f}" if len(ranked) > 1 else "n/a"
        return HealResult(
            self.name, CSS_SELECTOR, best.selector, round(best_score, 3),
            f"best look-alike (runner-up {runner_up})",
        )  # fmt: skip


class LlmStrategy(HealingStrategy):
    """PLACEHOLDER. Not part of the default chain; it exists to show where an LLM would plug in.

    TODO(future): implement only after answering these questions with your security team.
      1. Data: page HTML can contain personal data. Send only the candidate elements' attributes
         and text (already produced by ``PageReader.candidates``), never the whole DOM or values
         typed into fields. Redact emails, card numbers and tokens before sending.
      2. Determinism: ask the model to CHOOSE one candidate index from the list you pass (never to
         invent a selector) and use temperature 0. Treat the answer like any other strategy result:
         the healer verifies the selector exists and records the heal for human review.
      3. Cost/latency: call it last, only after cheaper strategies fail, once per locator per run
         (the healer caches results), with a hard timeout and a per-run call budget.
      4. Enable via a new setting such as ``heal_llm: bool = False`` plus an API key read from
         the environment (never from YAML), and add the strategy in ``LocatorHealer.from_settings``.
    """

    name = "llm"

    def heal(self, locator: Locator, baseline: ElementFingerprint | None) -> HealResult | None:
        raise NotImplementedError("LLM healing is a documented placeholder; see the class docstring")
