"""Provider abstraction used by model policies and the canonical environment."""

from abc import ABC, abstractmethod



class IncompleteModelOutputError(RuntimeError):
    """A provider ended before producing a complete assistant response."""

    def __init__(self, message, *, finish_reason, raw_output, request=None):
        super().__init__(message)
        self.finish_reason = finish_reason
        self.raw_output = raw_output
        self.request = request


class ModelProvider(ABC):
    @abstractmethod
    def complete(self, messages, **generation):
        """Return one assistant text using optional sampling parameters."""

    @property
    def provenance(self):
        return {"provider": self.__class__.__name__}
