"""Canonical SocialFlux production pipeline.

The package owns orchestration only. Domain logic remains with ``environment``,
``evaluation``, ``rollout`` and ``tasks``.
"""

from .flow import PIPELINE_STAGES, PipelinePreflight, Stage

__all__ = ["PIPELINE_STAGES", "PipelinePreflight", "Stage"]
