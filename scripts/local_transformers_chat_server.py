#!/usr/bin/env python3
"""Minimal OpenAI-compatible local Transformers server for reproducible rollouts."""

import argparse
import logging
from collections.abc import Mapping
from contextlib import asynccontextmanager
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException
import torch
from transformers import (
    AutoConfig,
    AutoModelForCausalLM,
    AutoModelForImageTextToText,
    AutoProcessor,
    AutoTokenizer,
)
from transformers.cache_utils import DynamicCache
from transformers.utils import import_utils as transformers_import_utils
import uvicorn

LOGGER = logging.getLogger(__name__)
_ORIGINAL_DYNAMIC_CACHE_GET_MAX_LENGTH = DynamicCache.get_max_length


def _final_text(value):
    text = str(value).strip()
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1].strip()
    return text


def _legacy_get_max_length(cache):
    try:
        return _ORIGINAL_DYNAMIC_CACHE_GET_MAX_LENGTH(cache)
    except ValueError:
        return None


def _legacy_get_usable_length(cache, new_seq_length, layer_idx=0):
    previous_length = cache.get_seq_length(layer_idx)
    maximum_length = cache.get_max_length()
    if maximum_length is not None and previous_length + new_seq_length > maximum_length:
        return maximum_length - new_seq_length
    return previous_length


def _install_transformers_compatibility_shims():
    # DeepSeek-V2-Lite remote code still imports this Transformers 4 helper.
    # FX wrapping is optional for inference, so a false fallback is safe.
    if not hasattr(transformers_import_utils, "is_torch_fx_available"):
        transformers_import_utils.is_torch_fx_available = lambda: False
    if not hasattr(DynamicCache, "seen_tokens"):
        DynamicCache.seen_tokens = property(lambda cache: cache.get_seq_length())
    DynamicCache.get_max_length = _legacy_get_max_length
    if not hasattr(DynamicCache, "get_usable_length"):
        DynamicCache.get_usable_length = _legacy_get_usable_length


def _load_backend(model_path, architecture):
    _install_transformers_compatibility_shims()
    if architecture == "auto":
        config = AutoConfig.from_pretrained(model_path, trust_remote_code=True)
        names = " ".join(getattr(config, "architectures", [])).lower()
        architecture = "image_text" if any(
            token in names for token in ("conditionalgeneration", "imagetotext")
        ) else "causal_lm"
    if architecture == "image_text":
        tokenizer = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForImageTextToText.from_pretrained(
            model_path,
            dtype=torch.bfloat16,
            device_map="cuda",
            trust_remote_code=True,
        ).eval()
    else:
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            dtype=torch.bfloat16,
            device_map="cuda",
            trust_remote_code=True,
        ).eval()
    return tokenizer, model


def create_app(model_path, architecture="auto", use_cache=True):
    state = {}
    lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        state["processor"], state["model"] = _load_backend(model_path, architecture)
        yield
        state.clear()

    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"ok": "model" in state, "model": model_path}

    @app.post("/v1/chat/completions")
    def chat(payload: dict):
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=400, detail="messages must be a non-empty list")
        processor = state["processor"]
        model = state["model"]
        try:
            template_options = {
                "add_generation_prompt": True,
                "tokenize": True,
                "return_dict": True,
                "return_tensors": "pt",
            }
            try:
                inputs = processor.apply_chat_template(
                    messages,
                    enable_thinking=False,
                    **template_options,
                )
            except (TypeError, ValueError):
                inputs = processor.apply_chat_template(messages, **template_options)
            if isinstance(inputs, Mapping):
                inputs = dict(inputs)
            else:
                inputs = {"input_ids": inputs}
            inputs = {key: value.to(model.device) for key, value in inputs.items()}
            temperature = float(payload.get("temperature", 0.7))
            generation = {
                "max_new_tokens": int(payload.get("max_tokens", 512)),
                "do_sample": temperature > 0,
                "use_cache": use_cache,
            }
            if temperature > 0:
                generation["temperature"] = temperature
            for key in ("top_p", "top_k", "repetition_penalty"):
                if payload.get(key) is not None:
                    generation[key] = payload[key]
            with lock, torch.inference_mode():
                if isinstance(payload.get("seed"), int):
                    torch.manual_seed(payload["seed"])
                    torch.cuda.manual_seed_all(payload["seed"])
                output = model.generate(**inputs, **generation)
            prompt_length = inputs["input_ids"].shape[-1]
            text = _final_text(processor.decode(
                output[0][prompt_length:],
                skip_special_tokens=True,
            ))
        except Exception as exc:
            LOGGER.exception("chat completion failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": payload.get("model", model_path),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }],
        }

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--architecture",
        choices=("auto", "causal_lm", "image_text"),
        default="auto",
    )
    parser.add_argument("--disable-cache", action="store_true")
    args = parser.parse_args()
    uvicorn.run(
        create_app(args.model, args.architecture, use_cache=not args.disable_cache),
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
