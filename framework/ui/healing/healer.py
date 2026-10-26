"""
Module  : framework.ui.healing.healer
Author  : Anil Kalisetti
Purpose : Orchestrates healing for one browser session and keeps the audit trail.

Responsibilities
    * decide whether a locator may heal (enabled, not opted out, not in record mode)
    * run the strategies in order and remember the first success for the rest of the test
    * record every heal as a ``HealEvent`` (shown in the management report)
    * in record mode, capture fingerprints of elements that were found normally
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from framework.core.logger import get_logger
from framework.ui.healing.fingerprint import ElementFingerprint, JsPageReader, PageReader
from framework.ui.healing.locator import Locator
from framework.ui.healing.scoring import WeightedAttributeScorer
from framework.ui.healing.store import FingerprintStore
from framework.ui.healing.strategies import FallbackStrategy, FingerprintStrategy, HealingStrategy

if TYPE_CHECKING:
    from framework.config.settings import Settings

log = get_logger("ui.healing")


@dataclass(frozen=True)
class HealEvent:
    locator: str  # "LoginPage.LOGIN_BUTTON"
    original: str  # "css selector=#login-button"
    healed: str
    strategy: str
    score: float | None
    url: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HealEvent:
        return cls(**data)


class LocatorHealer:
    def __init__(
        self,
        strategies: Sequence[HealingStrategy],
        store: FingerprintStore,
        reader: PageReader | None = None,
        *,
        enabled: bool = True,
        record: bool = False,
        heal_after: float = 3.0,
    ) -> None:
        self._strategies = tuple(strategies)
        self._store = store
        self._reader = reader
        self._enabled = enabled
        self._record = record
        self.heal_after = heal_after
        self._events: list[HealEvent] = []
        self._recorded: dict[str, ElementFingerprint] = {}
        self._healed: dict[tuple[str, str], Locator] = {}

    # --- construction ---------------------------------------------------------------------------
    @classmethod
    def disabled(cls) -> LocatorHealer:
        """Used by pages built without a healer: behaves exactly like plain Selenium."""
        return cls((), FingerprintStore(Path()), enabled=False)

    @classmethod
    def from_settings(cls, driver: Any, settings: Settings, store: FingerprintStore) -> LocatorHealer:
        reader = JsPageReader(driver)
        strategies = [
            FallbackStrategy(driver),
            FingerprintStrategy(reader, WeightedAttributeScorer(), settings.heal_threshold, settings.heal_margin),
            # TODO(future): append LlmStrategy(...) here once enabled (see its docstring).
        ]
        return cls(
            strategies,
            store,
            reader,
            enabled=settings.locator_healing,
            record=settings.record_locators,
            heal_after=settings.heal_after,
        )

    # --- decisions --------------------------------------------------------------------------------
    def can_heal(self, locator: Locator) -> bool:
        # Recording happens on a known-good build; healing there would hide the very drift we want to see.
        return self._enabled and not self._record and getattr(locator, "heal", False)

    def preferred(self, locator: Locator) -> Locator:
        """The healed replacement if this locator already healed earlier in the test, else itself."""
        return self._healed.get((locator[0], locator[1]), locator)

    # --- healing ------------------------------------------------------------------------------------
    def heal(self, locator: Locator, url: str = "") -> Locator | None:
        baseline = self._store.get(locator.name) if locator.name else None
        for strategy in self._strategies:
            result = strategy.heal(locator, baseline)
            if result is None:
                continue
            healed = locator.derive(result.by, result.value)
            self._healed[(locator[0], locator[1])] = healed
            event = HealEvent(
                locator=locator.name or f"{locator[0]}={locator[1]}",
                original=f"{locator[0]}={locator[1]}",
                healed=f"{result.by}={result.value}",
                strategy=result.strategy,
                score=result.score,
                url=url,
                detail=result.detail,
            )
            self._events.append(event)
            log.warning("LOCATOR HEALED %s: %s -> %s (%s, score=%s)", event.locator, event.original,
                        event.healed, event.strategy, event.score)  # fmt: skip
            return healed
        return None

    # --- recording --------------------------------------------------------------------------------------
    def record(self, locator: Locator, element: Any) -> Any:
        """In record mode remember what ``element`` looks like; always returns ``element``."""
        name = getattr(locator, "name", "")
        if self._record and name and self._reader is not None:
            self._recorded[name] = self._reader.describe(element)
        return element

    # --- audit trail -------------------------------------------------------------------------------------
    @property
    def events(self) -> list[HealEvent]:
        return list(self._events)

    @property
    def recorded(self) -> dict[str, ElementFingerprint]:
        return dict(self._recorded)
