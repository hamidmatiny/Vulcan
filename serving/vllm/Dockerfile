# Vulcan vLLM contract shim (CPU) — public :9004 over internal OpenAI-compatible engine.
# Build from repo root:
#   docker build -f serving/vllm/Dockerfile -t vulcan-vllm:cpu .

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VULCAN_RUNTIME_MODE=cpu \
    VLLM_URL=http://vllm-engine:8000 \
    VLLM_WAIT_SECONDS=300 \
    PORT=9004 \
    HOST=0.0.0.0

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY contracts/model-contract /app/contracts/model-contract
RUN pip install --no-cache-dir -e /app/contracts/model-contract

COPY serving/vllm/requirements.txt /app/serving/vllm/requirements.txt
RUN pip install --no-cache-dir -r /app/serving/vllm/requirements.txt

COPY serving/vllm /app/serving/vllm
COPY serving/common/src/vulcan_serving_common/otel.py /app/serving/vllm/otel_setup.py

WORKDIR /app/serving/vllm
EXPOSE 9004

HEALTHCHECK --interval=10s --timeout=5s --start-period=120s --retries=36 \
  CMD curl -fsS http://127.0.0.1:9004/health | grep -q '"status":"ok"'

CMD ["uvicorn", "shim.service:app", "--host", "0.0.0.0", "--port", "9004"]
