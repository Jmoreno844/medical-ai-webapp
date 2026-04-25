from fastapi import APIRouter

from app.domains.auth import api as auth_api
from app.domains.documents import api as documents_api
from app.domains.documents import sse_api
from app.domains.encounters import api as encounters_api
from app.domains.patients import api as patients_api
from app.domains.system import csrf_api, health_api
from app.domains.templates import api as templates_api

api_v1_router = APIRouter()
api_v1_router.include_router(health_api.router, tags=["health"])
api_v1_router.include_router(csrf_api.router, tags=["csrf"])
api_v1_router.include_router(auth_api.router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(encounters_api.router, tags=["encounters"])
api_v1_router.include_router(documents_api.router, tags=["documents"])
api_v1_router.include_router(patients_api.router, tags=["patients"])
api_v1_router.include_router(templates_api.router, tags=["templates"])
api_v1_router.include_router(sse_api.router, tags=["sse"])
