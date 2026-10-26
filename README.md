<!-- Author: Anil Kalisetti -->
# pytest-framework

A reference **PyTest** framework for QA automation. One repository covers **UI, API, database and ETL /
data-migration testing**, with management-ready reports, Jira defect creation, coverage, screenshots,
self-healing locators, parallel runs, multi-browser and cloud-grid execution (Sauce Labs, BrowserStack,
LambdaTest), Docker, and CI pipelines for GitHub Actions, Jenkins, GitLab and Azure DevOps.

> **Status, honestly.** Offline layers (unit, data/ETL, database, reporting, Jira client, settings, healing
> logic) are verified by automated tests. Live layers (real browser, public APIs, cloud grids, real Jira) were
> written carefully but **have not been run against the real services**. Run `make smoke` once in your
> environment and expect to adjust a selector or an assertion. Details: [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Documentation

| Read this | When you want to |
|---|---|
| [User guide](docs/USER_GUIDE.md) | install, configure, write UI/API/DB/ETL tests, run on cloud, read reports, troubleshoot |
| [Capabilities](docs/CAPABILITIES.md) | see everything the framework can do, where it lives and how far it is proven |
| [Running tests](docs/RUNNING.md) | run in parallel, group by tag, test on many browsers; the OOP map |
| [Self-healing locators](docs/SELF_HEALING.md) | understand and operate locator healing |
| [Architecture](docs/ARCHITECTURE.md) | understand the design rules and how to extend each part |
| [Limitations](docs/LIMITATIONS.md) | know what is verified, what is not, and what is deliberately left out |
| [Framework comparison](docs/FRAMEWORK_COMPARISON.md) | see how it ranks and the backlog of gaps |
| [Contributing](CONTRIBUTING.md) / [Changelog](CHANGELOG.md) | contribute; see what changed |

## Quick start

```bash
make install            # creates .venv, installs dependencies
make unit data db       # offline self-tests, ETL and database tests (seconds, no internet)
make smoke              # fast business-critical checks across UI, API, DB
make regression         # everything except @slow, in parallel
make report             # open reports/executive_summary.html
```
No `make`? `pytest -m smoke -n auto` works directly. `make help` lists every target.

## Capabilities at a glance

| Concern | What you get | More |
|---|---|---|
| UI | Page Objects, Selenium 4, **self-healing locators**, Chrome / Edge / Firefox / Safari, one browser per test | [guide §4-5](docs/USER_GUIDE.md#4-writing-ui-tests) |
| Where it runs | your machine, any Selenium Grid, Sauce Labs, BrowserStack, LambdaTest (URL + auth placeholders) | [guide §9](docs/USER_GUIDE.md#9-running-on-grid-sauce-labs-browserstack-lambdatest) |
| API | retrying client, one **service class per resource**, JSON-schema checks, JSONPlaceholder + httpbingo suites | [guide §6](docs/USER_GUIDE.md#6-writing-api-tests) |
| Database | read test data from a DB, execute, **write results back**; SQLAlchemy, bound parameters | [guide §7](docs/USER_GUIDE.md#7-database-driven-tests) |
| ETL / migration | row count, schema, nulls, duplicates, orphans, aggregates, **streaming full-row diff**, ~40 edge cases | [guide §8](docs/USER_GUIDE.md#8-data-migration--etl-validation) |
| Grouping | tags `smoke sanity regression uat e2e critical`, typo-safe `--tags`, `--list-tags` | [guide §3](docs/USER_GUIDE.md#3-choosing-which-tests-run) |
| Speed | parallel (`-n`), per-worker data and logs, retries, timeouts | [RUNNING](docs/RUNNING.md) |
| Reporting | **you choose** which of executive / html / junit / allure / coverage to generate (`REPORTS`, `--reports`); executive HTML/MD/JSON with **GREEN / AMBER / RED** verdict, by area / tag / browser, trend; pytest-html, JUnit, Allure results, coverage | [guide §10](docs/USER_GUIDE.md#10-reports) |
| Defects | Jira bugs per failure, de-duplicated, dry-run first, safety cap | [guide §11](docs/USER_GUIDE.md#11-jira-defects) |
| Delivery | Docker, local Grid via compose, four CI pipelines, Makefile, pre-commit | [guide §12-13](docs/USER_GUIDE.md#12-cicd) |

## Make targets

| Command | Does |
|---|---|
| `make install` / `make install-dev` | create `.venv` and install dependencies / also lint tooling and git hooks |
| `make lint` / `make format` / `make typecheck` | ruff check / auto-fix / mypy |
| `make unit` / `make data` / `make db` | offline framework self-tests / ETL tests / database tests |
| `make api` / `make ui` | API tests (internet) / browser tests (Chrome, or `MODE=saucelabs`) |
| `make smoke` / `make regression` / `make all` | smoke / everything except slow / everything |
| `make tag TAGS="uat"` / `make parallel TAGS="smoke or uat"` / `make tags` | run a tag group / in parallel / count tests per tag |
| `make browsers BROWSERS=chrome,firefox` | UI tests on several browsers |
| `make record-locators` | record the self-healing baseline |
| `make report` / `make allure` | open the management report / Allure report |
| `make docker-build` / `make docker-test` | build the image / run with a local Selenium Grid |
| `make clean` | remove reports and caches |

## Command cheat sheet

```bash
pytest --tags "smoke or uat" -n auto                  # group by tag, in parallel
pytest -m ui --ui-browsers chrome,firefox -n 4        # every UI test on two browsers
pytest --list-tags                                    # tests per tag
pytest --test-env staging                             # another environment file
pytest -m ui --headed --ui-browser firefox            # watch one browser
pytest -m ui --execution-mode saucelabs --build-name rel-24.3   # cloud (set SAUCE_USERNAME / SAUCE_ACCESS_KEY)
pytest --reports html,junit                       # choose the reports a run produces (default: all)
pytest --tags smoke --fail-on-heal                    # release gate: fail if any locator had to be healed
pytest --raise-jira-defects                           # Jira bugs (dry run until JIRA_* are set)
pytest --no-healing                                   # plain Selenium behaviour
make record-locators                                  # record the self-healing baseline (known-good build only)
docker compose up --build --abort-on-container-exit --exit-code-from tests   # tests + local Selenium Grid
```

| Option | Meaning |
|---|---|
| `--test-env NAME` | load `config/environments/NAME.yaml` |
| `--ui-browser B` / `--ui-browsers A,B` or `all` / `--headed` | browser(s); show the window |
| `--execution-mode M` / `--grid-url URL` / `--build-name N` | where UI tests run; hub URL; cloud build label |
| `--tags EXPR` / `--list-tags` | select by tag (validated) / count tests per tag |
| `--screenshots on_failure\|always\|never` | screenshot policy |
| `--reports TYPES` / `--list-reports` | choose reports: `executive,html,junit,allure,coverage`, `all`, `none` (or `REPORTS=...`) |
| `--no-healing` / `--record-locators` / `--fail-on-heal` | self-healing switches |
| `--raise-jira-defects` / `--jira-max-defects N` | Jira defect creation and its cap |

Settings and environment variables are listed in the [user guide](docs/USER_GUIDE.md#2-configuration);
precedence is CLI > environment/`.env` > `config/environments/*.yaml` > defaults, and secrets only ever come
from the environment.

## Cloud platforms (placeholders to fill)

Copy `.env.example` to `.env` and set:

| Platform | Variables |
|---|---|
| Sauce Labs | `SAUCE_USERNAME`, `SAUCE_ACCESS_KEY`, optional `GRID_URL` (default region endpoint otherwise) |
| BrowserStack | `BROWSERSTACK_USERNAME`, `BROWSERSTACK_ACCESS_KEY` |
| LambdaTest | `LT_USERNAME`, `LT_ACCESS_KEY` |
| Any Selenium Grid | `EXECUTION_MODE=remote`, `GRID_URL` |

## Management report

Choose what a run generates with `REPORTS` or `--reports` (`pytest --list-reports` shows the types); the default is all.

Open `reports/executive_summary.html` after any run. Verdict: **GREEN** >= 95 % pass with no failed `critical`
test, **AMBER** >= 80 %, **RED** below or any failed `critical` test. It also shows results by area, tag and
browser, locators that healed, failures with screenshots, flaky tests, coverage and the trend. The same content is
in `reports/summary.md` (published to the GitHub job summary by CI) and `reports/summary.json`.

## Project layout

```
framework/
  config/         layered settings (CLI > env > YAML > defaults)
  core/           logging, waits, data loading, tags, parallel helpers, CI detection
  ui/             base_page, browsers, targets, driver_factory, screenshot, pages/, healing/
  api/            client, services (one class per resource), assertions, auth placeholder
  db/             client, repository (read test data, write results back), sample data
  data/           ETL validator
  integrations/   Jira client
  reporting/      models and executive report renderers
  plugins/        pytest plugins: options, tags, evidence, healing, jira, executive report
  sample_app/     systems under test used by the examples (tax calculator, CRM migration)
tests/            unit/ (framework self-tests)  ui/  api/  db/  data/
config/           environments/*.yaml, locator_fingerprints.json (self-healing baseline)
docs/             USER_GUIDE  CAPABILITIES  RUNNING  SELF_HEALING  ARCHITECTURE  FRAMEWORK_COMPARISON  LIMITATIONS
```

## Writing your own tests

1. Put the test in the layer folder (`tests/ui`, `api`, `db`, `data`); the layer tag is added automatically.
2. Add tags: `@pytest.mark.smoke`, `regression`, `uat`, `e2e`, `critical`.
3. Use the fixtures: `settings`, `driver`, `login_page`, `healer`, `api_client`, `posts_api`, `db`, `repo`, `validator`.
4. Replace the sample app and sample sites with yours. Step-by-step examples: [user guide](docs/USER_GUIDE.md).

## Keeping these docs current

Every change updates this README and the [changelog](CHANGELOG.md). `tests/unit/test_documentation.py` fails if a
command-line option or setting is undocumented, a documentation file is not linked from here, or a link is broken.

Author: Anil Kalisetti · License: MIT
