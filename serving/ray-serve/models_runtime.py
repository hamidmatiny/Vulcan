"""Load phase-1 pinned reference models for the BentoML adapter."""

from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

LLM_MODEL_ID = "reference-tiny-llm"
VISION_MODEL_ID = "reference-tiny-vision"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def models_dir() -> Path:
    env = os.environ.get("VULCAN_MODELS_DIR")
    if env:
        return Path(env)
    return _repo_root() / "models" / "artifacts"


@dataclass
class LlmBundle:
    tokenizer: Any
    model: Any
    device: str

    def generate(self, messages: list[dict[str, str]], max_tokens: int, temperature: float) -> dict[str, Any]:
        # GPT-2 is causal LM — concatenate chat turns into a plain prompt.
        prompt_parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            prompt_parts.append(f"{role}: {content}")
        prompt_parts.append("assistant:")
        prompt = "\n".join(prompt_parts)

        import torch

        inputs = self.tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        prompt_len = int(inputs["input_ids"].shape[-1])
        do_sample = temperature is not None and temperature > 0
        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": max(1, int(max_tokens)),
            "pad_token_id": self.tokenizer.eos_token_id,
            "do_sample": do_sample,
        }
        if do_sample:
            gen_kwargs["temperature"] = float(temperature)
        with torch.no_grad():
            out = self.model.generate(**inputs, **gen_kwargs)
        new_tokens = out[0][prompt_len:]
        text = self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        completion = int(new_tokens.shape[0])
        return {
            "text": text or "",
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": prompt_len,
                "completion_tokens": completion,
                "total_tokens": prompt_len + completion,
            },
        }


@dataclass
class VisionBundle:
    session: Any
    input_name: str
    output_name: str
    labels: list[str]
    mean: list[float]
    std: list[float]
    crop: int

    def classify(self, images: list[dict[str, str]], prompt: str | None) -> dict[str, Any]:
        from PIL import Image

        # Use first image; contract allows a batch but reference path is single-image.
        img_meta = images[0]
        raw = base64.b64decode(img_meta["data_base64"])
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        image = image.resize((self.crop, self.crop), Image.BILINEAR)
        arr = np.asarray(image).astype(np.float32) / 255.0
        mean = np.array(self.mean, dtype=np.float32)
        std = np.array(self.std, dtype=np.float32)
        arr = (arr - mean) / std
        # NCHW
        tensor = np.transpose(arr, (2, 0, 1))[None, ...]
        outputs = self.session.run([self.output_name], {self.input_name: tensor})
        logits = outputs[0][0]
        # Softmax for scores
        exp = np.exp(logits - np.max(logits))
        probs = exp / np.sum(exp)
        top_idx = int(np.argmax(probs))
        label = self.labels[top_idx] if top_idx < len(self.labels) else str(top_idx)
        score = float(probs[top_idx])
        text = f"{label} ({score:.3f})"
        if prompt:
            text = f"{prompt.strip()}: {text}"
        return {
            "text": text,
            "labels": [{"name": label, "score": score}],
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }


def load_llm(device: str | None = None) -> LlmBundle:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    path = models_dir() / "llm" / "gpt2-small"
    if not (path / "model.safetensors").is_file() and not (path / "config.json").is_file():
        raise FileNotFoundError(
            f"LLM artifacts missing at {path}. Run `make models-export` or bake models into the image."
        )
    dev = device or ("cuda" if torch.cuda.is_available() and os.environ.get("VULCAN_RUNTIME_MODE") == "gpu" else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(str(path), local_files_only=True)
    model.to(dev)
    model.eval()
    return LlmBundle(tokenizer=tokenizer, model=model, device=dev)


def load_vision() -> VisionBundle:
    import onnxruntime as ort

    path = models_dir() / "vision" / "resnet18"
    onnx_path = path / "model.onnx"
    if not onnx_path.is_file():
        raise FileNotFoundError(
            f"Vision ONNX missing at {onnx_path}. Run `make models-export` or bake models into the image."
        )
    preprocess = json.loads((path / "preprocess.json").read_text(encoding="utf-8"))
    labels = json.loads((path / "imagenet_classes.json").read_text(encoding="utf-8"))
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    return VisionBundle(
        session=session,
        input_name=preprocess.get("input_name", "pixel_values"),
        output_name=preprocess.get("output_name", "logits"),
        labels=list(labels),
        mean=list(preprocess.get("mean") or [0.485, 0.456, 0.406]),
        std=list(preprocess.get("std") or [0.229, 0.224, 0.225]),
        crop=int(preprocess.get("crop") or 224),
    )
