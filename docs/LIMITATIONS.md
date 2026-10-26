<!-- Author: Anil Kalisetti -->
# What is verified, what is not, and what is deliberately left out

## Verification status

| Area | Status |
|---|---|
| Unit, data/ETL, db logic, reporting, Jira client, settings | Run offline in a sandbox using a minimal pytest-compatible runner (no internet, no pip). 298 of 299 passed, 1 skipped (needs Selenium). Mutation checks confirmed tests fail when logic is broken. |
| Real `pytest` plugin wiring (`conftest.py`, evidence/Jira/report plugins, xdist) | **Not run.** Written to documented pytest hooks; first real run may need small fixes. |
| SQLAlchemy-backed `DatabaseClient` | **Not run** (stdlib sqlite3 stand-in used). |
| Selenium UI tests, driver factory, cloud grids | **Not run.** SauceDemo selectors are from memory. |
| Public API tests (JSONPlaceholder, httpbingo) | **Not run.** A few expectations (`/bytes/0`, `x-total-count`, `/posts/abc`) are from memory. |
| Live Jira | **Not run**; request shapes follow Jira Cloud REST v3. |

Added later (parallel, tags, multi-browser, OOP refactor): the pure logic and class hierarchies
were verified offline (378 passed, 1 skipped) using a fake Selenium, and 7 deliberate bugs in the new
code were each caught by the tests. **Not run for real:** the `--tags`/`--list-tags` plugin hooks
under genuine pytest, `pytest_generate_tests` browser fan-out, per-worker DB/log files under a real
`pytest -n`, and the refactored page objects against a real browser. Also, `--dist=loadgroup` and
the per-worker log recipe follow the pytest-xdist documentation but have not been exercised here.

Self-healing locators: logic, guards, reporting and the browser-side JavaScript are verified offline (see
docs/SELF_HEALING.md). **Not run:** healing in a real browser, the `--record-locators` flow end to end, and
`--fail-on-heal` under real pytest. The committed baseline `config/locator_fingerprints.json` is empty until you
record it on a known-good build. Healed locators are not screenshotted (the failure screenshots still apply).

Selectable reports (`REPORTS` / `--reports`): parsing, option switching, missing-plugin handling and the coverage
writer are verified offline (with a stand-in for `coverage`). **Not run for real:** that html, junit and allure
pick up the options this plugin sets before they start (written against their documented option names), that
xdist workers inherit them, and pytest-cov's `--cov-report=` (empty = print nothing) plus reading its data file at
the end of the run. If a report is missing on your first run, `pytest --reports <type>` and the run header line
(`reports: ...`) tell you which side is at fault.

First step in your environment: `make install && make unit data db`, then `make smoke`.

## Not included, and why

| Feature | Reason / next step |
|---|---|
| Allure HTML generation | Results are produced; rendering needs the Allure CLI (a Java tool). `make allure` runs it if installed. |
| Mobile (Appium) | Needs devices/emulators and a different driver stack; the cloud capability layer is ready to extend. |
| Visual regression | Needs a baseline-image store and policy decisions (tolerance, ownership). |
| Performance / load | Belongs in Locust/k6; pytest is not a load generator. |
| Contract testing (Pact) | Needs a broker and provider pipelines. |
| BDD (pytest-bdd) | A style choice; adds a Gherkin layer many teams do not want. |
| Accessibility (axe-core) | Needs the axe script bundled or fetched; good next addition. |
| Playwright option | Selenium chosen because cloud vendors are Selenium-first; a Playwright driver could implement the same page-object interface. |
| Secrets manager (Vault, AWS SM) | Environment variables work with every CI; adapters are site-specific. |
| Persistent trend store | `history.json` is per workspace; CI needs a cache/artifact or database to persist it. |
| OAuth2/API-token auth | Placeholder in `framework/api/auth.py` with detailed TODO. |
| Non-SQLite DB drivers | SQLAlchemy supports them; install the driver and set `DB_URL`. |
| Test impact analysis, flaky-test quarantine DB | Needs historical storage across runs. |
