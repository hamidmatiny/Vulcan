"""CPU OpenAI-compatible server for Vulcan vLLM adapter (ADR-002).

Exposes the same `/v1/models` + `/v1/chat/completions` surface that the contract
shim expects from vLLM's OpenAI-compatible API. Loads the phase-1 GPT-2 pin via
transformers — correctness path only; not continuous batching / PagedAttention.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "reference-tiny-llm"
DEFAULT_MODEL_DIR = os.environ.get(
    "VULCAN_MODEL_DIR",
    "/models/llm/gpt2-small",
)

app = FastAPI(title="Vulcan vLLM CPU OpenAI surface", docs_url=None, redoc_url=None)

_tokenizer = None
_model = None
_ready = False


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[ChatMessage]
    max_tokens: int = Field(default=16, ge=1, le=256)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


def _load() -> None:
    global _tokenizer, _model, _ready
    model_dir = Path(DEFAULT_MODEL_DIR)
    if not model_dir.is_dir():
        raise FileNotFoundError(f"model dir missing: {model_dir}")
    _tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    if _tokenizer.pad_token is None:
        _tokenizer.pad_token = _tokenizer.eos_token
    _model = AutoModelForCausalLM.from_pretrained(str(model_dir), local_files_only=True)
    _model.eval()
    _ready = True


@app.on_event("startup")
def _startup() -> None:
    _load()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if _ready else "starting",
        "engine": "cpu-openai-compat",
        "model": MODEL_ID,
    }


@app.get("/v1/models")
def list_models() -> dict[str, Any]:
    if not _ready:
        raise HTTPException(status_code=503, detail="model loading")
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "object": "model",
                "owned_by": "vulcan",
            }
        ],
    }


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest) -> JSONResponse:
    if not _ready or _model is None or _tokenizer is None:
        raise HTTPException(status_code=503, detail="model loading")
    if req.model not in (MODEL_ID, "gpt2", "/models/llm/gpt2-small"):
        raise HTTPException(status_code=404, detail=f"unknown model: {req.model}")

    prompt_parts = [f"{m.role}: {m.content}" for m in req.messages]
    prompt_parts.append("assistant:")
    prompt = "\n".join(prompt_parts)
    encoded = _tokenizer(prompt, return_tensors="pt")
    gen_kwargs: dict[str, Any] = {
        "max_new_tokens": int(req.max_tokens),
        "pad_token_id": _tokenizer.eos_token_id,
        "eos_token_id": _tokenizer.eos_token_id,
    }
    if req.temperature and req.temperature > 0:
        gen_kwargs["do_sample"] = True
        gen_kwargs["temperature"] = float(req.temperature)
    else:
        gen_kwargs["do_sample"] = False

    with torch.no_grad():
        out = _model.generate(**encoded, **gen_kwargs)
    new_tokens = out[0, encoded["input_ids"].shape[-1] :]
    text = _tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
    prompt_tokens = int(encoded["input_ids"].shape[-1])
    completion_tokens = int(new_tokens.shape[-1])
    body = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    return JSONResponse(body)


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
