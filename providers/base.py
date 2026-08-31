"""Provider abstraction used by all model-backed policies."""

from abc import ABC, abstractmethod


class ModelProvider(ABC):
    @abstractmethod
    def complete(self, messages):
        """Return one assistant text for a list of chat messages."""
