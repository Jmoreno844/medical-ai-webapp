from .base import router as base_router
from .callbacks import router as documentos_callbacks_router
from .generation import router as documentos_generation_router
from .sse import router as sse_router

__all__ = [
    "base_router",
    "sse_router",
    "documentos_callbacks_router",
    "documentos_generation_router",
]
