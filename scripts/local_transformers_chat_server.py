#!/usr/bin/env python3
"""Minimal OpenAI-compatible local Transformers server for reproducible rollouts."""

import argparse
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
import uvicorn


def _final_text(value):
    text = str(value).strip()
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1].strip()
    return text


def _load_backend(model_path, architecture):
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
            torch_dtype=torch.bfloat16,
            device_map="cuda",
            trust_remote_code=True,
        ).eval()
    else:
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            device_map="cuda",
            trust_remote_code=True,
        ).eval()
    return tokenizer, model


def create_app(model_path, architecture="auto"):
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
            if not isinstance(inputs, dict):
                inputs = {"input_ids": inputs}
            inputs = {key: value.to(model.device) for key, value in inputs.items()}
            temperature = float(payload.get("temperature", 0.7))
            generation = {
                "max_new_tokens": int(payload.get("max_tokens", 512)),
                "do_sample": temperature > 0,
                "temperature": max(temperature, 1e-5),
            }
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
    args = parser.parse_args()
    uvicorn.run(
        create_app(args.model, args.architecture),
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
