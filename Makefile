# Vulcan — root developer targets
.PHONY: up down logs test test-contracts lint help

COMPOSE ?= docker compose
PYTHON ?= $(shell command -v python3.12 >/dev/null 2>&1 && echo python3.12 || echo python3)
CONTRACTS_DIR := contracts/model-contract
CONTRACTS_VENV := $(CONTRACTS_DIR)/.venv
COVERAGE_MIN ?= 65

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?##"}; {printf "  %-18s %s\n", $$1, $$2}'

up: ## Start local stack (CPU-only; ADR-002)
	$(COMPOSE) up -d

down: ## Stop local stack
	$(COMPOSE) down

logs: ## Follow compose logs
	$(COMPOSE) logs -f

$(CONTRACTS_VENV)/bin/pytest: $(CONTRACTS_DIR)/pyproject.toml
	$(PYTHON) -m venv $(CONTRACTS_VENV)
	$(CONTRACTS_VENV)/bin/pip install -U pip
	$(CONTRACTS_VENV)/bin/pip install -e "$(CONTRACTS_DIR)[dev]"

test-contracts: $(CONTRACTS_VENV)/bin/pytest ## Contract schema tests (≥65% coverage)
	cd $(CONTRACTS_DIR) && .venv/bin/pytest -q \
		--cov=vulcan_model_contract \
		--cov-report=term-missing \
		--cov-fail-under=$(COVERAGE_MIN)

test: test-contracts ## Fan-out unit tests
	@echo "==> test: e2e"
	@echo "  skip e2e (tests/e2e not populated yet)"
	@echo "==> test: OK"

lint: $(CONTRACTS_VENV)/bin/pytest ## Fan-out linters
	@echo "==> lint: ruff (model-contract)"
	cd $(CONTRACTS_DIR) && .venv/bin/ruff check src tests
	@echo "==> lint: ADR presence (001, 002)"
	@test -f docs/adr/001-unified-model-serving-contract.md
	@test -f docs/adr/002-gpu-cost-safety-policy.md
	@echo "==> lint: OK"
