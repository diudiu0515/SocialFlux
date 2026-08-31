"""Build providers from a small, serializable policy config."""

from .openai_compatible import OpenAICompatibleProvider
from .anthropic import AnthropicProvider
from .gemini import GeminiProvider
from .local_vllm import LocalVLLMProvider


def build_provider(config):
    provider_type = config["provider"]
    kwargs = {key: value for key, value in config.items() if key != "provider"}
    if provider_type == "openai_compatible":
        return OpenAICompatibleProvider(**kwargs)
    if provider_type == "anthropic":
        return AnthropicProvider(**kwargs)
    if provider_type == "gemini":
        return GeminiProvider(**kwargs)
    if provider_type == "local_vllm":
        return LocalVLLMProvider(**kwargs)
    raise ValueError(f"unknown provider: {provider_type}")
