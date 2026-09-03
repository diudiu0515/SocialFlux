"""Build providers from serializable configs without embedding secrets."""

import os

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
    provider_type = config.pop("provider")
    api_key_env = config.pop("api_key_env", None)
    if api_key_env:
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ValueError(f"required provider secret is not set: {api_key_env}")
        config["api_key"] = api_key
    provider_class = _PROVIDER_CLASSES.get(provider_type)
    if provider_class is None:
        raise ValueError(f"unknown provider: {provider_type}")
    return provider_class(**config)


def public_provider_config(config):
    return {
        key: value
        for key, value in config.items()
        if key not in {"api_key", "api_key_env"}
    }
