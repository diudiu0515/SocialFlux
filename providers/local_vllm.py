"""Local vLLM uses the same OpenAI-compatible contract."""

from .openai_compatible import OpenAICompatibleProvider


class LocalVLLMProvider(OpenAICompatibleProvider):
    pass
