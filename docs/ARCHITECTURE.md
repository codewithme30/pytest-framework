<!-- Author: Anil Kalisetti -->
# Architecture

```
          pytest CLI / CI
                |
        conftest.py (root)  -- loads plugins, seeds sample DB, adds layer markers
                |
   +------------+--------------------------------------------+
   | framework/plugins                                       |
   |  options -> evidence -> jira -> executive_report        |
   +------------+--------------------------------------------+
                |
   tests/{ui,api,db,data,unit}  --uses-->  framework/{ui,api,db,data,...}
```

## Design rules

1. **Libraries know nothing about tests; tests know nothing about plumbing.** `framework/*`
   has no `import pytest` outside `plugins/`, so the libraries are reusable in scripts.
2. **One config object.** `Settings` is a frozen dataclass built once from
   CLI > env/.env > `config/environments/<env>.yaml` > defaults. Nothing else reads `os.environ`.
3. **Secrets only from the environment**, masked in logs, rejected in YAML.
4. **xdist-safe.** Collectors (report, Jira) run only in the controller process; per-test
   evidence travels in `user_properties`, which xdist serialises to the controller.
5. **Offline by default for correctness checks.** ETL, DB and unit layers use in-memory SQLite,
   so they gate PRs without flakiness; network/UI layers are separate jobs.
6. **Fail loud on bad config** (unknown YAML keys, YAML-1.1 `ON` → `True` trap, missing creds).

## Data-validation approach (ETL)

`ETLValidator.dataset_diff` streams both sides ordered by key and merge-joins them, so memory
is O(chunk) not O(rows). Reported categories: missing in target, unexpected in target,
value mismatch (with column and both values), duplicate keys. Row-count, schema, null,
duplicate, orphan and aggregate checks are separate, so a failure names the exact problem.
Numbers compare as `Decimal`; the transform hook maps legacy conventions (cents → amount,
`DD/MM/YYYY` → ISO) before comparison.

## Extending

| To add | Do this |
|---|---|
| A new environment | copy `config/environments/qa.yaml` |
| A new page | subclass `BasePage` in `framework/ui/pages` |
| A new browser | subclass `Browser` (or `ChromiumBrowser`) in `framework/ui/browsers.py`, set `name`; add it to `BROWSERS` in settings (a unit test fails if they drift) |
| A new healing strategy | subclass `HealingStrategy` (`framework/ui/healing/strategies.py`), add it in `LocatorHealer.from_settings` |
| A new cloud vendor | subclass `CloudTarget` in `framework/ui/targets.py`: capability block + status script; add the mode to `EXECUTION_MODES` |
| A new API resource | subclass `ResourceService` in `framework/api/services.py` |
| A new report type users can select | subclass `PluginReport` (a pytest plugin writes it) or `GeneratedReport` (we write it) in `framework/reporting/outputs.py`, add the name to `REPORT_NAMES` in settings (a unit test fails if they drift) |
| A new report format | subclass `ReportRenderer` in `framework/reporting/executive_report.py` |
| A new scenario table | subclass `ScenarioRepository` and set `table` |
| Token auth for an API | implement `framework/api/auth.py` (placeholder with detailed TODO) |
| A real DB | set `DB_URL` (SQLAlchemy URL) and install its driver |
