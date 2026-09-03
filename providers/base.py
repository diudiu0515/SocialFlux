"""Provider abstraction used by model policies and the canonical environment."""

from abc import ABC, abstractmethod


class ModelProvider(ABC):
    @abstractmethod
    def complete(self, messages, **generation):
        """Return one assistant text using optional sampling parameters."""

    @property
    def provenance(self):
        return {"provider": self.__class__.__name__}
