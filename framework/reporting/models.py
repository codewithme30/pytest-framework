"""
Module  : framework.reporting.models
Author  : Anil Kalisetti
Purpose : Plain data classes describing a test run, plus the build-verdict rules.

Verdict rules (thresholds are configurable via PASS_RATE_GREEN / PASS_RATE_AMBER):
    GREEN   pass rate >= green threshold AND no ``critical`` test failed
    AMBER   pass rate >= amber threshold AND no ``critical`` test failed
    RED     anything else (including any failed ``critical`` test)
    NO DATA nothing was executed (all skipped / deselected)

Pass rate = passed / (passed + failed + error). Skipped and expected-failure (xfail) tests are
reported separately and never inflate or deflate the rate.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cached_property

from framework.config.settings import BROWSERS
from framework.core.tags import STANDARD_TAGS

FAILING = frozenset({"failed", "error"})
_PARAM_SUFFIX = re.compile(r"\[([^\]]*)\]$")


@dataclass
class CaseResult:
    nodeid: str
    layer: str
    outcome: str  # passed | failed | error | skipped | xfailed | xpassed
    duration: float = 0.0
    message: str = ""
    markers: tuple[str, ...] = ()
    screenshot: str = ""
    jira_key: str = ""
    reruns: int = 0

    @property
    def short_name(self) -> str:
        return self.nodeid.rsplit("::", 1)[-1]

    @property
    def browser(self) -> str:
        """Browser name when the test id carries one (``test_login[firefox]``), else ''."""
        suffix = _PARAM_SUFFIX.search(self.nodeid)
        tokens = suffix.group(1).split("-") if suffix else []
        return next((t for t in tokens if t in BROWSERS), "")


@dataclass
class RunMetadata:
    product: str = "Application"
    environment: str = "qa"
    provider: str = "local"
    build_number: str = "local"
    branch: str = ""
    commit: str = ""
    build_url: str = ""
    execution_mode: str = "local"
    browser: str = ""
    started_at: str = ""
    duration_seconds: float = 0.0
    jira_base_url: str = ""


@dataclass
class RunSummary:
    metadata: RunMetadata
    results: list[CaseResult]
    green_threshold: float = 95.0
    amber_threshold: float = 80.0
    coverage_pct: float | None = None
    _extra: dict[str, object] = field(default_factory=dict, repr=False)

    @cached_property
    def counts(self) -> Counter[str]:
        return Counter(r.outcome for r in self.results)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def executed(self) -> int:
        return sum(self.counts[o] for o in ("passed", "failed", "error"))

    @property
    def failing(self) -> list[CaseResult]:
        return [r for r in self.results if r.outcome in FAILING]

    @property
    def pass_rate(self) -> float:
        return 100.0 * self.counts["passed"] / self.executed if self.executed else 0.0

    @property
    def flaky(self) -> list[CaseResult]:
        """Tests that passed only after being re-run: a reliability risk worth fixing."""
        return [r for r in self.results if r.reruns and r.outcome == "passed"]

    @property
    def critical_failures(self) -> list[CaseResult]:
        return [r for r in self.failing if "critical" in r.markers]

    @property
    def verdict(self) -> str:
        if self.executed == 0:
            return "NO DATA"
        if self.critical_failures or self.pass_rate < self.amber_threshold:
            return "RED"
        return "GREEN" if self.pass_rate >= self.green_threshold else "AMBER"

    def by_layer(self) -> dict[str, Counter[str]]:
        layers: dict[str, Counter[str]] = {}
        for r in self.results:
            layers.setdefault(r.layer, Counter())[r.outcome] += 1
        return dict(sorted(layers.items()))

    def by_tag(self, tags: Sequence[str] = STANDARD_TAGS) -> dict[str, Counter[str]]:
        """Outcome counts per tag (smoke, uat, ...). Tags nobody used are left out."""
        grouped: dict[str, Counter[str]] = {}
        for tag in tags:
            counter = Counter(r.outcome for r in self.results if tag in r.markers)
            if counter:
                grouped[tag] = counter
        return grouped

    def by_browser(self) -> dict[str, Counter[str]]:
        """Outcome counts per browser, for UI tests that ran on a browser matrix."""
        grouped: dict[str, Counter[str]] = {}
        for r in self.results:
            if r.browser:
                grouped.setdefault(r.browser, Counter())[r.outcome] += 1
        return dict(sorted(grouped.items()))

    @staticmethod
    def layer_pass_rate(counter: Counter[str]) -> float | None:
        executed = counter["passed"] + counter["failed"] + counter["error"]
        return 100.0 * counter["passed"] / executed if executed else None

    def slowest(self, limit: int = 10) -> list[CaseResult]:
        return sorted(self.results, key=lambda r: r.duration, reverse=True)[:limit]

    @property
    def headline(self) -> str:
        """One plain-English sentence for non-technical readers."""
        fails = len(self.failing)
        base = f"{self.pass_rate:.1f}% of {self.executed} automated checks passed"
        weakest = self._weakest_layer()
        if self.verdict == "NO DATA":
            return "No checks were executed in this run."
        if self.verdict == "GREEN":
            tail = f" ({fails} failure(s) listed below)." if fails else "."
            return f"Build is healthy: {base}{tail}"
        if self.verdict == "AMBER":
            return f"Build needs attention: {base}; {fails} failed{weakest}."
        crit = f" {len(self.critical_failures)} critical check(s) failed." if self.critical_failures else ""
        return f"Build is NOT ready for release: {base}; {fails} failed{weakest}.{crit}"

    def _weakest_layer(self) -> str:
        rated = [
            (self.layer_pass_rate(c), name)
            for name, c in self.by_layer().items()
            if c["failed"] + c["error"]
        ]
        rated = [(rate, name) for rate, name in rated if rate is not None]
        return f", mostly in the {min(rated)[1]} area" if rated else ""
