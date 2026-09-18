"""Build providers from serializable configs without embedding secrets."""

import os
from pathlib import Path

from .openai_compatible import OpenAICompatibleProvider
from .anthropic import AnthropicProvider
from .gemini import GeminiProvider
from .local_vllm import LocalVLLMProvider


_PROVIDER_CLASSES = {
    "openai_compatible": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "local_vllm": LocalVLLMProvider,
}


def build_provider(config):
    config = dict(config)
    endpoint_env = config.pop("endpoint_env", None)
    if endpoint_env:
        endpoint = os.environ.get(endpoint_env)
        if not endpoint:
            raise ValueError(
                f"required provider endpoint is not set: {endpoint_env}"
            )
        if config.get("endpoint"):
            raise ValueError(
                "provider config cannot set both endpoint and endpoint_env"
            )
        config["endpoint"] = endpoint
    provider_type = config.pop("provider")
    api_key_env = config.pop("api_key_env", None)
    api_key_file = config.pop("api_key_file", None)
    api_key = os.environ.get(api_key_env) if api_key_env else None
    if not api_key and api_key_file:
        path = Path(api_key_file).expanduser()
        if path.is_file():
            api_key = path.read_text(encoding="utf-8").strip()
    if api_key_env or api_key_file:
        if not api_key:
            sources = " or ".join(filter(None, (api_key_env, str(api_key_file or ""))))
            raise ValueError(f"required provider secret is not set: {sources}")
        config["api_key"] = api_key
    provider_class = _PROVIDER_CLASSES.get(provider_type)
    if provider_class is None:
        raise ValueError(f"unknown provider: {provider_type}")
    return provider_class(**config)


def public_provider_config(config):
    return {
        key: value
        for key, value in config.items()
        if key not in {"api_key", "api_key_env", "api_key_file"}
    }
