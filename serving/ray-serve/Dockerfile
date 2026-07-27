# Vulcan Ray Serve CPU image (ADR-002 — no CUDA in default build).
# Build from repo root:
#   docker build -f serving/ray-serve/Dockerfile -t vulcan-ray-serve:cpu .
#
# Requires phase-1 artifacts under models/artifacts/ (run `make models-export` first).

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VULCAN_RUNTIME_MODE=cpu \
    VULCAN_MODELS_DIR=/models \
    RAY_DEDUP_LOGS=0 \
    RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO=0 \
    PORT=9002 \
    HOST=0.0.0.0 \
    RAY_NUM_CPUS=2

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY contracts/model-contract /app/contracts/model-contract
RUN pip install --no-cache-dir -e /app/contracts/model-contract

COPY serving/ray-serve/requirements.txt /app/serving/ray-serve/requirements.txt
RUN pip install --no-cache-dir -r /app/serving/ray-serve/requirements.txt \
 && pip install --no-cache-dir torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu

COPY serving/ray-serve /app/serving/ray-serve
COPY serving/common/src/vulcan_serving_common/otel.py /app/serving/ray-serve/otel_setup.py
COPY models/artifacts/ /models/

WORKDIR /app/serving/ray-serve
EXPOSE 9002

HEALTHCHECK --interval=10s --timeout=5s --start-period=180s --retries=18 \
  CMD curl -fsS http://127.0.0.1:9002/health | grep -q '"status":"ok"'

CMD ["python", "service.py"]
