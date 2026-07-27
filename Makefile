# Vulcan — root developer targets
.PHONY: up down logs test test-contracts test-serving-common test-benchmark \
	test-checkpointing test-sagemaker test-bedrock test-gateway \
	test-cost-exporter docs-serve docs-build up-observability lint \
	reference-server benchmark-smoke benchmark-bentoml benchmark-ray-serve \
	benchmark-triton benchmark-vllm benchmark-compare models-export \
	models-verify triton-prepare wait-for-health validate-kserve \
	validate-gpu-infra validate-autoscaling validate-kubeflow \
	validate-advanced-gpu help

COMPOSE ?= docker compose
PYTHON ?= $(shell command -v python3.12 >/dev/null 2>&1 && echo python3.12 || echo python3)
CONTRACTS_DIR := contracts/model-contract
CONTRACTS_VENV := $(CONTRACTS_DIR)/.venv
SERVING_COMMON_DIR := serving/common
SERVING_COMMON_VENV := $(SERVING_COMMON_DIR)/.venv
CHECKPOINTING_DIR := autoscaling/checkpointing
CHECKPOINTING_VENV := $(CHECKPOINTING_DIR)/.venv
SAGEMAKER_DIR := pipelines/sagemaker
SAGEMAKER_VENV := $(SAGEMAKER_DIR)/.venv
BEDROCK_DIR := bedrock-gateway
BEDROCK_VENV := $(BEDROCK_DIR)/.venv
MODELS_VENV := models/.venv
COVERAGE_MIN ?= 65
# Vulcan host ports: 9000–9099
REF_HOST ?= 127.0.0.1
REF_PORT ?= 9001
BENTOML_PORT ?= 9000
RAY_SERVE_PORT ?= 9002
TRITON_PORT ?= 9003
VLLM_PORT ?= 9004
GATEWAY_PORT ?= 9007
PROMETHEUS_PORT ?= 9008
GRAFANA_PORT ?= 9009
TEMPO_PORT ?= 9010
# Poll loop mirrors CI health-wait (96 × 5s ≈ 8 min).
HEALTH_WAIT_RETRIES ?= 96
HEALTH_WAIT_SLEEP_SECS ?= 5

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?##"}; {printf "  %-22s %s\n", $$1, $$2}'

up: triton-prepare ## Start local stack (:9000/:9002/:9003/:9004; CPU-only)
	$(COMPOSE) up -d --build --wait bentoml ray-serve triton vllm

up-observability: ## Backends + gateway + Prometheus/Grafana/Tempo (:9008/:9009/:9010)
	$(COMPOSE) up -d --build --wait bentoml ray-serve gateway \
		otel-collector tempo prometheus alertmanager blackbox cost-exporter synthetic-dcgm grafana

down: ## Stop local stack
	$(COMPOSE) down

logs: ## Follow compose logs
	$(COMPOSE) logs -f

# WAIT_URL=http://127.0.0.1:9003  OR  WAIT_PORT=9003 (host=$(REF_HOST))
wait-for-health: ## Poll /health until "status":"ok" (set WAIT_URL or WAIT_PORT)
	@url="$(WAIT_URL)"; \
	if [ -z "$$url" ]; then \
	  if [ -z "$(WAIT_PORT)" ]; then \
	    echo "wait-for-health: set WAIT_URL or WAIT_PORT" >&2; exit 2; \
	  fi; \
	  url="http://$(REF_HOST):$(WAIT_PORT)"; \
	fi; \
	url="$${url%/}"; \
	echo "==> wait-for-health $$url/health (retries=$(HEALTH_WAIT_RETRIES), sleep=$(HEALTH_WAIT_SLEEP_SECS)s)"; \
	for i in $$(seq 1 $(HEALTH_WAIT_RETRIES)); do \
	  if curl -fsS "$$url/health" 2>/dev/null | grep -q '"status":"ok"'; then \
	    echo "ready: $$url"; \
	    curl -fsS "$$url/health"; echo; \
	    exit 0; \
	  fi; \
	  echo "waiting ($$i/$(HEALTH_WAIT_RETRIES))..."; \
	  sleep $(HEALTH_WAIT_SLEEP_SECS); \
	done; \
	echo "wait-for-health: timed out waiting for $$url/health" >&2; \
	exit 1

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
		$(MAKE) wait-for-health WAIT_URL="$(VULCAN_BACKEND_URL)"; \
		echo "==> conformance against $(VULCAN_BACKEND_URL) (no local coverage gate)"; \
		cd $(SERVING_COMMON_DIR) && .venv/bin/pytest -q tests/conformance; \
	else \
		cd $(SERVING_COMMON_DIR) && .venv/bin/pytest -q \
			--cov=vulcan_serving_common \
			--cov-report=term-missing \
			--cov-fail-under=$(COVERAGE_MIN); \
	fi

test-benchmark: $(SERVING_COMMON_VENV)/bin/pytest ## Benchmark compare-script unit tests
	PYTHONPATH=benchmark/scripts $(SERVING_COMMON_VENV)/bin/python -m pytest -q benchmark/tests

test: test-contracts test-serving-common test-benchmark test-gateway test-cost-exporter ## Fan-out unit tests
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
	@$(MAKE) wait-for-health WAIT_PORT=$(REF_PORT)
	BASE_URL=http://$(REF_HOST):$(REF_PORT) \
	MODEL_TYPE=llm MODEL_ID=reference-tiny-llm \
	VUS=2 DURATION=8s BACKEND_NAME=reference \
	RESULTS_OUT=benchmark/results/reference-llm.json \
	bash benchmark/scripts/run_k6.sh

benchmark-bentoml: ## Short CPU k6 against bentoml (:9000) → bentoml-cpu.json
	@$(MAKE) wait-for-health WAIT_PORT=$(BENTOML_PORT)
	BASE_URL=http://$(REF_HOST):$(BENTOML_PORT) \
	MODEL_TYPE=llm MODEL_ID=reference-tiny-llm \
	VUS=2 DURATION=10s BACKEND_NAME=bentoml \
	RESULTS_OUT=benchmark/results/bentoml-cpu.json \
	bash benchmark/scripts/run_k6.sh

benchmark-ray-serve: ## Short CPU k6 against ray-serve (:9002) → ray-serve-cpu.json
	@$(MAKE) wait-for-health WAIT_PORT=$(RAY_SERVE_PORT)
	BASE_URL=http://$(REF_HOST):$(RAY_SERVE_PORT) \
	MODEL_TYPE=llm MODEL_ID=reference-tiny-llm \
	VUS=2 DURATION=10s BACKEND_NAME=ray-serve \
	RESULTS_OUT=benchmark/results/ray-serve-cpu.json \
	bash benchmark/scripts/run_k6.sh

benchmark-triton: ## Short CPU k6 against triton (:9003) → triton-cpu.json
	@$(MAKE) wait-for-health WAIT_PORT=$(TRITON_PORT)
	BASE_URL=http://$(REF_HOST):$(TRITON_PORT) \
	MODEL_TYPE=llm MODEL_ID=reference-tiny-llm \
	VUS=2 DURATION=10s BACKEND_NAME=triton \
	RESULTS_OUT=benchmark/results/triton-cpu.json \
	bash benchmark/scripts/run_k6.sh

benchmark-vllm: ## Short CPU k6 against vllm (:9004) → vllm-cpu.json
	@$(MAKE) wait-for-health WAIT_PORT=$(VLLM_PORT)
	BASE_URL=http://$(REF_HOST):$(VLLM_PORT) \
	MODEL_TYPE=llm MODEL_ID=reference-tiny-llm \
	VUS=2 DURATION=10s BACKEND_NAME=vllm \
	RESULTS_OUT=benchmark/results/vllm-cpu.json \
	bash benchmark/scripts/run_k6.sh

triton-prepare: ## Populate Triton model_repository with ONNX (needs models-export)
	@test -d $(MODELS_VENV) || $(MAKE) models-export
	$(MODELS_VENV)/bin/pip install -q -r serving/triton/scripts/requirements-prepare.txt
	$(MODELS_VENV)/bin/python serving/triton/scripts/prepare_model_repo.py

validate-kserve: ## helm template + kubeconform + conftest (no cluster apply)
	bash serving/kserve/scripts/validate.sh

validate-gpu-infra: ## terraform validate/plan + GPU Operator/MIG helm+conftest (no apply)
	bash gpu-infra/scripts/validate.sh

validate-autoscaling: ## Karpenter helm template + kubeconform + conftest (no apply)
	bash autoscaling/karpenter/scripts/validate.sh

validate-kubeflow: ## compile KFP + kubeconform/conftest PyTorchJob/ISVC (no apply)
	bash pipelines/kubeflow/scripts/validate.sh

validate-advanced-gpu: ## Schema-validate vLLM quant manifests + lint TRT-LLM config.pbtxt (no GPU)
	chmod +x serving/scripts/validate-advanced-gpu-serving.sh
	bash serving/scripts/validate-advanced-gpu-serving.sh

$(CHECKPOINTING_VENV)/bin/pytest: $(CHECKPOINTING_DIR)/pyproject.toml
	$(PYTHON) -m venv $(CHECKPOINTING_VENV)
	$(CHECKPOINTING_VENV)/bin/pip install -U pip
	$(CHECKPOINTING_VENV)/bin/pip install -e "$(CHECKPOINTING_DIR)[dev]"

test-checkpointing: $(CHECKPOINTING_VENV)/bin/pytest ## Checkpoint-on-SIGTERM / resume (≥65%)
	cd $(CHECKPOINTING_DIR) && .venv/bin/pytest -q \
		--cov=vulcan_checkpointing --cov-report=term-missing \
		--cov-fail-under=$(COVERAGE_MIN)

$(SAGEMAKER_VENV)/bin/pytest: $(SAGEMAKER_DIR)/pyproject.toml
	$(PYTHON) -m venv $(SAGEMAKER_VENV)
	$(SAGEMAKER_VENV)/bin/pip install -U pip
	$(SAGEMAKER_VENV)/bin/pip install -e "$(SAGEMAKER_DIR)[dev]"

test-sagemaker: $(SAGEMAKER_VENV)/bin/pytest ## SageMaker pipeline/registry moto tests (≥65%)
	cd $(SAGEMAKER_DIR) && SAGEMAKER_SUPPRESS_V2_WARNING=1 .venv/bin/pytest -q \
		--cov=vulcan_sagemaker --cov-report=term-missing \
		--cov-fail-under=$(COVERAGE_MIN)

$(BEDROCK_VENV)/bin/pytest: $(BEDROCK_DIR)/pyproject.toml $(CONTRACTS_DIR)/pyproject.toml
	$(PYTHON) -m venv $(BEDROCK_VENV)
	$(BEDROCK_VENV)/bin/pip install -U pip
	$(BEDROCK_VENV)/bin/pip install -e "$(CONTRACTS_DIR)[dev]"
	$(BEDROCK_VENV)/bin/pip install -e "$(BEDROCK_DIR)[dev]"

test-bedrock: $(BEDROCK_VENV)/bin/pytest ## Bedrock gateway adapter moto tests (≥65%)
	cd $(BEDROCK_DIR) && .venv/bin/pytest -q \
		--cov=vulcan_bedrock --cov-report=term-missing \
		--cov-fail-under=$(COVERAGE_MIN)

test-gateway: ## Go tests for gateway/internal (≥65% coverage; excludes thin cmd/)
	cd gateway && go test ./internal/... -coverprofile=coverage.out -covermode=atomic \
		&& go tool cover -func=coverage.out | awk '/^total:/{gsub(/%/,"",$$3); printf "gateway coverage: %s%%\n", $$3; if ($$3+0 < $(COVERAGE_MIN)) { print "coverage below $(COVERAGE_MIN)%" > "/dev/stderr"; exit 1 }}'

COST_EXPORTER_DIR := observability/cost-exporter
COST_EXPORTER_VENV := $(COST_EXPORTER_DIR)/.venv

$(COST_EXPORTER_VENV)/bin/pytest: $(COST_EXPORTER_DIR)/pyproject.toml
	$(PYTHON) -m venv $(COST_EXPORTER_VENV)
	$(COST_EXPORTER_VENV)/bin/pip install -U pip
	$(COST_EXPORTER_VENV)/bin/pip install -e "$(COST_EXPORTER_DIR)[dev]"

test-cost-exporter: $(COST_EXPORTER_VENV)/bin/pytest ## Cost-exporter unit tests (≥65%)
	cd $(COST_EXPORTER_DIR) && .venv/bin/pytest -q \
		--cov=exporter --cov-report=term-missing \
		--cov-fail-under=$(COVERAGE_MIN)

docs-build: ## Build MkDocs Material site → site/
	$(PYTHON) -m venv docs/.venv
	docs/.venv/bin/pip install -q -U pip
	docs/.venv/bin/pip install -q -r docs/requirements-docs.txt
	docs/.venv/bin/mkdocs build

docs-serve: ## Serve docs locally (http://127.0.0.1:8000)
	$(PYTHON) -m venv docs/.venv
	docs/.venv/bin/pip install -q -U pip
	docs/.venv/bin/pip install -q -r docs/requirements-docs.txt
	docs/.venv/bin/mkdocs serve -a 127.0.0.1:8000

benchmark-gateway: ## Short CPU k6 against gateway (:9007) → gateway-cpu.json
	@$(MAKE) wait-for-health WAIT_PORT=$(GATEWAY_PORT)
	BASE_URL=http://$(REF_HOST):$(GATEWAY_PORT) \
	MODEL_TYPE=llm MODEL_ID=reference-tiny-llm \
	VUS=2 DURATION=10s BACKEND_NAME=gateway \
	RESULTS_OUT=benchmark/results/gateway-cpu.json \
	bash benchmark/scripts/run_k6.sh

benchmark-compare: ## Markdown table from benchmark/results/*.json
	$(PYTHON) benchmark/scripts/compare_results.py --skip-schema 2>/dev/null || \
		$(SERVING_COMMON_VENV)/bin/python benchmark/scripts/compare_results.py

models-export: ## Fetch/export pinned reference models (CPU)
	$(PYTHON) -m venv $(MODELS_VENV)
	$(MODELS_VENV)/bin/pip install -U pip
	$(MODELS_VENV)/bin/pip install -r models/scripts/requirements.txt
	# Force CPU wheels without reinstalling shared deps (numpy ABI must stay intact).
	$(MODELS_VENV)/bin/pip install --force-reinstall --no-deps torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu
	PYTHONHASHSEED=0 $(MODELS_VENV)/bin/python models/scripts/export_llm.py
	PYTHONHASHSEED=0 $(MODELS_VENV)/bin/python models/scripts/export_vision.py
	PYTHONHASHSEED=0 $(MODELS_VENV)/bin/python models/scripts/write_manifest.py --require-artifacts

models-verify: ## Verify artifacts match MANIFEST.md
	PYTHONHASHSEED=0 $(MODELS_VENV)/bin/python models/scripts/verify_manifest.py
