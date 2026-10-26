# ---------------------------------------------------------------------------
# Author  : Anil Kalisetti
# Purpose : One-word commands for every common task (same commands locally and in CI).
# Usage   : make help
# ---------------------------------------------------------------------------
PYTHON  ?= python3
VENV    ?= .venv
BIN     := $(VENV)/bin
PYTEST  := $(BIN)/pytest
WORKERS ?= auto

.DEFAULT_GOAL := help
.PHONY: help install install-dev lint format typecheck unit api data db ui smoke regression \
        all parallel tag tags browsers record-locators report allure docker-build docker-test clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Create .venv and install runtime dependencies
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt

install-dev: install ## Also install lint / type-check tooling and git hooks
	$(BIN)/pip install -r requirements-dev.txt
	$(BIN)/pre-commit install

lint: ## Static analysis (ruff)
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format: ## Auto-format and auto-fix lint findings
	$(BIN)/ruff format .
	$(BIN)/ruff check --fix .

typecheck: ## Type check the framework package (mypy)
	$(BIN)/mypy framework

unit: ## Offline framework self-tests (seconds, no network)
	$(PYTEST) -m unit

data: ## ETL / data validation tests (offline, in-memory databases)
	$(PYTEST) -m "data and not slow"

db: ## Database-driven tests (offline)
	$(PYTEST) -m db

api: ## API tests (needs internet: JSONPlaceholder + httpbingo)
	$(PYTEST) -m api -n $(WORKERS)

ui: ## Browser tests on this machine (needs Chrome; add MODE=saucelabs etc. to go remote)
	$(PYTEST) -m ui $(if $(MODE),--execution-mode $(MODE),) --reruns 1 --only-rerun WebDriverException -n 4

smoke: ## Fast, business-critical checks across all layers
	$(PYTEST) -m smoke -n $(WORKERS)

regression: ## Full regression (everything except slow tests)
	$(PYTEST) -m "not slow" -n $(WORKERS)

all: ## Absolutely everything, including slow tests
	$(PYTEST) -n $(WORKERS)

parallel: ## Any tag expression in parallel: make parallel TAGS="smoke or uat" WORKERS=4
	$(PYTEST) --tags "$(or $(TAGS),not slow)" -n $(WORKERS)

tag: ## Run one tag group: make tag TAGS="uat" (use quotes for expressions)
	$(PYTEST) --tags "$(TAGS)" -n $(WORKERS)

tags: ## Show how many tests carry each tag (smoke, uat, regression, ...)
	$(PYTEST) --list-tags --collect-only -q -p no:cacheprovider

browsers: ## UI tests on several browsers: make browsers BROWSERS=chrome,firefox (or all)
	$(PYTEST) -m ui --ui-browsers $(or $(BROWSERS),all) -n $(WORKERS) --reruns 1 --only-rerun WebDriverException

record-locators: ## Capture locator fingerprints on a KNOWN-GOOD build, then commit the diff
	$(PYTEST) -m "ui and smoke" --record-locators -n 0

report: ## Open the management summary (macOS: open, Linux: xdg-open)
	@(open reports/executive_summary.html || xdg-open reports/executive_summary.html) 2>/dev/null || \
		echo "Open reports/executive_summary.html in a browser"

allure: ## Build and open the Allure report (requires the Allure CLI)
	allure serve reports/allure-results

docker-build: ## Build the test-runner image
	docker build -t pytest-framework .

docker-test: ## Run the whole stack against a local Selenium Grid container
	docker compose up --build --abort-on-container-exit --exit-code-from tests

clean: ## Remove generated reports and caches
	rm -rf reports .pytest_cache .ruff_cache .mypy_cache .coverage
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
