<!-- Author: Anil Kalisetti -->
# Changelog

Every change to the framework adds an entry here and updates the README (a unit test fails if a new
command-line option or setting is not documented). Newest first.

## 2026-10-26 - Documentation
* Added [docs/USER_GUIDE.md](docs/USER_GUIDE.md) (task-oriented) and [docs/CAPABILITIES.md](docs/CAPABILITIES.md)
  (what exists, where, how far verified).
* README rewritten as an index; `.env.example` lists the healing and reporting settings.
* Added `tests/unit/test_documentation.py` so options, settings, make targets and links cannot drift from the docs.

## 2026-10-26 - Self-healing locators
* `Locator` objects with `fallbacks` and `heal=False`; fingerprint matching with threshold and ambiguity guards.
* Committed baseline `config/locator_fingerprints.json`; `--record-locators`, `--no-healing`, `--fail-on-heal`.
* "Locators healed automatically" in the management report; `reports/locator_healing.json`.
* Docs: [SELF_HEALING.md](docs/SELF_HEALING.md). LLM healing is a documented placeholder only.

## 2026-10-26 - Parallel runs, tags, multi-browser, OOP
* Per-worker SQLite and log files; `--dist=loadgroup` and `xdist_group`.
* `--tags`, `--list-tags`; `uat` and `e2e` tags; report breakdown by tag and by browser.
* `--ui-browsers chrome,firefox|all`; Safari support; browser and execution-target class hierarchies.
* Report renderers, API service classes, scenario repository base class, abstract `BasePage`.
* Docs: [RUNNING.md](docs/RUNNING.md).

## 2026-10-26 - Initial release
* UI, API, database and ETL suites; executive report; Jira integration; coverage and screenshots.
* Docker, local Grid, cloud-grid targets, and CI pipelines for four systems.
* Docs: ARCHITECTURE, FRAMEWORK_COMPARISON, LIMITATIONS.
