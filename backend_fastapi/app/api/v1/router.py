from fastapi import APIRouter

from app.domains.auth import api as auth_api
from app.domains.copilot import api as copilot_api
from app.domains.copilot import internal_tools_api as copilot_internal_tools_api
from app.domains.documents import api as documents_api
from app.domains.documents import callbacks_api as document_callbacks_api
from app.domains.documents import generation_api as document_generation_api
from app.domains.documents import sse_api
from app.domains.encounters import api as encounters_api
from app.domains.patients import api as patients_api
from app.domains.system import csrf_api, health_api
from app.domains.templates import api as templates_api
from app.domains.transcription import api as transcription_api
from app.domains.transcription import api_test as transcription_api_test

api_v1_router = APIRouter()
api_v1_router.include_router(health_api.router, tags=["health"])
api_v1_router.include_router(csrf_api.router, tags=["csrf"])
api_v1_router.include_router(auth_api.router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(encounters_api.router, tags=["encounters"])
api_v1_router.include_router(documents_api.router, tags=["documents"])
api_v1_router.include_router(document_generation_api.router, tags=["documents"])
api_v1_router.include_router(document_callbacks_api.router, tags=["documents"])
api_v1_router.include_router(transcription_api.router, tags=["transcription"])
api_v1_router.include_router(transcription_api_test.router, tags=["transcription-test"])
api_v1_router.include_router(patients_api.router, tags=["patients"])
api_v1_router.include_router(templates_api.router, tags=["templates"])
api_v1_router.include_router(sse_api.router, tags=["sse"])
api_v1_router.include_router(copilot_api.router)
api_v1_router.include_router(copilot_internal_tools_api.router)
