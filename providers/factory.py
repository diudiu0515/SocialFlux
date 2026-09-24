"""Build providers from serializable configs without embedding secrets."""

import os
from pathlib import Path

from .openai_compatible import OpenAICompatibleProvider
from .openai_responses import OpenAIResponsesProvider
from .failover import FailoverProvider
from .anthropic import AnthropicProvider
from .gemini import GeminiProvider
from .local_vllm import LocalVLLMProvider


_PROVIDER_CLASSES = {
    "openai_compatible": OpenAICompatibleProvider,
    "openai_responses": OpenAIResponsesProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "local_vllm": LocalVLLMProvider,
    "failover": FailoverProvider,
}


def build_provider(config):
    config = dict(config)
    if config.get("provider") == "failover":
        config.pop("provider")
        candidates = config.pop("candidates", None)
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("failover provider requires non-empty candidates")
        return FailoverProvider(
            candidates=[build_provider(candidate) for candidate in candidates],
            **config,
        )
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
    api_key_files = config.pop("api_key_files", None)
    if api_key_files and (api_key_env or api_key_file):
        raise ValueError(
            "provider config cannot combine api_key_files with another secret source"
        )
    api_key = os.environ.get(api_key_env) if api_key_env else None
    if not api_key and api_key_file:
        path = Path(api_key_file).expanduser()
        if path.is_file():
            api_key = path.read_text(encoding="utf-8").strip()
    if api_key_files:
        if not isinstance(api_key_files, list) or not api_key_files:
            raise ValueError("api_key_files must be a non-empty list")
        api_keys = []
        for item in api_key_files:
            path = Path(item).expanduser()
            key = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
            if not key:
                raise ValueError(f"required provider secret is not set: {path}")
            api_keys.append(key)
        config["api_keys"] = api_keys
    elif api_key_env or api_key_file:
        if not api_key:
            sources = " or ".join(filter(None, (api_key_env, str(api_key_file or ""))))
            raise ValueError(f"required provider secret is not set: {sources}")
        config["api_key"] = api_key
    provider_class = _PROVIDER_CLASSES.get(provider_type)
    if provider_class is None:
        raise ValueError(f"unknown provider: {provider_type}")
    return provider_class(**config)


def public_provider_config(config):
    private_keys = {
        "api_key", "api_keys", "api_key_env", "api_key_file", "api_key_files",
    }
    result = {}
    for key, value in config.items():
        if key in private_keys:
            continue
        if key == "candidates" and isinstance(value, list):
            result[key] = [public_provider_config(item) for item in value]
        else:
            result[key] = value
    return result
