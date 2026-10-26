<!-- Author: Anil Kalisetti -->
# User guide

Task-oriented: find what you want to do, copy the command or the pattern. For *what the framework
can do*, see [CAPABILITIES.md](CAPABILITIES.md); for *how it is built*, see [ARCHITECTURE.md](ARCHITECTURE.md).

> **Status.** Offline layers are verified; live layers (real browser, public APIs, cloud grids, Jira)
> have not been run yet. See [LIMITATIONS.md](LIMITATIONS.md) and expect to adjust a selector or an
> assertion on your first live run.

## Contents
1. [Install and first run](#1-install-and-first-run)
2. [Configuration](#2-configuration)
3. [Choosing which tests run](#3-choosing-which-tests-run)
4. [Writing UI tests](#4-writing-ui-tests)
5. [Self-healing locators](#5-self-healing-locators)
6. [Writing API tests](#6-writing-api-tests)
7. [Database-driven tests](#7-database-driven-tests)
8. [Data migration / ETL validation](#8-data-migration--etl-validation)
9. [Running on Grid, Sauce Labs, BrowserStack, LambdaTest](#9-running-on-grid-sauce-labs-browserstack-lambdatest)
10. [Reports: what you get and how to read them](#10-reports)
11. [Jira defects](#11-jira-defects)
12. [CI/CD](#12-cicd)
13. [Docker](#13-docker)
14. [Troubleshooting](#14-troubleshooting)
15. [Glossary](#15-glossary)

---

## 1. Install and first run

Requirements: Python 3.10+, `make` (optional), Chrome (for UI tests), internet (for API/UI sample tests).

```bash
git clone https://github.com/codewithme30/pytest-framework.git && cd pytest-framework
make install            # creates .venv and installs requirements.txt
make unit data db       # offline checks, no browser or internet needed (start here)
make smoke              # fast business-critical checks across UI, API, DB
make report             # opens reports/executive_summary.html
```

Without `make`: `python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pytest -m "unit or data or db"`.

For contributors: `make install-dev` adds ruff, mypy and a pre-commit hook; `make lint typecheck` must be clean.

## 2. Configuration

Precedence (highest wins): **command-line flag > environment variable / `.env` > `config/environments/<env>.yaml` > default**.

* Copy `.env.example` to `.env` for local runs (never commit it).
* Pick an environment file with `--test-env staging` (or `TEST_ENV=staging`); copy `config/environments/qa.yaml` to add one.
* **Secrets** (access keys, tokens) come from environment variables only; the loader rejects them in YAML.
* An unknown key in YAML is an error, so typos are caught on the first run.

Every setting is an environment variable named after the field in upper case (`HEADLESS`, `DB_URL`, ...):

| Setting (env var) | Default | Purpose / CLI flag |
|---|---|---|
| `TEST_ENV` | `qa` | environment file; `--test-env` |
| `PRODUCT_NAME` | Sample Retail Platform | shown in reports |
| `BASE_UI_URL` / `BASE_API_URL` / `HTTPBIN_URL` | SauceDemo / JSONPlaceholder / httpbingo | systems under test |
| `BROWSER` | `chrome` | `chrome`, `firefox`, `edge`, `safari`; `--ui-browser`, many: `--ui-browsers` |
| `HEADLESS` | `true` | `--headed` shows the window |
| `CHROME_BINARY` | empty | e.g. `/usr/bin/chromium` in Docker |
| `WINDOW_SIZE` | `1920,1080` | |
| `EXPLICIT_WAIT` / `PAGE_LOAD_TIMEOUT` | 10 / 30 s | UI waits |
| `EXECUTION_MODE` | `local` | `local`, `remote`, `saucelabs`, `browserstack`, `lambdatest`; `--execution-mode` |
| `GRID_URL` | empty | hub URL override; `--grid-url` |
| `GRID_USERNAME` / `GRID_ACCESS_KEY` | empty | or `SAUCE_*`, `BROWSERSTACK_*`, `LT_*` |
| `PLATFORM_NAME` / `BROWSER_VERSION` | Windows 11 / latest | cloud capabilities |
| `BUILD_NAME` | CI build id | label in cloud dashboards; `--build-name` |
| `LOCATOR_HEALING` | `true` | `--no-healing` to disable |
| `HEAL_THRESHOLD` / `HEAL_MARGIN` / `HEAL_AFTER` | 0.8 / 0.1 / 3 s | healing sensitivity |
| `LOCATOR_BASELINE` | `config/locator_fingerprints.json` | fingerprint file |
| `RECORD_LOCATORS` / `FAIL_ON_HEAL` | `false` | `--record-locators` / `--fail-on-heal` |
| `API_TIMEOUT` / `API_RETRIES` | 15 s / 3 | API client |
| `DB_URL` | `sqlite:///reports/sample_test.db` | any SQLAlchemy URL |
| `SEED_SAMPLE_DB` | `true` | reset the sample table each session; set `false` for a real DB |
| `ETL_SOURCE_DB_URL` / `ETL_TARGET_DB_URL` | empty | placeholders for real source/target systems |
| `JIRA_ENABLED`, `JIRA_BASE_URL`, `JIRA_USER_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, `JIRA_ISSUE_TYPE`, `JIRA_LABELS` | off | see [section 11](#11-jira-defects) |
| `REPORTS_DIR` | `reports` | output folder |
| `SCREENSHOT_POLICY` | `on_failure` | `on_failure`, `always`, `never`; `--screenshots` |
| `PASS_RATE_GREEN` / `PASS_RATE_AMBER` | 95 / 80 | verdict thresholds |

## 3. Choosing which tests run

Tests are grouped with **tags** (pytest markers):

| Tag | Use it for | Typical pipeline stage |
|---|---|---|
| `smoke` | fast, business-critical | every commit |
| `sanity` | narrow checks after a deploy | post-deploy |
| `regression` | full functional coverage | nightly |
| `uat` | business sign-off scenarios | pre-release |
| `e2e` | complete customer journeys | nightly / pre-release |
| `critical` | a failure forces the build RED | any |
| `slow`, `network`, `known_defect(key)` | long-running / needs internet / already tracked | filters |
| `ui`, `api`, `db`, `data`, `etl`, `unit` | layer; applied automatically from the folder | filters |

```bash
pytest --tags smoke                      # typo-safe: --tags smok is an error
pytest --tags "smoke or uat" -n auto     # in parallel, one worker per core
pytest --tags "regression and not slow"
pytest -m "api and smoke"                # plain pytest -m also works
pytest --list-tags                       # how many tests carry each tag
pytest tests/api/test_posts_crud.py::test_get_post_by_id   # one test
make tag TAGS="uat"        make parallel TAGS="smoke or uat" WORKERS=4
```

**Parallel:** `-n auto` or `-n 4`. Each worker gets its own SQLite copy and log file; keep order-dependent
tests together with `@pytest.mark.xdist_group("name")`. **Many browsers:** `--ui-browsers chrome,firefox`
(or `all`) runs every UI test once per browser, ids become `test_login[firefox]`.
Details: [RUNNING.md](RUNNING.md).

## 4. Writing UI tests

Pattern: **page object** (locators and business actions) + **test** (what should be true).

```python
# framework/ui/pages/profile_page.py
from framework.ui.base_page import BasePage, css

class ProfilePage(BasePage):
    DISPLAY_NAME = css('[data-test="display-name"]', fallbacks=["#displayName"])   # fallbacks: see section 5
    SAVE = css('[data-test="save"]')

    def is_loaded(self) -> bool:                  # REQUIRED: every page can recognise itself
        return self.is_visible(self.DISPLAY_NAME)

    def rename_to(self, name: str) -> None:       # a business action, not "type into field"
        self.type_text(self.DISPLAY_NAME, name)
        self.click(self.SAVE)
```
```python
# tests/ui/test_profile.py
import pytest

@pytest.mark.regression
def test_customer_can_rename_profile(inventory_page, driver, settings, healer):
    page = ProfilePage(driver, settings.explicit_wait, healer)   # pass `healer` to enable self-healing
    page.rename_to("Priya Nair")
    assert page.text_of(ProfilePage.DISPLAY_NAME) == "Priya Nair"
```
Rules that keep suites stable: tests never touch selectors; all waiting is explicit and lives in `BasePage`
(`find`, `click`, `type_text`, `wait_for_url_contains`...); use `is_visible` / `is_absent` for checks that
something is (not) there; one fresh browser per test, so tests never share a cart or cookies.
Fixtures: `driver`, `browser_name`, `healer`, `login_page`, `inventory_page`, `cart_page`, `checkout_page`,
`users`, `products` (see `tests/ui/conftest.py`). A new page fixture is three lines there.

## 5. Self-healing locators

If a selector stops matching, the framework tries your declared `fallbacks`, then the closest look-alike to a
stored fingerprint, and **reports** the repair. It will not guess: low similarity or two near-identical
candidates means the test fails normally. Money-moving actions: `css("#pay", heal=False)`.

```bash
make record-locators                       # once, on a KNOWN-GOOD build; commit the diff
pytest --tags smoke                        # healing is on by default
pytest --tags smoke --fail-on-heal         # release gate: any heal fails the run
pytest --no-healing                        # plain Selenium behaviour
```
Review heals in the management report ("Locators healed automatically") or `reports/locator_healing.json`,
then fix the selector in the page class. Full details and limits: [SELF_HEALING.md](SELF_HEALING.md).

## 6. Writing API tests

Use a **service class** per resource (one place for URLs and verbs) and the assertion helpers:

```python
# tests/api/test_posts_by_user.py
import pytest
from framework.api.assertions import array_of, assert_json_schema, assert_status

pytestmark = pytest.mark.network

@pytest.mark.smoke
def test_filter_by_user_returns_only_that_users_posts(posts_api, schemas):
    response = posts_api.list(userId=3)
    assert_status(response, 200)
    assert_json_schema(response.json(), array_of(schemas["post"]))
    assert {p["userId"] for p in response.json()} == {3}
```
Available service fixtures: `posts_api`, `comments_api`, `users_api`, `todos_api`, `albums_api`, `photos_api`;
raw client fixtures `api_client`, `httpbin` and a factory `new_client(base_url, ...)` for tests that change
auth or headers. Assertion helpers: `assert_status`, `assert_json_schema`, `assert_response_time`,
`assert_header_contains`, `assert_json_subset`, `array_of`. Schemas live in `tests/api/schemas/*.json`.

**Add your own API:**
```python
# framework/api/services.py
class OrdersService(ResourceService):
    resource = "orders"                                   # gives list/get/create/replace/update/delete
    def cancel(self, order_id):                           # then add business-specific calls
        return self._client.post(self._path(order_id, "cancel"))
```
Set `BASE_API_URL`, add a fixture next to `posts_api` in `tests/api/conftest.py`. The client retries only
idempotent verbs (GET/HEAD/PUT/DELETE), never POST, logs every call and redacts secrets. Token auth:
`ApiClient.set_bearer_token(...)`; OAuth2 helper is a documented placeholder in `framework/api/auth.py`.

## 7. Database-driven tests

Real-life pattern: analysts keep scenarios in a table; tests pull rows marked `NEW`, run them, and write the
result back to the same row.

```python
from framework.db.repository import ScenarioRepository

class LoanCaseRepository(ScenarioRepository):
    table = "loan_cases"          # needs columns: id, status, actual_total, error_message, executed_at

# in a test:  repo.fetch_cases()  ->  run  ->  repo.record_result(case["id"], passed, actual="1000.00")
```
Worked example: `tests/db/test_db_driven_tax.py` (one pytest test per database row, results written back, even
when the assertion fails). Fixtures: `db` (configured DB), `repo`, `scratch_db` (private in-memory DB). Point at
a real database with `DB_URL=postgresql+psycopg2://user:***@host/db` and `SEED_SAMPLE_DB=false`.
`DatabaseClient` offers `fetch_all`, `fetch_one`, `scalar`, `stream`, `execute`, `execute_many`, `transaction`,
`table_exists`, `columns`, `row_count`; always bind values (`:name`), never format SQL strings. Under `-n`,
SQLite files are per worker; for a shared server database partition the rows per worker.

## 8. Data migration / ETL validation

Real-life scenario (the sample): a retailer moves a legacy CRM into a warehouse. `ETLValidator` compares
source and target and names the exact problem.

```python
validator.row_count("legacy_customers", "dim_customer", expected_rejects=2).assert_passed()
validator.schema_match("legacy_customers", "dim_customer", {"cust_id": "customer_id"}).assert_passed()
validator.null_check("dim_customer", ["customer_id", "email"]).assert_passed()
validator.duplicate_check("dim_customer", ["email"]).assert_passed()
validator.orphan_check("fact_order", "customer_id", "dim_customer", "customer_id").assert_passed()
validator.aggregate_check("legacy_orders", "SUM(amount_cents) / 100.0",     # same total on both sides,
                          "fact_order", "SUM(amount)", tolerance=Decimal("0.005"))   # to the cent
validator.dataset_diff(                             # every row and column, streamed
    "SELECT * FROM legacy_customers ORDER BY cust_id",
    "SELECT * FROM dim_customer ORDER BY customer_id",
    source_key="cust_id", target_key="customer_id",
    transform=expected_row_for,                     # source row -> expected target row (business rules)
    ignore_keys=rejected_ids,                       # rows legitimately not migrated
).assert_passed()
```
`dataset_diff` reports missing rows, unexpected rows, column mismatches (with both values) and duplicate keys,
using memory proportional to a chunk, not the table. Use `ETL_SOURCE_DB_URL` / `ETL_TARGET_DB_URL` for real
systems (placeholders). Worked examples: `tests/data/` (about 40 edge cases: unicode names, leap days,
duplicate emails, orphan orders, rejected rows, idempotent re-run, 20k-row volume marked `slow`).
`tests/data/test_etl_validator.py` proves each check *fails* when data is corrupted ("test the tests").

## 9. Running on Grid, Sauce Labs, BrowserStack, LambdaTest

The test code does not change; configuration chooses **what** browser and **where**.

| Target | Set | Notes |
|---|---|---|
| This machine | `EXECUTION_MODE=local` | Selenium Manager downloads the driver |
| Your Selenium Grid | `EXECUTION_MODE=remote`, `GRID_URL=http://grid:4444/wd/hub` | `docker compose up` gives you one locally |
| Sauce Labs | `EXECUTION_MODE=saucelabs`, `SAUCE_USERNAME`, `SAUCE_ACCESS_KEY` | region hub: override with `GRID_URL` |
| BrowserStack | `EXECUTION_MODE=browserstack`, `BROWSERSTACK_USERNAME`, `BROWSERSTACK_ACCESS_KEY` | |
| LambdaTest | `EXECUTION_MODE=lambdatest`, `LT_USERNAME`, `LT_ACCESS_KEY` | |

```bash
pytest -m ui --execution-mode saucelabs --ui-browsers chrome,firefox -n 4 --build-name release-24.3
```
Platform and version come from `PLATFORM_NAME` / `BROWSER_VERSION` (Safari needs a macOS platform). After each
test the session is marked passed/failed on the vendor dashboard. Missing credentials stop the run before any
paid session starts. A device/OS matrix file is a documented placeholder in `framework/ui/targets.py`.

## 10. Reports

Every run writes to `reports/`:

| File | Audience | Content |
|---|---|---|
| `executive_summary.html` | managers, product owners | verdict, KPIs, results by area/tag/browser, healed locators, failures with evidence, trend, slowest tests |
| `summary.md` | CI job summary, chat | the same in Markdown (GitHub Actions publishes it to the run page) |
| `summary.json` | dashboards, automation | machine readable |
| `report.html` | testers | pytest-html with logs and screenshots |
| `junit.xml` | CI test tabs | JUnit |
| `allure-results/` | Allure users | `make allure` (needs the Allure CLI) |
| `coverage-html/`, `coverage.xml` | developers | line/branch coverage of `framework/` |
| `logs/pytest-<worker>.log` | debugging | one log per worker |
| `jira_defects_preview.json`, `locator_healing.json`, `history.json` | as named | dry-run defects, heals, pass-rate trend |

**Reading the verdict:** pass rate = passed / (passed + failed). **GREEN** >= 95 % and no failed `critical`
test; **AMBER** >= 80 %; **RED** below, or any failed `critical` test. Skipped and expected-failure tests never
change the rate. "Flaky" lists tests that passed only after a retry: they pass the build but hide instability.
Screenshots (and page source) are captured on failure by default (`SCREENSHOT_POLICY`).

## 11. Jira defects

```bash
pytest --raise-jira-defects        # dry run unless JIRA_* variables are set
```
Dry run writes `reports/jira_defects_preview.json`. For real bugs set `JIRA_BASE_URL`, `JIRA_USER_EMAIL`,
`JIRA_API_TOKEN` (an Atlassian API token), `JIRA_PROJECT_KEY`. One defect per failing test, de-duplicated by a
fingerprint label (a still-open bug gets a comment instead); screenshot attached; created defects appear in the
executive report. Guards: `--jira-max-defects 25` caps a bad run (environment outage); mark a failure you
already track with `@pytest.mark.known_defect("QA-123")` so no new bug is raised.

## 12. CI/CD

Ready pipelines: `.github/workflows/ci.yml`, `Jenkinsfile`, `.gitlab-ci.yml`, `azure-pipelines.yml`. All run the
same commands: lint and typecheck, **offline tests on every PR**, API tests, UI tests nightly or on demand with
inputs for tags, browsers and execution mode; artifacts and the management summary are published. Add secrets
in your CI (`SAUCE_USERNAME`, `SAUCE_ACCESS_KEY`, `JIRA_API_TOKEN`, ...); the files list the names. A build runs
anywhere with: `pip install -r requirements.txt && pytest --tags "<expression>" -n auto`.
Persisting the trend across CI runs needs `reports/history.json` to be cached or archived (placeholder in
`write_reports`).

## 13. Docker

```bash
make docker-build                                   # image with Python, Chromium, dependencies
docker run --rm -v "$PWD/reports:/app/reports" pytest-framework -m "not ui"
make docker-test                                    # tests + a Selenium Grid container; watch at http://localhost:7900
```

## 14. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `Unknown key 'x' in qa.yaml` | typo in a YAML setting; keys equal the setting names in section 2 |
| `... requires credentials` (cloud mode) | set the provider's username/access-key variables; nothing was started |
| `EXECUTION_MODE=remote requires GRID_URL` | set `GRID_URL` |
| `--tags: unknown tag(s) smok` | typo; run `pytest --list-tags` or see `markers` in `pyproject.toml` |
| "... not found in `markers` configuration option" | register new markers in `pyproject.toml` (`--strict-markers` is on) |
| UI test times out finding an element | selector changed (check "Locators healed" / failure screenshot); fix the page class or record a new baseline |
| Chrome crashes in a container | the framework already adds `--no-sandbox` and `--disable-dev-shm-usage`; set `CHROME_BINARY` (the Dockerfile does) and give the container enough shared memory (`shm_size`) |
| API test fails with a 5xx or timeout | the public sample API was down; re-run (`--reruns 2`) or point `BASE_API_URL` to your own |
| "database is locked" | do not point several workers at one SQLite file; the sample uses a file per worker |
| Reports folder is empty after a crash | reports are written at the end of the run; see `reports/logs/` |
| Parallel run fails but serial passes | tests share state; isolate data or group with `xdist_group` |

## 15. Glossary

**Marker / tag** a label on a test used to select it. **Fixture** setup code a test receives by parameter name.
**Page object** a class that hides a screen's selectors behind business actions. **Execution target** where a
browser runs (local, Grid, cloud). **xdist worker** one parallel test process. **Fingerprint** a stored
description of an element used by self-healing. **Heal** a runtime repair of a broken locator.
**Baseline** the committed file of fingerprints. **ETL** extract-transform-load: moving data between systems.
**Verdict** GREEN / AMBER / RED build health in the executive report.
