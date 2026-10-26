<!-- Author: Anil Kalisetti -->
# How this framework compares

**Method and caveat.** GitHub was unreachable from the build sandbox, so this compares against
*kinds* of public PyTest frameworks (not named repositories, whose stars and features change).
Scores are my own judgement of design on paper, 0-5, and this framework's live layers are
untested (see LIMITATIONS.md). Treat it as a to-do list, not a leaderboard.

Archetypes: **A** = typical Selenium + Page Object starter template; **B** = API-focused
template (requests + schema); **C** = mature enterprise-grade community framework
(Allure, BDD, Docker, multiple drivers); **D** = Playwright-pytest based template.

| Capability | This | A | B | C | D |
|---|---|---|---|---|---|
| UI page objects, driver factory | 4 | 3 | 0 | 4 | 4 |
| Cloud grids (Sauce / BrowserStack / LambdaTest) | 4 (untested) | 1 | 0 | 3 | 2 |
| API client, retries, schema checks | 4 | 0 | 4 | 3 | 1 |
| DB-driven data with write-back | 4 | 0 | 1 | 2 | 0 |
| ETL / migration validation | 5 | 0 | 0 | 1 | 0 |
| Management-level report with verdict + trend | 4 | 0 | 0 | 2 | 0 |
| Jira defect creation, de-duplication | 4 | 0 | 0 | 3 | 0 |
| CI templates (4 systems) + Docker | 4 | 1 | 2 | 4 | 3 |
| Coverage, screenshots, parallel, retries | 4 | 2 | 2 | 4 | 3 |
| Config layering and secrets hygiene | 4 | 1 | 2 | 3 | 2 |
| Framework self-tests | 4 | 0 | 1 | 3 | 1 |
| **Proven in real runs / community use** | **1** | 3 | 3 | 5 | 4 |
| Allure dashboard out of the box | 2 | 2 | 1 | 5 | 3 |
| BDD support | 0 | 1 | 0 | 4 | 1 |
| Mobile / Appium | 0 | 0 | 0 | 3 | 1 |
| Visual regression, accessibility | 0 | 0 | 0 | 2 | 3 |
| Performance / contract testing | 0 | 0 | 1 | 1 | 0 |
| Auto-wait / trace / video debugging | 1 | 1 | 0 | 2 | 5 |

## Where it ranks

Strongest on **breadth in one repo** (UI + API + DB + ETL) and **stakeholder reporting**; roughly
on par with archetype C on structure, and **behind all of them on real-world proof**, which
matters most. Expect an honest rank of "upper-middle until it has been run in anger".

## Where it lags (backlog)

1. Run it for real: fix first-run issues in plugins, SQLAlchemy client, UI selectors, API expectations.
2. Persistent trend/flaky history (database or artifact) instead of per-workspace `history.json`.
3. Allure report generation + hosting (GitHub Pages) in CI.
4. Playwright driver behind the same page-object interface (traces, video, auto-waits).
5. Mobile/Appium on the existing cloud capability layer.
6. Visual regression and axe-core accessibility checks.
7. Contract tests (Pact) and a Locust/k6 companion for performance.
8. Optional BDD layer (pytest-bdd).
9. Secrets-manager adapters, OAuth2 helper (placeholder exists).
10. Test-impact analysis and automatic flaky-test quarantine.
