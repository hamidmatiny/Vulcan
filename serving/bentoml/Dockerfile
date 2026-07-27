# Vulcan BentoML CPU image (ADR-002 — no CUDA in default build).
# Build from repo root:
#   docker build -f serving/bentoml/Dockerfile -t vulcan-bentoml:cpu .
#
# Requires phase-1 artifacts under models/artifacts/ (run `make models-export` first).

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VULCAN_RUNTIME_MODE=cpu \
    VULCAN_MODELS_DIR=/models \
    BENTOML_HOME=/tmp/bentoml \
    PORT=9000

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY contracts/model-contract /app/contracts/model-contract
RUN pip install --no-cache-dir -e /app/contracts/model-contract

COPY serving/bentoml/requirements.txt /app/serving/bentoml/requirements.txt
RUN pip install --no-cache-dir -r /app/serving/bentoml/requirements.txt \
 && pip install --no-cache-dir torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu

COPY serving/bentoml /app/serving/bentoml
COPY serving/common/src/vulcan_serving_common/otel.py /app/serving/bentoml/otel_setup.py
COPY models/artifacts/ /models/

WORKDIR /app/serving/bentoml
EXPOSE 9000

HEALTHCHECK --interval=10s --timeout=5s --start-period=120s --retries=12 \
  CMD curl -fsS http://127.0.0.1:9000/health | grep -q '"status":"ok"'

CMD ["bentoml", "serve", "service:VulcanService", "--host", "0.0.0.0", "--port", "9000"]
