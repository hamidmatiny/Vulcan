# Vulcan — root developer targets
.PHONY: up down logs test test-contracts test-serving-common test-benchmark \
	lint reference-server benchmark-smoke benchmark-bentoml benchmark-ray-serve \
	benchmark-compare models-export models-verify help

COMPOSE ?= docker compose
PYTHON ?= $(shell command -v python3.12 >/dev/null 2>&1 && echo python3.12 || echo python3)
CONTRACTS_DIR := contracts/model-contract
CONTRACTS_VENV := $(CONTRACTS_DIR)/.venv
SERVING_COMMON_DIR := serving/common
SERVING_COMMON_VENV := $(SERVING_COMMON_DIR)/.venv
MODELS_VENV := models/.venv
COVERAGE_MIN ?= 65
# Vulcan host ports: 9000–9099
REF_HOST ?= 127.0.0.1
REF_PORT ?= 9001
BENTOML_PORT ?= 9000
RAY_SERVE_PORT ?= 9002

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?##"}; {printf "  %-22s %s\n", $$1, $$2}'

up: ## Start local stack (bentoml :9000, ray-serve :9002; CPU-only)
	$(COMPOSE) up -d --build bentoml ray-serve

down: ## Stop local stack
	$(COMPOSE) down

logs: ## Follow compose logs
	$(COMPOSE) logs -f

$(CONTRACTS_VENV)/bin/pytest: $(CONTRACTS_DIR)/pyproject.toml
	$(PYTHON) -m venv $(CONTRACTS_VENV)
	$(CONTRACTS_VENV)/bin/pip install -U pip
	$(CONTRACTS_VENV)/bin/pip install -e "$(CONTRACTS_DIR)[dev]"

$(SERVING_COMMON_VENV)/bin/pytest: $(SERVING_COMMON_DIR)/pyproject.toml $(CONTRACTS_DIR)/pyproject.toml
	$(PYTHON) -m venv $(SERVING_COMMON_VENV)
	$(SERVING_COMMON_VENV)/bin/pip install -U pip
	$(SERVING_COMMON_VENV)/bin/pip install -e "$(CONTRACTS_DIR)[dev]"
	$(SERVING_COMMON_VENV)/bin/pip install -e "$(SERVING_COMMON_DIR)[dev]"

test-contracts: $(CONTRACTS_VENV)/bin/pytest ## Contract schema tests (≥65% coverage)
	cd $(CONTRACTS_DIR) && .venv/bin/pytest -q \
		--cov=vulcan_model_contract \
		--cov-report=term-missing \
		--cov-fail-under=$(COVERAGE_MIN)

test-serving-common: $(SERVING_COMMON_VENV)/bin/pytest ## Conformance + client tests (≥65%)
	@if [ -n "$(VULCAN_BACKEND_URL)" ]; then \
		echo "==> conformance against $$VULCAN_BACKEND_URL (no local coverage gate)"; \
		cd $(SERVING_COMMON_DIR) && .venv/bin/pytest -q tests/conformance; \
	else \
		cd $(SERVING_COMMON_DIR) && .venv/bin/pytest -q \
			--cov=vulcan_serving_common \
			--cov-report=term-missing \
			--cov-fail-under=$(COVERAGE_MIN); \
	fi

test-benchmark: $(SERVING_COMMON_VENV)/bin/pytest ## Benchmark compare-script unit tests
	PYTHONPATH=benchmark/scripts $(SERVING_COMMON_VENV)/bin/python -m pytest -q benchmark/tests

test: test-contracts test-serving-common test-benchmark ## Fan-out unit tests
	@echo "==> test: OK"

lint: $(CONTRACTS_VENV)/bin/pytest $(SERVING_COMMON_VENV)/bin/pytest ## Fan-out linters
	@echo "==> lint: ruff (model-contract)"
	cd $(CONTRACTS_DIR) && .venv/bin/ruff check src tests
	@echo "==> lint: ruff (serving/common)"
	cd $(SERVING_COMMON_DIR) && .venv/bin/ruff check src tests
	@echo "==> lint: ADR presence (001, 002)"
	@test -f docs/adr/001-unified-model-serving-contract.md
	@test -f docs/adr/002-gpu-cost-safety-policy.md
	@echo "==> lint: OK"

reference-server: $(SERVING_COMMON_VENV)/bin/pytest ## Trivial reference server (:9001)
	$(SERVING_COMMON_VENV)/bin/vulcan-reference-server --host $(REF_HOST) --port $(REF_PORT)

benchmark-smoke: ## k6 smoke against reference server (:9001)
	BASE_URL=http://$(REF_HOST):$(REF_PORT) \
	MODEL_TYPE=llm MODEL_ID=reference-tiny-llm \
	VUS=2 DURATION=8s BACKEND_NAME=reference \
	RESULTS_OUT=benchmark/results/reference-llm.json \
	bash benchmark/scripts/run_k6.sh

benchmark-bentoml: ## Short CPU k6 against bentoml (:9000) → bentoml-cpu.json
	BASE_URL=http://$(REF_HOST):$(BENTOML_PORT) \
	MODEL_TYPE=llm MODEL_ID=reference-tiny-llm \
	VUS=2 DURATION=10s BACKEND_NAME=bentoml \
	RESULTS_OUT=benchmark/results/bentoml-cpu.json \
	bash benchmark/scripts/run_k6.sh

benchmark-ray-serve: ## Short CPU k6 against ray-serve (:9002) → ray-serve-cpu.json
	BASE_URL=http://$(REF_HOST):$(RAY_SERVE_PORT) \
	MODEL_TYPE=llm MODEL_ID=reference-tiny-llm \
	VUS=2 DURATION=10s BACKEND_NAME=ray-serve \
	RESULTS_OUT=benchmark/results/ray-serve-cpu.json \
	bash benchmark/scripts/run_k6.sh

benchmark-compare: ## Markdown table from benchmark/results/*.json
	$(PYTHON) benchmark/scripts/compare_results.py --skip-schema 2>/dev/null || \
		$(SERVING_COMMON_VENV)/bin/python benchmark/scripts/compare_results.py

models-export: ## Fetch/export pinned reference models (CPU)
	$(PYTHON) -m venv $(MODELS_VENV)
	$(MODELS_VENV)/bin/pip install -U pip
	$(MODELS_VENV)/bin/pip install -r models/scripts/requirements.txt
	cd models/scripts && ../.venv/bin/python export_llm.py
	cd models/scripts && ../.venv/bin/python export_vision.py
	cd models/scripts && ../.venv/bin/python write_manifest.py --require-artifacts

models-verify: ## Verify artifacts match MANIFEST.md
	cd models/scripts && ../.venv/bin/python verify_manifest.py
