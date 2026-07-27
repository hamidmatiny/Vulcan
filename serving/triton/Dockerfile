# Vulcan Triton contract shim (CPU) — public :9003 over internal Triton HTTP.
# Build from repo root:
#   docker build -f serving/triton/Dockerfile -t vulcan-triton:cpu .
#
# Requires phase-1 artifacts under models/artifacts/ (tokenizer + vision sidecars).

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VULCAN_RUNTIME_MODE=cpu \
    VULCAN_MODELS_DIR=/models \
    TRITON_URL=triton-engine:8000 \
    TRITON_WAIT_SECONDS=300 \
    PORT=9003 \
    HOST=0.0.0.0

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY contracts/model-contract /app/contracts/model-contract
RUN pip install --no-cache-dir -e /app/contracts/model-contract

COPY serving/triton/requirements.txt /app/serving/triton/requirements.txt
RUN pip install --no-cache-dir -r /app/serving/triton/requirements.txt

COPY serving/triton /app/serving/triton
COPY serving/common/src/vulcan_serving_common/otel.py /app/serving/triton/otel_setup.py
COPY models/artifacts/ /models/

ENV VULCAN_TOKENIZER_DIR=/models/llm/gpt2-small \
    VULCAN_LABELS_PATH=/models/vision/resnet18/imagenet_classes.json \
    VULCAN_PREPROCESS_PATH=/models/vision/resnet18/preprocess.json

WORKDIR /app/serving/triton
EXPOSE 9003

HEALTHCHECK --interval=10s --timeout=5s --start-period=240s --retries=36 \
  CMD curl -fsS http://127.0.0.1:9003/health | grep -q '"status":"ok"'

CMD ["uvicorn", "shim.service:app", "--host", "0.0.0.0", "--port", "9003"]
