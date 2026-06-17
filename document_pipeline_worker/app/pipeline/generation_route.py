from __future__ import annotations

from dataclasses import dataclass

from document_pipeline_core.common.templates import (
    ClinicalTemplate,
    template_supports_hybrid_generation,
)
from document_pipeline_core.generation.lib import GENERATION_ROUTE_HYBRID

from app.pipeline.config import PipelineConfig


@dataclass(frozen=True, slots=True)
class ResolvedGenerationRoute:
    requested_generation_route: str
    effective_generation_route: str
    template_supports_hybrid: bool

    def metadata(self) -> dict[str, object]:
        return {
            "requested_generation_route": self.requested_generation_route,
            "effective_generation_route": self.effective_generation_route,
            "template_supports_hybrid": self.template_supports_hybrid,
        }


def resolve_effective_generation_route(
    *,
    template: ClinicalTemplate,
    pipeline_config: PipelineConfig,
) -> ResolvedGenerationRoute:
    requested = pipeline_config.generation_route.strip().lower()
    supports_hybrid = template_supports_hybrid_generation(template)
    effective = GENERATION_ROUTE_HYBRID if supports_hybrid else requested
    return ResolvedGenerationRoute(
        requested_generation_route=requested,
        effective_generation_route=effective,
        template_supports_hybrid=supports_hybrid,
    )


__all__ = [
    "ResolvedGenerationRoute",
    "resolve_effective_generation_route",
]
