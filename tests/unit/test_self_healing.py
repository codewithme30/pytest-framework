"""
Module  : tests/unit/test_self_healing.py
Author  : Anil Kalisetti
Purpose : Self-healing locators: scoring, strategies, safety guards, audit trail and the
          BasePage integration, all offline (fake page, fake Selenium).

Running example (a real-life one): a retail site renames the login button's id from
``login-button`` to ``signin-btn`` in a release. The button still says "Login".
"""

from __future__ import annotations

import importlib
import json
import sys
import types

import pytest

from framework.config.settings import load_settings
from framework.core.exceptions import ConfigurationError
from framework.plugins.healing_plugin import HealingCollector
from framework.reporting.executive_report import render_html, render_markdown, write_reports
from framework.reporting.models import CaseResult, RunMetadata, RunSummary
from framework.ui.healing import (
    Candidate,
    ElementFingerprint,
    FallbackStrategy,
    FingerprintStore,
    FingerprintStrategy,
    LlmStrategy,
    Locator,
    LocatorHealer,
    PageReader,
    WeightedAttributeScorer,
)
from framework.ui.healing.transport import export_properties, parse_fingerprints, parse_heals

CSS = "css selector"

LOGIN_BUTTON = ElementFingerprint(
    tag="input", id="login-button", data_test="login-button", type="submit", text="Login",
    classes=("submit-button", "btn_action"), parent_tag="div",
)  # fmt: skip
RENAMED_BUTTON = ElementFingerprint(
    tag="input", id="signin-btn", data_test="login-button", type="submit", text="Login",
    classes=("submit-button", "btn_action"), parent_tag="div",
)  # fmt: skip
PASSWORD_BOX = ElementFingerprint(
    tag="input", id="password", data_test="password", type="password", placeholder="Password",
    classes=("input_error", "form_input"), parent_tag="div",
)  # fmt: skip


class FakeReader(PageReader):
    def __init__(self, candidates: list[Candidate] | None = None) -> None:
        self._candidates = candidates or []

    def describe(self, element):
        return LOGIN_BUTTON

    def candidates(self, tag):
        return [c for c in self._candidates if c.fingerprint.tag == tag]


def _page(*pairs: tuple[ElementFingerprint, str]) -> FakeReader:
    return FakeReader([Candidate(fp, selector) for fp, selector in pairs])


def _strategy(reader: FakeReader, threshold: float = 0.8, margin: float = 0.1) -> FingerprintStrategy:
    return FingerprintStrategy(reader, WeightedAttributeScorer(), threshold, margin)


class Page:  # a class body gives locators their names, exactly like the real page objects
    BUTTON = Locator(CSS, "#login-button", fallbacks=['[data-test="login-button"]', ("xpath", "//input")])


# --- Locator ----------------------------------------------------------------------------------------
def test_locator_still_behaves_like_a_selenium_tuple():
    by, value = Page.BUTTON
    assert (by, value) == (CSS, "#login-button")
    assert Page.BUTTON == (CSS, "#login-button")
    assert len(Page.BUTTON) == 2


def test_locator_names_itself_from_the_class_that_owns_it():
    assert Page.BUTTON.name == "Page.BUTTON"


def test_fallbacks_are_normalised_and_bare_strings_mean_css():
    assert Page.BUTTON.fallbacks == ((CSS, '[data-test="login-button"]'), ("xpath", "//input"))


def test_healing_is_on_by_default_and_can_be_opted_out_per_locator():
    assert Locator(CSS, "#a").heal is True
    assert Locator(CSS, "#pay", heal=False).heal is False


def test_a_derived_locator_keeps_its_name_but_never_heals_again():
    healed = Page.BUTTON.derive(CSS, "#signin-btn")
    assert healed == (CSS, "#signin-btn") and healed.name == "Page.BUTTON" and healed.heal is False


# --- fingerprint ---------------------------------------------------------------------------------------
def test_fingerprint_dict_omits_empty_fields_and_round_trips():
    data = LOGIN_BUTTON.to_dict()
    assert "name" not in data and "role" not in data
    assert ElementFingerprint.from_dict(data) == LOGIN_BUTTON


def test_fingerprint_loading_ignores_unknown_keys_from_a_newer_version():
    assert ElementFingerprint.from_dict({"tag": "a", "future_field": 1}).tag == "a"


# --- scoring --------------------------------------------------------------------------------------------
def test_identical_elements_score_one():
    assert WeightedAttributeScorer().score(LOGIN_BUTTON, LOGIN_BUTTON) == 1.0


def test_renamed_id_still_scores_high_because_everything_else_matches():
    assert WeightedAttributeScorer().score(LOGIN_BUTTON, RENAMED_BUTTON) >= 0.85


def test_a_different_control_on_the_same_page_scores_low():
    assert WeightedAttributeScorer().score(LOGIN_BUTTON, PASSWORD_BOX) < 0.4


def test_different_tag_never_matches():
    link = ElementFingerprint(tag="a", id="login-button", data_test="login-button", text="Login")
    assert WeightedAttributeScorer().score(LOGIN_BUTTON, link) == 0.0


def test_attributes_the_original_never_had_cannot_hurt_a_candidate():
    sparse = ElementFingerprint(tag="button", text="Pay")
    rich = ElementFingerprint(tag="button", text="Pay", id="new-id", classes=("x",), data_test="pay")
    assert WeightedAttributeScorer().score(sparse, rich) == 1.0


def test_a_baseline_with_only_a_tag_carries_no_evidence():
    assert WeightedAttributeScorer().score(ElementFingerprint(tag="input"), RENAMED_BUTTON) == 0.0


# --- fingerprint strategy and its two guards ---------------------------------------------------------------
def test_renamed_button_is_found_among_the_other_inputs():
    reader = _page((PASSWORD_BOX, "#password"), (RENAMED_BUTTON, "[data-test=\"login-button\"]"))
    result = _strategy(reader).heal(Page.BUTTON, LOGIN_BUTTON)
    assert result is not None and result.value == '[data-test="login-button"]'
    assert result.strategy == "fingerprint" and result.score >= 0.85


def test_guard_one_nothing_similar_enough_means_no_heal():
    assert _strategy(_page((PASSWORD_BOX, "#password"))).heal(Page.BUTTON, LOGIN_BUTTON) is None


def test_guard_two_two_near_identical_candidates_means_no_heal():
    twin = ElementFingerprint(**{**RENAMED_BUTTON.to_dict(), "id": "login-btn-2", "classes": RENAMED_BUTTON.classes})
    reader = _page((RENAMED_BUTTON, "#a"), (twin, "#b"))
    assert _strategy(reader).heal(Page.BUTTON, LOGIN_BUTTON) is None  # we would be guessing


def test_no_baseline_or_no_candidates_means_no_heal():
    assert _strategy(_page((RENAMED_BUTTON, "#a"))).heal(Page.BUTTON, None) is None
    assert _strategy(_page()).heal(Page.BUTTON, LOGIN_BUTTON) is None


def test_a_stricter_threshold_refuses_a_borderline_match():
    reader = _page((RENAMED_BUTTON, "#a"))
    assert _strategy(reader, threshold=0.99).heal(Page.BUTTON, LOGIN_BUTTON) is None


# --- fallback strategy ------------------------------------------------------------------------------------------
def test_first_visible_declared_fallback_wins(dom_kit):
    dom = dom_kit.Dom({(CSS, '[data-test="login-button"]'): dom_kit.Element(), ("xpath", "//input"): dom_kit.Element()})
    result = FallbackStrategy(dom).heal(Page.BUTTON, None)
    assert (result.by, result.value, result.score) == (CSS, '[data-test="login-button"]', None)


def test_hidden_fallbacks_are_ignored(dom_kit):
    dom = dom_kit.Dom({(CSS, '[data-test="login-button"]'): dom_kit.Element(displayed=False)})
    assert FallbackStrategy(dom).heal(Page.BUTTON, None) is None


def test_the_llm_strategy_is_only_a_placeholder():
    with pytest.raises(NotImplementedError, match="placeholder"):
        LlmStrategy().heal(Page.BUTTON, None)


# --- healer: orchestration, audit trail, switches ---------------------------------------------------------------------
def _healer(dom, reader=None, store=None, **kwargs):
    reader = reader or _page((RENAMED_BUTTON, "#signin-btn"))
    store = store or FingerprintStore(None, {"Page.BUTTON": LOGIN_BUTTON})
    return LocatorHealer([FallbackStrategy(dom), _strategy(reader)], store, reader, **kwargs)


def test_declared_fallback_is_tried_before_the_fingerprint(dom_kit):
    dom = dom_kit.Dom({(CSS, '[data-test="login-button"]'): dom_kit.Element()})
    healer = _healer(dom)
    healed = healer.heal(Page.BUTTON, "https://shop.example/login")
    assert healed == (CSS, '[data-test="login-button"]')
    assert [e.strategy for e in healer.events] == ["fallback"]


def test_fingerprint_is_used_when_no_fallback_works(dom_kit):
    healer = _healer(dom_kit.Dom())
    assert healer.heal(Page.BUTTON, "https://shop.example/login") == (CSS, "#signin-btn")
    event = healer.events[0]
    assert (event.locator, event.original, event.healed) == ("Page.BUTTON", f"{CSS}=#login-button", f"{CSS}=#signin-btn")
    assert event.strategy == "fingerprint" and event.score >= 0.85 and event.url.endswith("/login")


def test_a_healed_locator_is_remembered_for_the_rest_of_the_test(dom_kit):
    healer = _healer(dom_kit.Dom())
    healed = healer.heal(Page.BUTTON)
    assert healer.preferred(Page.BUTTON) == healed
    assert healer.can_heal(healer.preferred(Page.BUTTON)) is False  # a healed locator never heals again


def test_a_failed_heal_records_nothing(dom_kit):
    healer = _healer(dom_kit.Dom(), reader=_page((PASSWORD_BOX, "#password")))
    assert healer.heal(Page.BUTTON) is None
    assert healer.events == []


def test_healer_switches():
    healer = LocatorHealer([], FingerprintStore(None))
    assert healer.can_heal(Page.BUTTON)
    assert not healer.can_heal(Locator(CSS, "#pay", heal=False))  # per-locator opt-out
    assert not healer.can_heal((CSS, "#plain-tuple"))  # not a Locator: nothing to heal with
    assert not LocatorHealer([], FingerprintStore(None), enabled=False).can_heal(Page.BUTTON)
    assert not LocatorHealer([], FingerprintStore(None), record=True).can_heal(Page.BUTTON)  # known-good build only
    assert not LocatorHealer.disabled().can_heal(Page.BUTTON)


def test_record_mode_captures_named_locators_only():
    healer = LocatorHealer([], FingerprintStore(None), FakeReader(), record=True)
    assert healer.record(Page.BUTTON, "element") == "element"  # returns the element unchanged
    healer.record(Locator(CSS, "#unnamed"), "other")
    assert list(healer.recorded) == ["Page.BUTTON"]
    outside_record_mode = LocatorHealer([], FingerprintStore(None), FakeReader())
    outside_record_mode.record(Page.BUTTON, "element")
    assert outside_record_mode.recorded == {}


def test_events_are_returned_as_a_copy(dom_kit):
    healer = _healer(dom_kit.Dom())
    healer.heal(Page.BUTTON)
    healer.events.clear()
    assert len(healer.events) == 1


# --- BasePage integration (fake Selenium) ---------------------------------------------------------------------------------
@pytest.fixture
def demo(fake_selenium, monkeypatch, dom_kit):
    for name in ("framework.ui.base_page", "framework.ui.pages"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    base = importlib.import_module("framework.ui.base_page")

    class DemoPage(base.BasePage):
        BUTTON = base.css("#login-button", fallbacks=['[data-test="login-button"]'])
        PAY = base.css("#pay", fallbacks=["#pay-2"], heal=False)

        def is_loaded(self) -> bool:
            return True

    def build(elements, healer=None):
        dom = dom_kit.Dom(elements)
        return DemoPage(dom, 10, healer), dom

    return types.SimpleNamespace(build=build, Page=DemoPage, fake=fake_selenium, dom_kit=dom_kit)


def test_a_working_locator_is_untouched(demo):
    button = demo.dom_kit.Element()
    page, dom = demo.build({(CSS, "#login-button"): button})
    healer = _healer(dom)
    page._healer = healer
    page.click(demo.Page.BUTTON)
    assert button.clicked and healer.events == []


def test_a_broken_locator_heals_through_a_declared_fallback(demo):
    fallback = demo.dom_kit.Element()
    page, dom = demo.build({(CSS, '[data-test="login-button"]'): fallback})
    healer = _healer(dom)
    page._healer = healer
    page.click(demo.Page.BUTTON)
    assert fallback.clicked
    page.click(demo.Page.BUTTON)  # second use goes straight to the healed selector
    assert len(healer.events) == 1


def test_a_broken_locator_with_no_trustworthy_match_fails_like_plain_selenium(demo):
    page, dom = demo.build({(CSS, "#password"): demo.dom_kit.Element()})
    page._healer = _healer(dom, reader=_page((PASSWORD_BOX, "#password")))
    with pytest.raises(demo.fake.TimeoutException):
        page.click(demo.Page.BUTTON)
    assert page._healer.events == []


def test_opted_out_locators_fail_even_when_a_fallback_exists(demo):
    page, dom = demo.build({(CSS, "#pay-2"): demo.dom_kit.Element()})
    page._healer = _healer(dom)
    with pytest.raises(demo.fake.TimeoutException):
        page.click(demo.Page.PAY)
    assert page._healer.events == []


def test_probing_helpers_never_heal(demo):
    page, dom = demo.build({(CSS, '[data-test="login-button"]'): demo.dom_kit.Element()})
    page._healer = _healer(dom)
    assert page.is_visible(demo.Page.BUTTON) is False  # "is the original there?" is answered honestly
    assert page._healer.events == []


def test_pages_without_a_healer_behave_like_plain_selenium(demo):
    page, _ = demo.build({(CSS, '[data-test="login-button"]'): demo.dom_kit.Element()})
    with pytest.raises(demo.fake.TimeoutException):
        page.find(demo.Page.BUTTON)


# --- baseline store -----------------------------------------------------------------------------------------------------------
def test_store_round_trip_is_sorted_and_deterministic(tmp_path):
    path = tmp_path / "config" / "locators.json"
    store = FingerprintStore(path)
    store.merge({"B.two": PASSWORD_BOX, "A.one": LOGIN_BUTTON})
    store.save()
    first = path.read_text(encoding="utf-8")
    assert list(json.loads(first)["fingerprints"]) == ["A.one", "B.two"]
    reloaded = FingerprintStore.load(path)
    assert reloaded.get("A.one") == LOGIN_BUTTON and len(reloaded) == 2
    reloaded.save()
    assert path.read_text(encoding="utf-8") == first  # no noisy diffs when nothing changed


def test_missing_baseline_is_an_empty_store(tmp_path):
    assert len(FingerprintStore.load(tmp_path / "absent.json")) == 0


def test_corrupt_baseline_is_a_clear_configuration_error(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="bad.json"):
        FingerprintStore.load(path)


# --- transport (worker -> controller) ---------------------------------------------------------------------------------------------
def test_events_and_fingerprints_survive_the_trip_through_user_properties(dom_kit):
    healer = _healer(dom_kit.Dom(), record=False)
    healer.heal(Page.BUTTON, "https://shop.example/login")
    recorder = LocatorHealer([], FingerprintStore(None), FakeReader(), record=True)
    recorder.record(Page.BUTTON, object())
    props = export_properties(healer) + export_properties(recorder)
    assert parse_heals(props)[0].locator == "Page.BUTTON"
    assert parse_fingerprints(props) == {"Page.BUTTON": LOGIN_BUTTON}


def test_a_healer_that_did_nothing_exports_nothing():
    assert export_properties(LocatorHealer([], FingerprintStore(None))) == []


# --- controller plugin ----------------------------------------------------------------------------------------------------------------
def _report(nodeid, healer):
    return types.SimpleNamespace(nodeid=nodeid, user_properties=export_properties(healer))


def _healed_report(dom_kit, nodeid="tests/ui/test_login.py::test_ok"):
    healer = _healer(dom_kit.Dom())
    healer.heal(Page.BUTTON, "https://shop.example/login")
    return _report(nodeid, healer)


def _settings(tmp_path, **env):
    return load_settings(environ={"REPORTS_DIR": str(tmp_path / "reports"), **env})


def test_collector_writes_an_audit_file_and_leaves_a_green_exit_code_alone(tmp_path, dom_kit):
    collector = HealingCollector(_settings(tmp_path))
    collector.pytest_runtest_logreport(_healed_report(dom_kit))
    session = types.SimpleNamespace(exitstatus=pytest.ExitCode.OK)
    collector.pytest_sessionfinish(session)
    audit = json.loads((tmp_path / "reports" / "locator_healing.json").read_text(encoding="utf-8"))
    assert audit["tests/ui/test_login.py::test_ok"][0]["healed"] == f"{CSS}=#signin-btn"
    assert session.exitstatus == pytest.ExitCode.OK


def test_fail_on_heal_turns_a_green_run_into_a_failed_one(tmp_path, dom_kit):
    collector = HealingCollector(_settings(tmp_path, FAIL_ON_HEAL="true"))
    collector.pytest_runtest_logreport(_healed_report(dom_kit))
    session = types.SimpleNamespace(exitstatus=pytest.ExitCode.OK)
    collector.pytest_sessionfinish(session)
    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED


def test_fail_on_heal_does_nothing_when_nothing_healed(tmp_path):
    collector = HealingCollector(_settings(tmp_path, FAIL_ON_HEAL="true"))
    session = types.SimpleNamespace(exitstatus=pytest.ExitCode.OK)
    collector.pytest_sessionfinish(session)
    assert session.exitstatus == pytest.ExitCode.OK
    assert not (tmp_path / "reports" / "locator_healing.json").exists()


def test_record_mode_merges_fingerprints_into_the_baseline_file(tmp_path):
    baseline = tmp_path / "locators.json"
    FingerprintStore(baseline, {"Old.kept": PASSWORD_BOX}).save()
    settings = _settings(tmp_path, RECORD_LOCATORS="true", LOCATOR_BASELINE=str(baseline))
    recorder = LocatorHealer([], FingerprintStore(None), FakeReader(), record=True)
    recorder.record(Page.BUTTON, object())
    collector = HealingCollector(settings)
    collector.pytest_runtest_logreport(_report("t::a", recorder))
    collector.pytest_sessionfinish(types.SimpleNamespace(exitstatus=pytest.ExitCode.OK))
    saved = FingerprintStore.load(baseline)
    assert saved.get("Page.BUTTON") == LOGIN_BUTTON and saved.get("Old.kept") == PASSWORD_BOX


def test_baseline_is_not_touched_outside_record_mode(tmp_path):
    baseline = tmp_path / "locators.json"
    recorder = LocatorHealer([], FingerprintStore(None), FakeReader(), record=True)
    recorder.record(Page.BUTTON, object())
    collector = HealingCollector(_settings(tmp_path, LOCATOR_BASELINE=str(baseline)))
    collector.pytest_runtest_logreport(_report("t::a", recorder))
    collector.pytest_sessionfinish(types.SimpleNamespace(exitstatus=pytest.ExitCode.OK))
    assert not baseline.exists()


def test_terminal_summary_lists_every_heal(tmp_path, dom_kit):
    collector = HealingCollector(_settings(tmp_path))
    collector.pytest_runtest_logreport(_healed_report(dom_kit))
    lines: list[str] = []
    terminal = types.SimpleNamespace(section=lines.append, write_line=lines.append)
    collector.pytest_terminal_summary(terminal)
    assert any("Page.BUTTON" in line and "#signin-btn" in line for line in lines)


# --- settings ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("env", [{"HEAL_THRESHOLD": "0"}, {"HEAL_THRESHOLD": "1.5"}, {"HEAL_MARGIN": "-0.1"}, {"HEAL_AFTER": "-1"}])
def test_invalid_healing_settings_are_rejected(env):
    with pytest.raises(ConfigurationError, match="Healing"):
        load_settings(environ=env)


def test_healing_defaults_are_conservative():
    s = load_settings(environ={})
    assert (s.locator_healing, s.heal_threshold, s.record_locators, s.fail_on_heal) == (True, 0.8, False, False)
    assert s.locator_baseline_path.name == "locator_fingerprints.json" and s.locator_baseline_path.is_absolute()


# --- management report -------------------------------------------------------------------------------------------------------------------
def _healed_summary(dom_kit):
    events = tuple(e.to_dict() for e in parse_heals(_healed_report(dom_kit).user_properties))
    results = [CaseResult("tests/ui/t.py::test_a", "ui", "passed", 0.2, heals=events), CaseResult("tests/ui/t.py::test_b", "ui", "passed")]
    return RunSummary(RunMetadata(product="Shop", build_number="9", started_at="2026-10-26 10:00"), results)


def test_report_lists_healed_locators_for_review(tmp_path, dom_kit):
    summary = _healed_summary(dom_kit)
    html_text, md_text = render_html(summary, [], tmp_path), render_markdown(summary)
    assert "Locators healed automatically" in html_text and "#signin-btn" in html_text and "Locators healed" in html_text
    assert "Page.BUTTON" in md_text and "update these selectors" in md_text
    data = json.loads(write_reports(summary, tmp_path)["json"].read_text(encoding="utf-8"))
    assert data["locator_heals"][0]["strategy"] == "fingerprint"


def test_report_without_heals_has_no_healing_section(tmp_path):
    summary = RunSummary(RunMetadata(), [CaseResult("tests/ui/t.py::a", "ui", "passed")])
    assert "healed automatically" not in render_html(summary, [], tmp_path)
