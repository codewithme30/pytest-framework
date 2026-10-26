<!-- Author: Anil Kalisetti -->
# pytest-framework

A reference **PyTest** framework for QA automation: UI, API, database and ETL/data-migration
testing in one repo, with management-ready reporting, Jira defect creation, coverage,
screenshots, Docker, cloud grids (Sauce Labs / BrowserStack / LambdaTest) and CI pipelines
for GitHub Actions, Jenkins, GitLab and Azure DevOps.

> **Status, honestly.** The offline layers (unit, data/ETL, db, reporting, Jira client, settings)
> were exercised in a sandbox with no internet. The live layers (Selenium UI tests, the public
> API tests, cloud grids, real Jira) were written carefully but **not run against the real
> services**. Run `make smoke` once in your environment and expect to adjust a selector or
> an assertion. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Quick start

```bash
make install            # creates .venv, installs dependencies
make unit               # offline self-tests, seconds
make data db            # ETL + database tests, offline (in-memory SQLite)
make api                # API tests (needs internet)
make ui                 # browser tests (needs Chrome)
make regression         # everything except @slow, in parallel
make report             # open reports/executive_summary.html
```

No `make`? Use `pytest -m smoke -n auto` directly. All options are plain pytest options.

## What you get

| Concern | Where | Notes |
|---|---|---|
| Config | `framework/config`, `config/environments/*.yaml`, `.env` | CLI > env > YAML > defaults; secrets only from env |
| UI | `framework/ui`, `tests/ui` | Page Objects, Selenium 4 driver factory, SauceDemo examples |
| Browsers / targets | `framework/ui/browsers.py`, `targets.py` | one class per browser (Chrome, Firefox, Edge, Safari) and per place to run (local, Grid, Sauce Labs, BrowserStack, LambdaTest) |
| Cloud grids | `framework/ui/targets.py` | `--execution-mode saucelabs\|browserstack\|lambdatest\|remote`; URL + auth are placeholders in `.env` |
| API | `framework/api`, `tests/api` | Retrying client, one service class per resource, JSON-schema checks; JSONPlaceholder + httpbingo |
| Database | `framework/db`, `tests/db` | Fetch test data from a DB, run it, write results back |
| ETL / migration | `framework/data`, `tests/data` | Source-vs-target: counts, schema, nulls, duplicates, orphans, aggregates, full row diff, ~40 edge cases |
| Reporting | `framework/reporting` | Self-contained HTML + Markdown + JSON, GREEN/AMBER/RED verdict, trend history |
| Other reports | pytest-html, JUnit XML, Allure results, coverage HTML/XML | produced on every run |
| Jira | `framework/integrations/jira_client.py` | De-duplicated defects, dry-run by default |
| Screenshots | `framework/ui/screenshot.py` | On failure (configurable), attached to every report |
| Parallel / retry | xdist, rerunfailures, timeout | xdist-safe plugins |
| CI/CD | `.github/workflows`, `Jenkinsfile`, `.gitlab-ci.yml`, `azure-pipelines.yml` | Same `pytest` commands everywhere |

## Parallel, tags and browsers

```bash
pytest -n auto --tags "smoke or uat"                  # parallel, grouped by tag
pytest -m ui --ui-browsers chrome,firefox -n 4        # every UI test on two browsers, 4 workers
pytest --list-tags                                    # tests per tag
```
Details, safety rules for parallel runs and the OOP map: [docs/RUNNING.md](docs/RUNNING.md).

## Run it your way

```bash
pytest -m smoke                                   # by marker
pytest tests/api -n 4                             # a folder, 4 workers
pytest --test-env staging                         # another environment file
pytest -m ui --ui-browser chrome --headed         # watch the browser
pytest -m ui --execution-mode saucelabs           # cloud (set SAUCE_USERNAME / SAUCE_ACCESS_KEY)
pytest -m "not slow" --raise-jira-defects         # create Jira bugs (see below)
docker compose up --build --abort-on-container-exit --exit-code-from tests   # local Selenium Grid
```

### Cloud platforms (placeholders to fill)

Copy `.env.example` to `.env` and set:

| Platform | Variables |
|---|---|
| Sauce Labs | `SAUCE_USERNAME`, `SAUCE_ACCESS_KEY`, optional `GRID_URL` (default region endpoint is used otherwise) |
| BrowserStack | `BROWSERSTACK_USERNAME`, `BROWSERSTACK_ACCESS_KEY` |
| LambdaTest | `LT_USERNAME`, `LT_ACCESS_KEY` |
| Any Selenium Grid | `EXECUTION_MODE=remote`, `GRID_URL` |

Keys are never read from YAML (the loader rejects them) and are masked in logs.

### Management report

After every run open `reports/executive_summary.html`. It shows the build verdict
(GREEN ≥ 95 % pass, AMBER ≥ 80 %, RED below, or any failed `@critical` test), results per
layer, failures with screenshots, slowest tests, coverage and the trend over previous runs.
The same content is in `reports/summary.md` (pasted into the GitHub job summary by CI) and
`reports/summary.json` (for dashboards).

### Jira defects

```bash
pytest --raise-jira-defects        # without JIRA_* env vars: DRY RUN, writes reports/jira_defects_preview.json
```
Set `JIRA_BASE_URL`, `JIRA_USER_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` to create real
bugs. A fingerprint label prevents duplicates (an open bug gets a comment instead),
`--jira-max-defects` caps a bad run, and `@pytest.mark.known_defect("ABC-123")` suppresses
re-raising a bug you already track.

## Project layout

```
framework/   reusable libraries (config, core, ui, api, db, data, integrations, reporting, plugins)
tests/       unit/ (framework self-tests)  ui/  api/  db/  data/
config/      environments/*.yaml
docs/        ARCHITECTURE.md  FRAMEWORK_COMPARISON.md  LIMITATIONS.md
```

## Writing your own tests

1. Pick the layer folder; the layer marker is applied automatically.
2. Add `@pytest.mark.smoke` / `regression` / `critical` as appropriate.
3. Use fixtures: `settings`, `api_client`, `driver`, `db`, `validator`, page-object fixtures.
4. Replace the sample app (`framework/sample_app`) and sample sites with yours.

Author: Anil Kalisetti · License: MIT
