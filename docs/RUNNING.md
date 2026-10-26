<!-- Author: Anil Kalisetti -->
# Running tests: parallel, by tag, on many browsers

## 1. Parallel execution

```bash
pytest -n auto                    # one worker per CPU core
pytest -n 4 --tags smoke          # four workers, smoke tests only
make parallel TAGS="regression and not slow" WORKERS=8
```

What the framework does so parallel runs are safe (pytest-xdist):

| Shared thing | Problem in parallel | What we do |
|---|---|---|
| SQLite test-data file | two workers write results to one file | each worker gets its own copy: `sample_test_gw0.db`, `..._gw1.db` (`framework/core/parallel.py`) |
| Log file | workers overwrite one file | one log per worker: `reports/logs/pytest-gw0.log` |
| Browser | shared cookies / cart | one fresh browser per test |
| Reports, Jira, summary | duplicated or missing rows | collected only in the controller process; evidence travels in each test report |
| Tests that must run in order | would be split across workers | `@pytest.mark.xdist_group("checkout-flow")`; `--dist=loadgroup` is on by default |

Rules for your own tests: do not depend on another test's output; do not share files; for a
shared server database (Postgres, Oracle) partition rows per worker (placeholder with
instructions in `worker_db_url`).

## 2. Grouping by tag

A tag is a pytest marker. Standard tags: `smoke`, `sanity`, `regression`, `uat`, `e2e`,
`critical` (plus layer tags `ui api db data etl unit` applied automatically by folder, and
`slow`, `network`).

```bash
pytest --tags smoke                    # fast gate on every commit
pytest --tags "smoke or sanity"        # after a deployment
pytest --tags uat                      # business sign-off
pytest --tags "regression and not slow" -n auto
pytest --tags "uat and ui" --ui-browsers chrome,firefox
pytest --list-tags                     # how many tests carry each tag
```

`--tags` is checked against the registered markers, so a typo (`--tags smok`) is an error
instead of a silent, green, empty run. It combines with `-m` using AND. Add a new tag by
registering it in `pyproject.toml` (`--strict-markers` is on) and, if it should appear in the
report breakdown, in `framework/core/tags.py::STANDARD_TAGS`.

The management report shows pass rate **per tag** (is smoke green? is UAT green?) and, when a
browser matrix ran, **per browser**.

## 3. Multiple browsers

```bash
pytest -m ui --ui-browsers chrome,firefox      # every UI test once per browser
pytest -m ui --ui-browsers all                 # chrome, firefox, edge
pytest -m ui --ui-browser firefox              # just one, no id suffix
pytest -m ui --ui-browsers chrome,safari --execution-mode browserstack   # safari: macOS/cloud only
```

With more than one browser, test ids become `test_login[chrome]`, `test_login[firefox]`, so
failures, retries and Jira defects are per browser. Browsers x cloud platform x parallel
workers combine freely (`make browsers BROWSERS=all WORKERS=6`).

## 4. Object-oriented map

| Concept | Where | Example |
|---|---|---|
| Abstraction | `Browser`, `ExecutionTarget`, `BasePage`, `ReportRenderer` (abstract base classes) | every page must implement `is_loaded()` |
| Inheritance | `Chrome`/`Edge` <- `ChromiumBrowser` <- `Browser`; `SauceLabsTarget` <- `CloudTarget` <- `GridTarget`; `PostsService` <- `ResourceService`; pages <- `BasePage`; `DataRepository` <- `ScenarioRepository` | cloud vendors share credential rules, differ only in capability block and status script |
| Polymorphism | `browser.build_options()`, `target.report_status()`, `renderer.render()` | the test fixture never asks which browser or cloud it is |
| Encapsulation | private `_settings`, `_client`, `_table`; locators inside pages; URL building inside services | tests call `posts.get(7)`, never format `/posts/7` |
| Composition | services HAVE an `ApiClient`; the driver factory combines a `Browser` and an `ExecutionTarget` | one client with retries/logging shared by all services |
| Factory / Registry | `Browser.create(name)`, `ExecutionTarget.for_settings()`; subclasses register themselves | add `class Brave(ChromiumBrowser)` and `--ui-browsers brave` works |
| Strategy | browser (what) and target (where) chosen from config | laptop, Grid and Sauce Labs run identical tests |
| Template method | `ExecutionTarget.create_driver()` fixes the steps, subclasses fill them | options -> vendor capabilities -> start |
| Open/closed | new browser, cloud, report format, API resource = one new class | see `test_a_new_report_format_is_one_subclass` |

Deliberately NOT turned into classes: pure functions with no state (tax rounding, field
transforms in the migration, schema assertions). Wrapping them in classes would add ceremony
without any benefit.
