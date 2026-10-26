<!-- Author: Anil Kalisetti -->
# Framework capabilities

What the framework can do today, where it lives, and how far it has been proven.

**Status legend**
* **Verified** - exercised by automated tests that ran offline (no browser, no internet).
* **Not run live** - written carefully, but not yet run against the real service/browser. Expect small fixes.
* **Placeholder** - a documented extension point; deliberately not implemented.

Not included at all (Appium, visual regression, load testing, BDD...): see [LIMITATIONS.md](LIMITATIONS.md).

## Test execution

| Capability | Detail | Where | Status |
|---|---|---|---|
| Layered suites | UI, API, database, ETL/data, framework self-tests | `tests/{ui,api,db,data,unit}` | Verified (db, data, unit); Not run live (ui, api) |
| Tag grouping | `smoke sanity regression uat e2e critical` + layer tags; `--tags`, `--list-tags` (typo-safe) | `framework/core/tags.py`, `plugins/tags_plugin.py` | Verified (logic); hooks Not run live |
| Parallel execution | xdist `-n`, `xdist_group`, per-worker SQLite and log files | `framework/core/parallel.py`, `conftest.py` | Verified (logic); Not run live under `-n` |
| Retry and timeout | rerunfailures (`--reruns`), per-test timeout 180 s | `pyproject.toml` | Not run live |
| Soft assertions, mocking | pytest-check, pytest-mock available | `requirements.txt` | Available |
| Strict config | `--strict-markers`, `--strict-config` | `pyproject.toml` | Verified |

## UI automation

| Capability | Detail | Where | Status |
|---|---|---|---|
| Page Objects | abstract `BasePage`, explicit bounded waits, business actions | `framework/ui/base_page.py`, `pages/` | Verified (contract, fake Selenium); Not run live |
| Multi-browser | Chrome, Edge, Firefox, Safari classes; `--ui-browsers chrome,firefox` or `all` | `framework/ui/browsers.py`, `tests/ui/conftest.py` | Verified (options, fan-out logic) |
| Execution targets | local, any Selenium Grid, Sauce Labs, BrowserStack, LambdaTest (URL + auth placeholders) | `framework/ui/targets.py` | Verified (capabilities); Not run live |
| Cloud pass/fail status | marks the vendor session passed/failed | `targets.py` | Verified (scripts); Not run live |
| Self-healing locators | declared fallbacks + fingerprint matching, threshold + ambiguity guards, audit trail, `--fail-on-heal` | `framework/ui/healing/` | Verified (logic, JS under Node); Not run in a real browser |
| LLM-assisted healing | where it would plug in and the conditions | `healing/strategies.py::LlmStrategy` | Placeholder |
| Screenshots and page source | on failure / always / never | `framework/ui/screenshot.py`, `plugins/evidence_plugin.py` | Not run live |

## API testing

| Capability | Detail | Where | Status |
|---|---|---|---|
| HTTP client | session reuse, retries on idempotent verbs only, timeouts, redaction, Allure attachments | `framework/api/client.py` | Verified (stub server) |
| Service classes | one class per REST resource (CRUD + nested routes) | `framework/api/services.py` | Verified (stub server) |
| Assertions | status, JSON Schema, subset, header, response time | `framework/api/assertions.py` | Verified |
| Public-API suites | JSONPlaceholder (posts, users, comments, todos, albums, photos), httpbingo (status codes, every method, auth, redirects, cookies, gzip, uploads, latency and timeouts) | `tests/api/` | Not run live |
| Auth | bearer and basic helpers; OAuth2 | `client.py`, `auth.py` | Bearer/basic Verified; OAuth2 Placeholder |

## Data and database

| Capability | Detail | Where | Status |
|---|---|---|---|
| Database client | SQLAlchemy, bound parameters, identifier validation, streaming, transactions | `framework/db/client.py` | Verified with a SQLite stand-in; SQLAlchemy Not run live |
| Data-driven from DB, write results back | scenarios in a table, status/actual/error/time written to the row | `framework/db/repository.py`, `tests/db/` | Verified (stand-in) |
| Repository base class | `ScenarioRepository` + one subclass per table | `repository.py` | Verified |
| ETL / migration validation | row count, schema, null, duplicate, orphan, aggregate, streaming full-row diff with transform and ignore list | `framework/data/etl_validator.py` | Verified |
| Migration edge cases | unicode, leap days, duplicate emails, orphans, rejects, idempotent re-run, 20k-row volume | `tests/data/` | Verified |
| "Tests for the tests" | validator is shown to fail on every corruption type | `tests/data/test_etl_validator.py` | Verified |
| Real source/target systems | `ETL_SOURCE_DB_URL`, `ETL_TARGET_DB_URL` | settings | Placeholder |

## Reporting and integrations

| Capability | Detail | Where | Status |
|---|---|---|---|
| Executive report | GREEN/AMBER/RED verdict, KPIs, by area/tag/browser, healed locators, failures with evidence, trend, slowest, flaky | `framework/reporting/` | Verified (rendering and rules) |
| Report formats | HTML, Markdown, JSON (pluggable `ReportRenderer` classes) | `executive_report.py` | Verified |
| Choose your reports | `REPORTS` / `--reports` picks any of executive, html, junit, allure, coverage (or all / none); `--list-reports`; typo-safe; missing plugin skipped with a note | `framework/reporting/outputs.py`, `plugins/report_selection_plugin.py` | Verified (selection logic); Not run live under real pytest |
| Technical reports | pytest-html, JUnit XML, Allure results | `outputs.py` | Not run live (Allure HTML needs its CLI) |
| Code coverage | line + branch of `framework/`, terminal + HTML + XML, shown in the summary | `framework/reporting/coverage_report.py` | Verified (logic with a stand-in); Not run live |
| Jira | one de-duplicated bug per failure, attachments, dry-run, safety cap, `known_defect` | `framework/integrations/jira_client.py`, `plugins/jira_plugin.py` | Verified (client against stub); Not run live |
| Trend across runs | `history.json` per workspace | `executive_report.py` | Verified; cross-run persistence Placeholder |
| CI metadata | GitHub Actions, Jenkins, GitLab, Azure DevOps detected for build info | `framework/core/ci_info.py` | Verified |

## Platform and delivery

| Capability | Detail | Where | Status |
|---|---|---|---|
| Layered configuration | CLI > env/.env > YAML > defaults, frozen settings, secrets from env only | `framework/config/` | Verified |
| Structured logging with masking | per-worker log files | `framework/core/logger.py`, `conftest.py` | Verified (masking) |
| Docker and local Grid | image with Chromium; compose with Selenium Grid + live view | `Dockerfile`, `docker-compose.yml` | Not run live |
| CI pipelines | GitHub Actions, Jenkins, GitLab CI, Azure DevOps | `.github/`, `Jenkinsfile`, `.gitlab-ci.yml`, `azure-pipelines.yml` | Not run live |
| Developer tooling | Makefile, ruff, mypy, pre-commit | `Makefile`, `pyproject.toml`, `.pre-commit-config.yaml` | Not run live |

## Design properties

* **Modular**: libraries under `framework/` know nothing about tests; tests know nothing about plumbing.
* **Object-oriented where it pays**: abstract bases and subclasses for browsers, execution targets, page
  objects, healing strategies, report renderers, API resources and scenario repositories; plain functions for
  pure logic. Map in [RUNNING.md](RUNNING.md#4-object-oriented-map).
* **Extensible by adding a class**: a browser, cloud vendor, report format, API resource, healing strategy or
  scenario table needs one new subclass; see the table in [ARCHITECTURE.md](ARCHITECTURE.md#extending).
* **Safe by default**: no secrets in files, parameterised SQL, healing and Jira have guards and dry-runs.
* **Fast and light**: streaming data comparison (constant memory), pushed-down aggregates, session reuse.
