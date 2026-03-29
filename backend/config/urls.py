from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from ninja import NinjaAPI
from apps.users.api import router as accounts_router
from apps.encounters.api import router as encounters_router
from apps.patients.api import router as patients_router
from apps.templates.api import router as templates_router
from django.conf import settings

from apps.documents.api import (
    base_router as documents_base_router,
    documents_callbacks_router,
    documents_generation_router,
    sse_router,
)
from apps.generative_ai.api import router as generative_ai_router

api = NinjaAPI(
    title="Medical API",
    version="1.0.0",
    urls_namespace="medical_api",
    csrf=not getattr(settings, "ENVIRONMENT", "") == "dev",  # Disable in dev only
)


@api.get("/csrf")
@ensure_csrf_cookie
@csrf_exempt
def get_csrf_token(request):
    return HttpResponse()


api.add_router("/", documents_base_router)
api.add_router("/", sse_router)
api.add_router("/", documents_callbacks_router)
api.add_router("/", documents_generation_router)
api.add_router("/auth/", accounts_router)
api.add_router("/", encounters_router)
api.add_router("/", patients_router)
api.add_router("/", templates_router)
api.add_router("/", generative_ai_router)

def _health(_request):
    """Lightweight liveness check for load balancers and Docker HEALTHCHECK."""
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("api/health/", _health),
    path("api/admin/", admin.site.urls),
    path("api/", api.urls),
    path("api/silk/", include("silk.urls", namespace="silk")),
]
